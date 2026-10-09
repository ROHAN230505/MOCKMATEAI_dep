"""
Voice Prosody Service tests (Section 9.7, Phase 5).

The rules worth protecting here are the trust rules. Two of the four prosody
signals are measured in the browser and posted by the client, which makes them
the only numbers in the scoring pipeline that originate outside the server. If
they were taken at face value, a crafted request could award itself a perfect
confidence score.
"""
import pytest

from app.models.enums import SessionStatus
from app.models.signals import ProsodySignal
from app.models.user import User
from app.services.feedback.scoring import compute_breakdown
from tests.feedback_factories import STRONG_ANSWER, add_turn, make_scored_session, make_session

PASSWORD = "Str0ng!Pass"


def _signup_and_login(client, email="prosody@example.com"):
    client.post("/api/v1/auth/signup", json={"name": "Ada", "email": email, "password": PASSWORD})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return resp.json()["data"]["accessToken"]


def _headers(token):
    return {"Authorization": "Bearer " + token}


def _user_by_email(db, email):
    return db.query(User).filter(User.email == email).one()


def _url(session_id):
    return "/api/v1/interviews/" + str(session_id) + "/signals/prosody"


def _body(**overrides):
    body = {"pitchVarianceScore": 68.0, "avgPauseDurationMs": 420.0, "voicedSeconds": 95.0}
    body.update(overrides)
    return body


# --- Submission ---


def test_prosody_is_recorded_and_readable(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "prosody@example.com")
    session = make_scored_session(db_session, user)

    resp = client.post(_url(session.id), json=_body(), headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["pitchVarianceScore"] == pytest.approx(68.0)
    assert data["avgPauseDurationMs"] == pytest.approx(420.0)

    read = client.get(_url(session.id), headers=_headers(token))
    assert read.status_code == 200
    assert read.json()["data"]["pitchVarianceScore"] == pytest.approx(68.0)


def test_filler_count_is_derived_server_side_not_accepted_from_the_client(client, db_session):
    """
    Section 9.7 scopes filler words to transcript pattern matching, and the
    server already does that. The client cannot supply the number, so the count
    in `prosody_signals` and the one in the feedback report are the same figure
    by construction rather than by agreement.
    """
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "prosody@example.com")
    session = make_session(db_session, user)
    add_turn(
        db_session, session, 1, "Q1",
        "Um, I basically, you know, did the thing.",
        relevance=5, completeness=5,
    )

    # Even if a client invents these keys they are not in the schema and are
    # ignored -- the response carries the server's own figures.
    resp = client.post(
        _url(session.id),
        json=_body(fillerWordCount=0, avgPaceWpm=999),
        headers=_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["fillerWordCount"] == 3  # um, basically, you know
    # No timings were supplied, so there is genuinely no pace to report.
    assert resp.json()["data"]["avgPaceWpm"] is None


def test_pace_is_measured_once_the_client_supplies_real_timings(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "prosody@example.com")
    session = make_session(db_session, user)
    add_turn(
        db_session, session, 1, "Q1", STRONG_ANSWER,
        relevance=9, completeness=9, started_at=0.0, ended_at=30.0,
    )

    resp = client.post(_url(session.id), json=_body(), headers=_headers(token))
    pace = resp.json()["data"]["avgPaceWpm"]
    assert pace is not None
    assert pace > 0


def test_resubmission_upserts_rather_than_duplicating(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "prosody@example.com")
    session = make_scored_session(db_session, user)

    client.post(_url(session.id), json=_body(pitchVarianceScore=40.0), headers=_headers(token))
    client.post(_url(session.id), json=_body(pitchVarianceScore=75.0), headers=_headers(token))

    rows = db_session.query(ProsodySignal).filter(ProsodySignal.session_id == session.id).all()
    assert len(rows) == 1
    db_session.refresh(rows[0])
    assert rows[0].pitch_variance_score == pytest.approx(75.0)


# --- Trust boundary ---


@pytest.mark.parametrize(
    "field,value",
    [
        ("pitchVarianceScore", 101),
        ("pitchVarianceScore", -1),
        ("avgPauseDurationMs", -5),
        ("avgPauseDurationMs", 90000),
        ("voicedSeconds", -1),
    ],
)
def test_out_of_range_values_are_rejected(client, db_session, field, value):
    """Client-supplied numbers are bounded at the schema, per Section 12.8's posture."""
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "prosody@example.com")
    session = make_scored_session(db_session, user)

    resp = client.post(_url(session.id), json=_body(**{field: value}), headers=_headers(token))
    assert resp.status_code == 422


