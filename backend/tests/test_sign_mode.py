"""
Sign-language mode (Phase 6).

The spec's promise, quoted on the landing page, is "the same engine, the same
rubric and the same feedback pipeline as voice. Not a reduced version of the
product — the product." Applying that literally is the trap: a rubric that
counts "um" and words-per-minute cannot be pointed at a signed answer unchanged.
It would hand every signing candidate a +12 bonus for the absence of English
filler words they were never assessed on, and judge them against a spoken pace
band that is not a unit of their language.

So "the same rubric" is honoured by scoring the same four categories against the
same evidence, and by dropping only the terms that measure *how words sounded*.
Most of this file exists to pin that distinction, and to prove the refactor that
made it possible did not move a single voice score.
"""
import pytest

from app.models.enums import InterviewMode, SessionStatus
from app.models.user import User
from app.services.feedback.scoring import compute_breakdown
from app.services.feedback.transcript_signals import (
    COMMUNICATION_BASELINE,
    FILLER_RATE_CLEAN,
    FILLER_RATE_HEAVY,
    FILLER_RATE_NOTICEABLE,
    TranscriptSignals,
    applicable_components,
    communication_score,
    extract_signals,
    renormalisation_factor,
)
from tests.feedback_factories import STRONG_ANSWER, add_turn, make_session

PASSWORD = "Str0ng!Pass"


def _signup_and_login(client, email="signer@example.com"):
    client.post("/api/v1/auth/signup", json={"name": "Ada", "email": email, "password": PASSWORD})
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["data"]["accessToken"]


def _headers(token):
    return {"Authorization": "Bearer " + token}


def _user_by_email(db, email):
    return db.query(User).filter(User.email == email).one()


# ---------------------------------------------------------------------------
# The refactor must not have moved any voice score
# ---------------------------------------------------------------------------
def _voice_score_oracle(signals: TranscriptSignals) -> float | None:
    """
    The pre-Phase-6 formula, written out again from scratch.

    An independent oracle rather than a golden number: if the component tables
    and the renormalisation are wrong in a way that happens to cancel out, a
    hardcoded expected value would not catch it, but two implementations
    disagreeing will.
    """
    if signals.answer_count == 0 or signals.total_words == 0:
        return None

    score = 65.0

    rate = signals.filler_rate_per_100_words
    if rate <= FILLER_RATE_CLEAN:
        score += 12
    elif rate <= FILLER_RATE_NOTICEABLE:
        score += 4
    elif rate <= FILLER_RATE_HEAVY:
        score -= 8
    else:
        score -= 18

    score -= (signals.under_elaborated_answers / signals.answer_count) * 20
    score += (signals.well_developed_answers / signals.answer_count) * 10

    markers = signals.structure_markers_per_answer
    if markers >= 2.0:
        score += 12
    elif markers >= 1.0:
        score += 6
    elif markers < 0.4:
        score -= 8

    score += (signals.quantified_answers / signals.answer_count) * 8

    if signals.speaking_pace_wpm is not None:
        pace = signals.speaking_pace_wpm
        if 110 <= pace <= 160:
            score += 5
        elif pace < 80 or pace > 200:
            score -= 8

    return max(0.0, min(100.0, round(score, 1)))


ANSWER_FIXTURES = [
    STRONG_ANSWER,
    "Um, I guess I would, like, probably just try some stuff and see.",
    "I refactored the payment retry logic and added idempotency keys.",
    "The situation was a flaky test suite. What I did was quarantine the worst "
    "offenders and fix the shared fixture underneath them. As a result the suite "
    "went from failing one run in three to passing forty consecutive runs, and the "
    "team stopped re-running builds by reflex.",
    "Basically, um, you know, sort of like, I actually kind of just did the thing, I mean.",
]


@pytest.mark.parametrize("text", ANSWER_FIXTURES)
@pytest.mark.parametrize("pace", [None, 60.0, 130.0, 240.0])
def test_voice_scores_are_unchanged_by_the_phase_6_refactor(text, pace):
    signals = extract_signals([{"text": text, "is_skipped": False}])
    signals.speaking_pace_wpm = pace

    assert communication_score(signals, modality=InterviewMode.VOICE) == _voice_score_oracle(signals)
    # And the default argument still means voice, so every existing call site is
    # scoring exactly what it scored before.
    assert communication_score(signals) == _voice_score_oracle(signals)


def test_voice_renormalisation_is_exactly_one():
    """
    Not approximately. If this drifts off 1.0 by any amount, every voice
    communication score in the product silently shifts.
    """
    assert renormalisation_factor(InterviewMode.VOICE) == 1.0
    assert len(applicable_components(InterviewMode.VOICE)) == 5


