"""
Feedback and export endpoint tests (Section 7.4, Section 4.10, Section 12.1A).

Covers the three things that would hurt most if they broke: someone reading
another candidate's transcript, a processing screen with nothing real to poll,
and an export endpoint with no cost ceiling.
"""
import json

from app.models.user import User
from tests.feedback_factories import make_scored_session, make_session


def _signup_and_login(client, email="feedback@example.com"):
    client.post("/api/v1/auth/signup", json={"name": "Ada Candidate", "email": email, "password": "Str0ng!Pass"})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "Str0ng!Pass"})
    return resp.json()["data"]["accessToken"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _user_by_email(db, email):
    return db.query(User).filter(User.email == email).one()


def _generate(client, token, session_id):
    return client.post(f"/api/v1/feedback/{session_id}/generate", headers=_headers(token))


# ---------------------------------------------------------------------------
# Report lifecycle (Section 4.10 / 4.11)
# ---------------------------------------------------------------------------
def test_status_is_pending_before_generation_starts(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user)

    resp = client.get(f"/api/v1/feedback/{session.id}/status", headers=_headers(token))
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "pending"


def test_report_404s_with_a_distinct_code_before_generation(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user)

    resp = client.get(f"/api/v1/feedback/{session.id}", headers=_headers(token))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "feedback_not_generated"


def test_generate_then_read_full_report(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user, company="Acme")

    gen = _generate(client, token, session.id)
    assert gen.status_code == 200

    resp = client.get(f"/api/v1/feedback/{session.id}", headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["status"] == "ready"
    assert data["sessionId"] == str(session.id)
    assert data["roleTarget"] == "Backend Engineer"
    assert data["targetCompanyName"] == "Acme"
    assert data["overallReadinessScore"] is not None
    assert data["readinessLabel"]
    assert data["summaryText"]
    assert data["disclaimer"]

    # Section 10.2's four categories are always present, each flagged with
    # whether it was actually measured.
    by_category = {row["category"]: row for row in data["categoryScores"]}
    assert set(by_category) == {"content", "communication", "confidence", "body_language"}
    assert by_category["content"]["measured"] is True
    assert by_category["confidence"]["measured"] is False
    assert by_category["confidence"]["score"] is None
    assert set(data["unmeasuredCategories"]) == {"confidence", "body_language"}

    # Section 9.8's skip accounting reaches the client.
    assert data["answeredCount"] == 2
    assert data["skippedCount"] == 1
    assert data["questionCount"] == 3
    assert any(turn["isSkipped"] for turn in data["turns"])

    assert data["strengths"] or data["improvements"]
    assert data["signals"]["answerCount"] == 2


def test_status_reports_ready_after_generation(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user)
    _generate(client, token, session.id)

    resp = client.get(f"/api/v1/feedback/{session.id}/status", headers=_headers(token))
    data = resp.json()["data"]
    assert data["status"] == "ready"
    assert data["generatedAt"]


def test_status_does_not_report_the_degraded_fallback_as_an_error(client, db_session):
    """
    Falling back to the deterministic writer is a success, not a failure. Leaking
    the fallback reason into `error` would make the processing screen show a
    failure banner over a report that generated fine.
    """
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user)
    _generate(client, token, session.id)

    from app.services.feedback import generator

    report = generator.get_report(db_session, session.id)
    assert report.generated_by == "deterministic"
    assert report.generation_error  # recorded server-side for diagnostics

    data = client.get(f"/api/v1/feedback/{session.id}/status", headers=_headers(token)).json()["data"]
    assert data["status"] == "ready"
    assert data["error"] is None


def test_generate_is_refused_while_the_interview_is_in_progress(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_session(db_session, user, status="in_progress")

    resp = _generate(client, token, session.id)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "interview_in_progress"


def test_ending_an_interview_starts_generation(client):
    """Section 4.10: the processing screen must have a real state to poll immediately."""
    token = _signup_and_login(client)
    start = client.post(
        "/api/v1/interviews/start",
        json={"role": "SDE", "type": "mixed", "durationMinutes": 15, "mode": "voice", "consentGiven": True},
        headers=_headers(token),
    )
    session_id = start.json()["data"]["sessionId"]

    end = client.post(f"/api/v1/interviews/{session_id}/end", headers=_headers(token))
    assert end.status_code == 200

    status = client.get(f"/api/v1/feedback/{session_id}/status", headers=_headers(token))
    # TestClient runs BackgroundTasks before returning, so by now the job has
    # finished; either state proves the row was claimed rather than 404ing.
    assert status.json()["data"]["status"] in {"processing", "ready"}


# ---------------------------------------------------------------------------
# Authorization (Section 12.2)
# ---------------------------------------------------------------------------
def test_another_user_cannot_read_a_report(client, db_session):
    owner_token = _signup_and_login(client, "owner@example.com")
    owner = _user_by_email(db_session, "owner@example.com")
    session = make_scored_session(db_session, owner)
    _generate(client, owner_token, session.id)

    intruder_token = _signup_and_login(client, "intruder@example.com")
    for path in (
        f"/api/v1/feedback/{session.id}",
        f"/api/v1/feedback/{session.id}/status",
        f"/api/v1/feedback/{session.id}/pdf",
        f"/api/v1/recordings/{session.id}/transcript",
    ):
        resp = client.get(path, headers=_headers(intruder_token))
        assert resp.status_code == 404, path


def test_feedback_requires_authentication(client, db_session):
    _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user)
    assert client.get(f"/api/v1/feedback/{session.id}").status_code == 401


# ---------------------------------------------------------------------------
# Exports (Section 7.4)
# ---------------------------------------------------------------------------
def test_pdf_download_returns_a_real_pdf(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user)
    _generate(client, token, session.id)

    resp = client.get(f"/api/v1/feedback/{session.id}/pdf", headers=_headers(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment;" in resp.headers["content-disposition"]
    assert resp.headers["cache-control"] == "private, no-store"
    assert resp.content.startswith(b"%PDF-")
    assert len(resp.content) > 1000


def test_pdf_is_refused_until_the_report_is_ready(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user)

    from app.services.feedback import generator

    generator.claim_report(db_session, session.id)

    resp = client.get(f"/api/v1/feedback/{session.id}/pdf", headers=_headers(token))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "feedback_not_ready"


def test_transcript_txt_contains_questions_answers_and_the_disclaimer(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user)

    resp = client.get(f"/api/v1/recordings/{session.id}/transcript", headers=_headers(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "MockMateAI — Interview Transcript" in body
    assert "not an assessment by any employer" in body
    assert "[Q1]" in body and "[Q3]" in body
    assert "skipped" in body


def test_transcript_json_includes_per_turn_scores(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user)
    _generate(client, token, session.id)

    resp = client.get(f"/api/v1/recordings/{session.id}/transcript?format=json", headers=_headers(token))
    assert resp.status_code == 200
    payload = json.loads(resp.content)
    assert payload["session"]["roleTarget"] == "Backend Engineer"
    assert len(payload["turns"]) == 3
    assert payload["turns"][0]["relevanceScore"] == 9
    assert payload["turns"][2]["isSkipped"] is True
    assert payload["report"]["overallReadinessScore"] is not None


def test_transcript_rejects_an_unknown_format(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user)

    resp = client.get(f"/api/v1/recordings/{session.id}/transcript?format=docx", headers=_headers(token))
    assert resp.status_code == 422


def test_audio_download_is_honestly_unavailable(client, db_session):
    """This build records no audio, so the endpoint says so instead of faking a file."""
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user)

    resp = client.get(f"/api/v1/recordings/{session.id}/audio", headers=_headers(token))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "recording_unavailable"
    assert "no audio is uploaded or stored" in resp.json()["error"]["message"]


def test_export_quota_is_enforced_per_user(client, db_session):
    """Section 12.1A's export tier: 20 per hour per user."""
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "feedback@example.com")
    session = make_scored_session(db_session, user)
    path = f"/api/v1/recordings/{session.id}/transcript"

    for _ in range(20):
        assert client.get(path, headers=_headers(token)).status_code == 200

    blocked = client.get(path, headers=_headers(token))
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "export_quota_exceeded"
