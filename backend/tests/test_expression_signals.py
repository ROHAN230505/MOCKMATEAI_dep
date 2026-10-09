"""
Expression Signal Service tests (Section 9.7, Phase 5B).

Expression has the widest trust boundary in the product: unlike prosody, where
the server independently derives half the row from the transcript, there is no
server-side view of the video at all. Every number originates in the browser.
So most of what is pinned here is the refusal to believe it uncritically —
bounds, coverage gates, and the rule that a session which stops being measurable
loses its earlier scores instead of keeping stale ones.
"""
import pytest

from app.models.enums import SessionStatus
from app.models.signals import ExpressionSignal
from app.models.user import User
from app.services.feedback.scoring import compute_breakdown
from tests.feedback_factories import make_scored_session, make_session

PASSWORD = "Str0ng!Pass"


def _signup_and_login(client, email="expression@example.com"):
    client.post("/api/v1/auth/signup", json={"name": "Ada", "email": email, "password": PASSWORD})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return resp.json()["data"]["accessToken"]


def _headers(token):
    return {"Authorization": "Bearer " + token}


def _user_by_email(db, email):
    return db.query(User).filter(User.email == email).one()


def _url(session_id):
    return "/api/v1/interviews/" + str(session_id) + "/signals/expression"


def _body(**overrides):
    body = {
        "eyeContactPercentage": 71.5,
        "smileFrequencyScore": 45.0,
        "postureFlagCount": 2,
        "analysedSeconds": 640.0,
        "faceDetectedSeconds": 590.0,
    }
    body.update(overrides)
    return body


# --- Submission ---


def test_expression_is_recorded_and_readable(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)

    resp = client.post(_url(session.id), json=_body(), headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["eyeContactPercentage"] == pytest.approx(71.5)
    assert data["smileFrequencyScore"] == pytest.approx(45.0)
    assert data["postureFlagCount"] == 2

    read = client.get(_url(session.id), headers=_headers(token))
    assert read.status_code == 200
    assert read.json()["data"]["eyeContactPercentage"] == pytest.approx(71.5)


def test_coverage_figures_are_not_stored(client, db_session):
    """
    `analysedSeconds` and `faceDetectedSeconds` exist to justify the three scores,
    not to be kept. They are checked and discarded — the response carries only
    what Section 8's table holds.
    """
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)

    resp = client.post(_url(session.id), json=_body(), headers=_headers(token))
    assert set(resp.json()["data"]) == {
        "sessionId",
        "eyeContactPercentage",
        "smileFrequencyScore",
        "postureFlagCount",
    }


def test_resubmission_upserts_rather_than_duplicating(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)

    client.post(_url(session.id), json=_body(eyeContactPercentage=40.0), headers=_headers(token))
    client.post(_url(session.id), json=_body(eyeContactPercentage=82.0), headers=_headers(token))

    rows = db_session.query(ExpressionSignal).filter(ExpressionSignal.session_id == session.id).all()
    assert len(rows) == 1
    db_session.refresh(rows[0])
    assert rows[0].eye_contact_percentage == pytest.approx(82.0)


# --- Trust boundary ---


@pytest.mark.parametrize(
    "field,value",
    [
        ("eyeContactPercentage", 101),
        ("eyeContactPercentage", -1),
        ("smileFrequencyScore", 1000),
        ("smileFrequencyScore", -0.5),
        ("postureFlagCount", -1),
        ("postureFlagCount", 5000),
        ("analysedSeconds", -1),
        ("faceDetectedSeconds", -1),
    ],
)
def test_out_of_range_values_are_rejected(client, db_session, field, value):
    """
    There is no server-side view of the video to cross-check these against, so
    the schema bounds are the whole defence. A crafted request must not be able
    to award itself a body-language score.
    """
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)

    resp = client.post(_url(session.id), json=_body(**{field: value}), headers=_headers(token))
    assert resp.status_code == 422


def test_too_little_analysed_video_is_discarded(client, db_session):
    """Twelve seconds of video is a sample, not a measurement of an interview."""
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)

    resp = client.post(
        _url(session.id),
        json=_body(analysedSeconds=12.0, faceDetectedSeconds=12.0),
        headers=_headers(token),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["eyeContactPercentage"] is None
    assert data["smileFrequencyScore"] is None
    assert data["postureFlagCount"] is None


def test_a_face_visible_too_rarely_is_discarded(client, db_session):
    """
    Ten percent coverage does not distinguish a candidate sitting out of frame
    from a covered lens or a dark room. Reporting a number either way would be
    inventing a measurement, so nothing is reported.
    """
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)

    resp = client.post(
        _url(session.id),
        json=_body(analysedSeconds=600.0, faceDetectedSeconds=60.0),
        headers=_headers(token),
    )
    assert resp.json()["data"]["eyeContactPercentage"] is None


def test_impossible_coverage_is_refused(client, db_session):
    """More face time than analysed time cannot happen, so nothing is believed."""
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)

    resp = client.post(
        _url(session.id),
        json=_body(analysedSeconds=100.0, faceDetectedSeconds=900.0),
        headers=_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["eyeContactPercentage"] is None


def test_a_session_that_stops_being_measurable_loses_its_earlier_scores(client, db_session):
    """
    The candidate covers the camera halfway through, dragging coverage under the
    floor. The row must not keep the scores from when it was still measurable —
    they describe the first half of an interview, not the interview.
    """
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)

    client.post(_url(session.id), json=_body(), headers=_headers(token))
    assert client.get(_url(session.id), headers=_headers(token)).json()["data"]["eyeContactPercentage"] is not None

    client.post(
        _url(session.id),
        json=_body(analysedSeconds=1200.0, faceDetectedSeconds=100.0),
        headers=_headers(token),
    )
    stale = client.get(_url(session.id), headers=_headers(token)).json()["data"]
    assert stale["eyeContactPercentage"] is None
    assert stale["smileFrequencyScore"] is None
    assert stale["postureFlagCount"] is None