# ---------------------------------------------------------------------------
# What the signed rubric does and does not count
# ---------------------------------------------------------------------------
def _signals(**overrides) -> TranscriptSignals:
    base = {
        "total_words": 50,
        "answer_count": 1,
        "filler_count": 0,
        "structure_marker_count": 1,
        "under_elaborated_answers": 0,
        "well_developed_answers": 0,
        "quantified_answers": 0,
        "speaking_pace_wpm": None,
    }
    base.update(overrides)
    return TranscriptSignals(**base)


def test_filler_words_move_a_voice_score_and_are_ignored_in_sign_mode():
    """
    The bug this phase existed to avoid. An English filler regex finds nothing in
    a signed answer, so under the old formula every signing candidate collected
    the full "clean speech" bonus for fluency nobody had assessed.
    """
    clean = _signals(filler_count=0)
    heavy = _signals(filler_count=10)  # 20 per 100 words, well past FILLER_RATE_HEAVY

    voice_clean = communication_score(clean, modality=InterviewMode.VOICE)
    voice_heavy = communication_score(heavy, modality=InterviewMode.VOICE)
    assert voice_clean > voice_heavy, "fillers must still matter when someone spoke"

    sign_clean = communication_score(clean, modality=InterviewMode.SIGN)
    sign_heavy = communication_score(heavy, modality=InterviewMode.SIGN)
    assert sign_clean == sign_heavy, "filler count must not influence a signed score at all"


def test_speaking_pace_moves_a_voice_score_and_is_ignored_in_sign_mode():
    """Words per minute is not a signing rate, so it is not a term of the score."""
    comfortable = _signals(speaking_pace_wpm=130.0)
    racing = _signals(speaking_pace_wpm=240.0)

    assert communication_score(comfortable, modality=InterviewMode.VOICE) > communication_score(
        racing, modality=InterviewMode.VOICE
    )
    assert communication_score(comfortable, modality=InterviewMode.SIGN) == communication_score(
        racing, modality=InterviewMode.SIGN
    )


@pytest.mark.parametrize(
    "better,worse",
    [
        ({"structure_marker_count": 3}, {"structure_marker_count": 0}),
        ({"well_developed_answers": 1}, {"under_elaborated_answers": 1}),
        ({"quantified_answers": 1}, {"quantified_answers": 0}),
    ],
)
def test_the_terms_that_survive_still_carry_the_signed_score(better, worse):
    """
    Dropping two terms must not flatten the score into a constant. What a
    candidate actually said — structured, developed, specific — is still what
    moves it, in both modalities.
    """
    assert communication_score(_signals(**better), modality=InterviewMode.SIGN) > communication_score(
        _signals(**worse), modality=InterviewMode.SIGN
    )


def test_a_signed_score_still_spans_the_full_range():
    """
    The reason the surviving terms are scaled up. Without renormalisation a
    flawless signed session would cap around 95 and a poor one floor near 37, so
    "72 out of 100" would quietly mean something different depending on how the
    candidate answered.
    """
    excellent = _signals(
        structure_marker_count=3, well_developed_answers=1, quantified_answers=1
    )
    poor = _signals(structure_marker_count=0, under_elaborated_answers=1)

    assert communication_score(excellent, modality=InterviewMode.SIGN) == 100.0
    assert communication_score(poor, modality=InterviewMode.SIGN) < 30.0


def test_a_signed_session_with_no_answers_scores_nothing():
    """The absence rule is modality-independent: nothing measured, nothing reported."""
    assert communication_score(extract_signals([]), modality=InterviewMode.SIGN) is None


def test_the_baseline_is_shared_so_an_average_session_lands_in_the_same_place():
    """
    A candidate who is neither good nor bad on the surviving terms sits at the
    same neutral point in both modalities, which is what makes the two scores
    comparable at all.
    """
    neutral = _signals(structure_marker_count=1)  # 1.0 markers/answer scores +6 in both
    voice = communication_score(neutral, modality=InterviewMode.VOICE)
    sign = communication_score(neutral, modality=InterviewMode.SIGN)
    assert abs(voice - COMMUNICATION_BASELINE) < 20
    assert abs(sign - COMMUNICATION_BASELINE) < 20


# ---------------------------------------------------------------------------
# End to end through the real pipeline
# ---------------------------------------------------------------------------
def _sign_session(db, user):
    session = make_session(db, user)
    session.mode = InterviewMode.SIGN
    db.commit()
    return session


def test_compute_breakdown_scores_a_signed_session_with_the_signed_rubric(client, db_session):
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "signer@example.com")

    voice = make_session(db_session, user)
    add_turn(db_session, voice, 1, "Q", STRONG_ANSWER, relevance=8, completeness=8)

    signed = _sign_session(db_session, user)
    add_turn(db_session, signed, 1, "Q", STRONG_ANSWER, relevance=8, completeness=8)

    voice_breakdown = compute_breakdown(db_session, voice.id)
    signed_breakdown = compute_breakdown(db_session, signed.id)

    # Same answer, same content score — the modality changes nothing about what
    # was said, only about which delivery signals exist.
    assert voice_breakdown.content_score == signed_breakdown.content_score
    assert signed_breakdown.communication_score is not None
    assert "communication" in signed_breakdown.measured_categories
    assert token  # the fixture is what created the user