def test_too_little_voiced_audio_is_discarded_not_stored(client, db_session):
    """
    A pitch figure from three seconds of speech is not a measurement. It is
    dropped to NULL rather than persisted, so the confidence score stays absent
    instead of resting on noise.
    """
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "prosody@example.com")
    session = make_scored_session(db_session, user)

    resp = client.post(_url(session.id), json=_body(voicedSeconds=3.0), headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["pitchVarianceScore"] is None
    assert data["avgPauseDurationMs"] is None
    # The transcript-derived half is still recorded -- it never depended on audio.
    assert data["fillerWordCount"] is not None


def test_prosody_is_refused_while_the_interview_is_running(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "prosody@example.com")
    session = make_session(db_session, user, status=SessionStatus.IN_PROGRESS)

    resp = client.post(_url(session.id), json=_body(), headers=_headers(token))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "interview_in_progress"


def test_another_user_cannot_write_or_read_prosody(client, db_session):
    owner_token = _signup_and_login(client, "owner2@example.com")
    owner = _user_by_email(db_session, "owner2@example.com")
    session = make_scored_session(db_session, owner)
    client.post(_url(session.id), json=_body(), headers=_headers(owner_token))

    intruder = _signup_and_login(client, "intruder2@example.com")
    assert client.post(_url(session.id), json=_body(), headers=_headers(intruder)).status_code == 404
    assert client.get(_url(session.id), headers=_headers(intruder)).status_code == 404


def test_prosody_requires_authentication(client, db_session):
    _signup_and_login(client)
    user = _user_by_email(db_session, "prosody@example.com")
    session = make_scored_session(db_session, user)
    assert client.post(_url(session.id), json=_body()).status_code == 401


def test_missing_prosody_reads_as_404_with_its_own_code(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "prosody@example.com")
    session = make_scored_session(db_session, user)

    resp = client.get(_url(session.id), headers=_headers(token))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "prosody_not_recorded"


# --- The Phase 4 -> Phase 5 handoff ---


def test_recording_prosody_turns_on_the_confidence_score(client, db_session):
    """
    The point of Phase 5A: once a prosody row exists, Phase 4's scoring starts
    reporting `confidence_score` with no change to the scoring code, and the
    weighted formula stops renormalising that category away.
    """
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "prosody@example.com")
    session = make_scored_session(db_session, user)

    before = compute_breakdown(db_session, session.id)
    assert before.confidence_score is None
    assert "confidence" in before.unmeasured_categories

    client.post(_url(session.id), json=_body(), headers=_headers(token))

    db_session.expire_all()
    after = compute_breakdown(db_session, session.id)
    assert after.confidence_score is not None
    assert "confidence" not in after.unmeasured_categories
    # Body language still is not measured -- that is Phase 5B, and it stays absent.
    assert "body_language" in after.unmeasured_categories


def test_a_discarded_short_sample_leaves_confidence_unmeasured(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "prosody@example.com")
    session = make_scored_session(db_session, user)

    client.post(_url(session.id), json=_body(voicedSeconds=2.0), headers=_headers(token))

    db_session.expire_all()
    breakdown = compute_breakdown(db_session, session.id)
    # A row exists, but with no usable audio figures -- so confidence must stay
    # NULL rather than being scored off an empty row.
    assert breakdown.confidence_score is None
    assert "confidence" in breakdown.unmeasured_categories


def test_prosody_pace_backfills_communication_when_the_transcript_had_no_timings(client, db_session):
    """
    `compute_breakdown` prefers the prosody row's pace when the transcript has
    none. Here the transcript has no timings either, so pace stays absent and
    the communication score must be reached without it -- not with a zero.
    """
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "prosody@example.com")
    session = make_scored_session(db_session, user)

    client.post(_url(session.id), json=_body(), headers=_headers(token))

    db_session.expire_all()
    breakdown = compute_breakdown(db_session, session.id)
    assert breakdown.communication_score is not None
    assert "communication" in breakdown.measured_categories