# --- Authorization ---


def test_expression_is_refused_while_the_interview_is_running(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_session(db_session, user, status=SessionStatus.IN_PROGRESS)

    resp = client.post(_url(session.id), json=_body(), headers=_headers(token))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "interview_in_progress"


def test_another_user_cannot_write_or_read_expression(client, db_session):
    """
    Section 12.2, and it matters more here than anywhere else in the API: this
    row is derived from someone's face.
    """
    owner_token = _signup_and_login(client, "owner3@example.com")
    owner = _user_by_email(db_session, "owner3@example.com")
    session = make_scored_session(db_session, owner)
    client.post(_url(session.id), json=_body(), headers=_headers(owner_token))

    intruder = _signup_and_login(client, "intruder3@example.com")
    assert client.post(_url(session.id), json=_body(), headers=_headers(intruder)).status_code == 404
    assert client.get(_url(session.id), headers=_headers(intruder)).status_code == 404


def test_expression_requires_authentication(client, db_session):
    _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)
    assert client.post(_url(session.id), json=_body()).status_code == 401


def test_missing_expression_reads_as_404_with_its_own_code(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)

    resp = client.get(_url(session.id), headers=_headers(token))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "expression_not_recorded"


# --- The handoff into Phase 4's scoring ---


def test_recording_expression_turns_on_the_body_language_score(client, db_session):
    """
    The point of Phase 5B: `body_language` becomes a real score with no change to
    Phase 4's scoring code, and the weighted formula stops renormalising it away.
    """
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)

    before = compute_breakdown(db_session, session.id)
    assert before.body_language_score is None
    assert "body_language" in before.unmeasured_categories

    client.post(_url(session.id), json=_body(), headers=_headers(token))

    db_session.expire_all()
    after = compute_breakdown(db_session, session.id)
    assert after.body_language_score is not None
    assert "body_language" in after.measured_categories


def test_an_unmeasurable_session_leaves_body_language_absent(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)

    client.post(
        _url(session.id),
        json=_body(analysedSeconds=8.0, faceDetectedSeconds=8.0),
        headers=_headers(token),
    )

    db_session.expire_all()
    breakdown = compute_breakdown(db_session, session.id)
    # A row exists but holds no usable scores, so the category must stay NULL
    # rather than being scored off an empty row.
    assert breakdown.body_language_score is None
    assert "body_language" in breakdown.unmeasured_categories


def test_all_four_categories_measured_uses_the_spec_weights_unchanged(client, db_session):
    """
    With prosody and expression both recorded, Section 10.2's formula runs at its
    full four categories and needs no renormalisation at all — the first time in
    this project's history that has been true.
    """
    from app.services.feedback.scoring import DEFAULT_CATEGORY_WEIGHTS

    token = _signup_and_login(client)
    user = _user_by_email(db_session, "expression@example.com")
    session = make_scored_session(db_session, user)

    client.post(
        f"/api/v1/interviews/{session.id}/signals/prosody",
        json={"pitchVarianceScore": 66.0, "avgPauseDurationMs": 420.0, "voicedSeconds": 300.0},
        headers=_headers(token),
    )
    client.post(_url(session.id), json=_body(), headers=_headers(token))

    db_session.expire_all()
    breakdown = compute_breakdown(db_session, session.id)
    assert breakdown.unmeasured_categories == []
    assert sorted(breakdown.measured_categories) == [
        "body_language",
        "communication",
        "confidence",
        "content",
    ]
    for category, weight in DEFAULT_CATEGORY_WEIGHTS.items():
        assert breakdown.effective_weights[category] == pytest.approx(weight)


# --- The PDF note that explains blank scores ---


@pytest.mark.parametrize(
    "scores,expect_present,expect_absent",
    [
        # Phase 4's state: both media categories missing.
        ((80.0, 70.0, None, None), ["Confidence and body language need", "they are left blank"], []),
        # Camera off, microphone fine. The old fixed sentence claimed confidence
        # was unmeasured here too, with a real confidence score printed above it.
        ((80.0, 70.0, 75.0, None), ["Body language needs video analysis", "it is left blank"], ["confidence and"]),
        # Microphone muted, camera fine.
        ((80.0, 70.0, None, 68.0), ["Confidence needs voice-tone analysis"], ["body language needs"]),
    ],
)
def test_the_pdf_note_names_only_what_was_actually_missing(scores, expect_present, expect_absent):
    from app.services.feedback.exports import unmeasured_note

    class Report:
        content_score, communication_score, confidence_score, body_language_score = scores

    note = unmeasured_note(Report())
    assert note is not None
    for fragment in expect_present:
        assert fragment in note, f"{fragment!r} missing from {note!r}"
    for fragment in expect_absent:
        assert fragment not in note, f"{fragment!r} should not be in {note!r}"


def test_the_pdf_prints_no_note_when_everything_was_measured():
    """Phase 5's normal case. There is nothing to explain, so nothing is said."""
    from app.services.feedback.exports import unmeasured_note

    class Report:
        content_score = 80.0
        communication_score = 70.0
        confidence_score = 75.0
        body_language_score = 68.0

    assert unmeasured_note(Report()) is None