def test_confidence_is_unmeasured_for_a_signed_session(client, db_session):
    """
    There is no audio track, so there is no prosody row, so confidence stays
    NULL and its weight is redistributed. Nothing new is needed for this to
    work — it is the Phase 4 renormalisation doing its job.
    """
    _signup_and_login(client)
    user = _user_by_email(db_session, "signer@example.com")
    signed = _sign_session(db_session, user)
    add_turn(db_session, signed, 1, "Q", STRONG_ANSWER, relevance=8, completeness=8)

    breakdown = compute_breakdown(db_session, signed.id)
    assert breakdown.confidence_score is None
    assert "confidence" in breakdown.unmeasured_categories


def test_body_language_is_still_measurable_in_sign_mode(client, db_session):
    """
    The camera is on in a signed interview, and body language matters more there
    rather than less. Expression signals are recorded exactly as in voice mode.
    """
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "signer@example.com")
    signed = _sign_session(db_session, user)
    signed.status = SessionStatus.COMPLETED
    db_session.commit()
    add_turn(db_session, signed, 1, "Q", STRONG_ANSWER, relevance=8, completeness=8)

    resp = client.post(
        f"/api/v1/interviews/{signed.id}/signals/expression",
        json={
            "eyeContactPercentage": 81.0,
            "smileFrequencyScore": 44.0,
            "postureFlagCount": 1,
            "analysedSeconds": 500.0,
            "faceDetectedSeconds": 470.0,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 200

    db_session.expire_all()
    breakdown = compute_breakdown(db_session, signed.id)
    assert breakdown.body_language_score is not None
    assert "body_language" in breakdown.measured_categories
    # Three of four measured: content, communication, body language.
    assert breakdown.unmeasured_categories == ["confidence"]
    assert abs(sum(breakdown.effective_weights.values()) - 1.0) < 1e-6


def test_prosody_submission_is_refused_for_a_signed_session(client, db_session):
    """A signed interview has no audio, so a prosody row would describe nothing."""
    token = _signup_and_login(client)
    user = _user_by_email(db_session, "signer@example.com")
    signed = _sign_session(db_session, user)
    signed.status = SessionStatus.COMPLETED
    db_session.commit()

    resp = client.post(
        f"/api/v1/interviews/{signed.id}/signals/prosody",
        json={"pitchVarianceScore": 70.0, "avgPauseDurationMs": 400.0, "voicedSeconds": 300.0},
        headers=_headers(token),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "modality_has_no_audio"


def test_a_prosody_update_over_the_socket_is_dropped_for_a_signed_session(client, db_session):
    """
    Dropped quietly rather than fatally: a client sending this is confused, not
    hostile, and an interview must not end over it.
    """
    from app.services.prosody_service import get_prosody

    token = _signup_and_login(client)
    started = client.post(
        "/api/v1/interviews/start",
        json={
            "role": "SDE",
            "type": "behavioral",
            "durationMinutes": 15,
            "mode": "sign",
            "consentGiven": True,
        },
        headers=_headers(token),
    ).json()["data"]
    session_id = started["sessionId"]

    with client.websocket_connect(f"/api/v1/interviews/{session_id}/live?token={token}") as ws:
        for _ in range(25):
            event = ws.receive_json()
            if event.get("type") == "question_asked":
                break
        ws.send_json({
            "type": "prosody_update",
            "prosody": {"pitchVarianceScore": 90.0, "voicedSeconds": 300.0},
        })
        # The socket is still healthy afterwards.
        ws.send_json({"type": "end_requested"})
        for _ in range(25):
            if ws.receive_json().get("type") == "session_ended":
                break
        else:
            raise AssertionError("session_ended never arrived")

    assert get_prosody(db_session, session_id) is None


def test_the_report_note_calls_confidence_not_applicable_rather_than_missing():
    """
    Wording matters here. "Needs voice-tone analysis, which this session didn't
    record" invites a signing candidate to go and fix a fault that is not theirs
    and does not exist.
    """
    from app.services.feedback.exports import unmeasured_note

    class Report:
        content_score = 80.0
        communication_score = 70.0
        confidence_score = None
        body_language_score = 68.0

    signed = unmeasured_note(Report(), modality=InterviewMode.SIGN)
    assert "not scored in this format" in signed
    assert "by design" in signed
    assert "did not record" not in signed

    spoken = unmeasured_note(Report(), modality=InterviewMode.VOICE)
    assert "did not record" in spoken
    assert "by design" not in spoken
