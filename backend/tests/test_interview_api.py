"""Integration tests for the interview REST endpoints (Section 7.3)."""

import uuid
from datetime import timedelta

from app.core.timeutils import utcnow
from app.models.interview import InterviewSession


def _signup_and_login(client, email="candidate@example.com"):
    client.post("/api/v1/auth/signup", json={"name": "Ada Candidate", "email": email, "password": "Str0ng!Pass"})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "Str0ng!Pass"})
    return resp.json()["data"]["accessToken"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _start_body(**overrides):
    body = {
        "role": "SDE",
        "type": "mixed",
        "durationMinutes": 15,
        "mode": "voice",
        "consentGiven": True,
    }
    body.update(overrides)
    return body


def test_start_interview_success(client):
    token = _signup_and_login(client)
    resp = client.post("/api/v1/interviews/start", json=_start_body(), headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["sessionId"]
    assert data["wsUrl"].endswith(f"/interviews/{data['sessionId']}/live")
    assert data["transportMode"] == "browser_native_speech"


def test_start_interview_requires_consent(client):
    token = _signup_and_login(client)
    resp = client.post(
        "/api/v1/interviews/start", json=_start_body(consentGiven=False), headers=_auth_headers(token)
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "consent_required"


def test_start_interview_accepts_sign_mode(client):
    """
    Phase 6. Sign mode was refused with `mode_not_available` up to Phase 5; it is
    now a first-class path through the same engine, so the same request that used
    to 400 has to start a real session.
    """
    token = _signup_and_login(client)
    resp = client.post("/api/v1/interviews/start", json=_start_body(mode="sign"), headers=_auth_headers(token))
    assert resp.status_code == 200
    started = resp.json()["data"]
    assert started["sessionId"]
    assert started["wsUrl"]  # the same live protocol, not a separate endpoint

    detail = client.get(
        f"/api/v1/interviews/{started['sessionId']}", headers=_auth_headers(token)
    ).json()["data"]
    assert detail["mode"] == "sign"
    # Same planned question list as voice: the modality changes how answers are
    # given, not what gets asked.
    assert len(detail["questions"]) > 0


def test_start_interview_requires_auth(client):
    resp = client.post("/api/v1/interviews/start", json=_start_body())
    assert resp.status_code == 401


def test_get_interview_detail(client):
    token = _signup_and_login(client)
    start_resp = client.post("/api/v1/interviews/start", json=_start_body(), headers=_auth_headers(token))
    session_id = start_resp.json()["data"]["sessionId"]

    detail_resp = client.get(f"/api/v1/interviews/{session_id}", headers=_auth_headers(token))
    assert detail_resp.status_code == 200
    data = detail_resp.json()["data"]
    assert data["id"] == session_id
    assert data["status"] == "in_progress"
    assert len(data["questions"]) == 3
    assert data["questions"][0]["answer"] is None


def test_get_interview_detail_blocks_other_users(client):
    token_a = _signup_and_login(client, email="a@example.com")
    token_b = _signup_and_login(client, email="b@example.com")
    start_resp = client.post("/api/v1/interviews/start", json=_start_body(), headers=_auth_headers(token_a))
    session_id = start_resp.json()["data"]["sessionId"]

    resp = client.get(f"/api/v1/interviews/{session_id}", headers=_auth_headers(token_b))
    assert resp.status_code == 404


def test_end_interview_marks_completed(client):
    token = _signup_and_login(client)
    start_resp = client.post("/api/v1/interviews/start", json=_start_body(), headers=_auth_headers(token))
    session_id = start_resp.json()["data"]["sessionId"]

    end_resp = client.post(f"/api/v1/interviews/{session_id}/end", headers=_auth_headers(token))
    assert end_resp.status_code == 200
    assert end_resp.json()["data"]["status"] == "completed"


def test_start_interview_accepts_jd_and_company(client):
    """Section 4.6: JD + company are persisted at session start for the engine to use."""
    token = _signup_and_login(client)
    resp = client.post(
        "/api/v1/interviews/start",
        json=_start_body(
            jobDescriptionText="We need a backend engineer strong in Go and Kubernetes.",
            targetCompanyName="a fintech startup",
        ),
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    session_id = resp.json()["data"]["sessionId"]

    detail = client.get(f"/api/v1/interviews/{session_id}", headers=_auth_headers(token)).json()["data"]
    assert detail["jobDescriptionText"] == "We need a backend engineer strong in Go and Kubernetes."
    assert detail["targetCompanyName"] == "a fintech startup"


def test_role_is_optional_when_a_job_description_is_supplied(client):
    """Section 4.6: "If a JD is entered, the role dropdown becomes optional-but-still-shown"."""
    token = _signup_and_login(client)
    resp = client.post(
        "/api/v1/interviews/start",
        json=_start_body(role="", jobDescriptionText="Senior Python engineer, async experience required."),
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200

    session_id = resp.json()["data"]["sessionId"]
    detail = client.get(f"/api/v1/interviews/{session_id}", headers=_auth_headers(token)).json()["data"]
    # role_target is NOT NULL and drives history grouping, so a JD-only
    # session still needs a human-readable label.
    assert detail["roleTarget"]


def test_start_interview_rejects_neither_role_nor_job_description(client):
    token = _signup_and_login(client)
    resp = client.post(
        "/api/v1/interviews/start", json=_start_body(role=""), headers=_auth_headers(token)
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "role_or_job_description_required"


def test_job_description_length_is_validated_server_side(client):
    """Section 4.6: "max ~5,000 characters ... server-side length-validated"."""
    token = _signup_and_login(client)
    resp = client.post(
        "/api/v1/interviews/start",
        json=_start_body(jobDescriptionText="x" * 5001),
        headers=_auth_headers(token),
    )
    assert resp.status_code == 422


def test_interview_history_lists_sessions_most_recent_first(client, db_session):
    token = _signup_and_login(client)
    first = client.post("/api/v1/interviews/start", json=_start_body(role="Data Analyst"), headers=_auth_headers(token))
    second = client.post("/api/v1/interviews/start", json=_start_body(role="SDE"), headers=_auth_headers(token))

    # Both starts land inside one tick of a ~15ms clock, so as written they carry
    # the same `started_at` and "most recent" has no answer. Backdating the first
    # one gives the ordering something real to sort on -- which is the behaviour
    # under test, rather than the resolution of the host clock.
    first_id = uuid.UUID(first.json()["data"]["sessionId"])
    session_row = db_session.get(InterviewSession, first_id)
    session_row.started_at = utcnow() - timedelta(hours=1)
    db_session.commit()

    history_resp = client.get("/api/v1/interviews/history", headers=_auth_headers(token))
    assert history_resp.status_code == 200
    items = history_resp.json()["data"]
    assert len(items) == 2
    ids_in_order = [item["id"] for item in items]
    assert ids_in_order[0] == second.json()["data"]["sessionId"]
    assert ids_in_order[1] == first.json()["data"]["sessionId"]


def test_history_order_is_stable_when_two_sessions_share_a_timestamp(client, db_session):
    """
    Two sessions really can carry the same `started_at`: the clock behind
    `utcnow()` has ~15ms resolution on Windows, and starting a session is faster
    than that. `started_at` alone is then not a total order, so the database may
    return the tied rows in a different order on each call -- which a paged
    history turns into a session shown twice and another never shown at all.
    """
    token = _signup_and_login(client)
    started = client.post("/api/v1/interviews/start", json=_start_body(role="SDE"), headers=_auth_headers(token))
    other = client.post("/api/v1/interviews/start", json=_start_body(role="SDE"), headers=_auth_headers(token))

    tied_at = utcnow()
    for response in (started, other):
        row = db_session.get(InterviewSession, uuid.UUID(response.json()["data"]["sessionId"]))
        row.started_at = tied_at
    db_session.commit()

    orders = set()
    for _ in range(4):
        resp = client.get("/api/v1/interviews/history", headers=_auth_headers(token))
        assert resp.status_code == 200
        orders.add(tuple(item["id"] for item in resp.json()["data"]))
    assert len(orders) == 1, f"tied sessions came back in {len(orders)} different orders"

    # And each page of a paged read sees a different session, rather than the
    # same one twice.
    pages = []
    for offset in (0, 1):
        resp = client.get(
            f"/api/v1/interviews/history?limit=1&offset={offset}", headers=_auth_headers(token)
        )
        assert resp.status_code == 200
        pages.append(resp.json()["data"][0]["id"])
    assert pages[0] != pages[1]
