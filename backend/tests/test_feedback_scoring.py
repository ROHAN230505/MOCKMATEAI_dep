"""
Deterministic scoring tests (Section 10.2, Section 9.7, Section 9.8).

These are the tests that matter most in Phase 4: the scores are what a candidate
will act on, and every rule below encodes a decision that would be invisible if
it silently regressed — a skip counted as a zero, an unmeasured category
defaulted to 50, or a weight change that never took effect.
"""
import uuid

import pytest

from app.models.scoring import ScoringWeights
from app.models.signals import ExpressionSignal, ProsodySignal
from app.services.feedback.scoring import (
    DEFAULT_CATEGORY_WEIGHTS,
    CategoryWeights,
    aggregate_content_score,
    compute_breakdown,
    load_category_weights,
    load_index_weights,
    load_turns,
    readiness_label,
    weighted_overall,
)
from app.services.feedback.transcript_signals import communication_score, extract_signals
from tests.feedback_factories import STRONG_ANSWER, WEAK_ANSWER, add_turn, make_session, make_user


def _make_user(db, email="scorer@example.com"):
    return make_user(db, email=email)


def _make_session(db, user, role="Backend Engineer"):
    return make_session(db, user, role=role)


def _add_turn(db, session, order, question, answer, **kwargs):
    return add_turn(db, session, order, question, answer, **kwargs)


# ---------------------------------------------------------------------------
# Section 9.7 — transcript signals
# ---------------------------------------------------------------------------
def test_filler_words_are_counted_as_whole_words():
    signals = extract_signals([{"text": "Um, I basically unlike, you know, liked it.", "is_skipped": False}])
    # "um", "basically", "you know" match; "unlike" and "liked" must NOT match
    # the \blike\b pattern.
    assert signals.filler_count == 3


def test_skipped_answers_contribute_no_signals():
    signals = extract_signals(
        [
            {"text": "I'll pass on this one.", "is_skipped": True},
            {"text": STRONG_ANSWER, "is_skipped": False},
        ]
    )
    assert signals.answer_count == 1


def test_clean_structured_answer_scores_above_filler_heavy_answer():
    strong = communication_score(extract_signals([{"text": STRONG_ANSWER, "is_skipped": False}]))
    weak = communication_score(extract_signals([{"text": WEAK_ANSWER, "is_skipped": False}]))
    assert strong is not None and weak is not None
    assert strong > weak


def test_communication_score_is_none_without_answers():
    assert communication_score(extract_signals([])) is None


def test_pace_is_only_computed_when_timings_exist():
    untimed = extract_signals([{"text": STRONG_ANSWER, "is_skipped": False}])
    assert untimed.speaking_pace_wpm is None

    timed = extract_signals(
        [{"text": STRONG_ANSWER, "is_skipped": False, "started_at": 0.0, "ended_at": 30.0}]
    )
    assert timed.speaking_pace_wpm is not None
    assert timed.speaking_pace_wpm > 0


# ---------------------------------------------------------------------------
# Section 9.8 — skip-aware aggregation
# ---------------------------------------------------------------------------
def test_skipped_questions_are_excluded_not_zeroed(db_session):
    user = _make_user(db_session)
    session = _make_session(db_session, user)
    _add_turn(db_session, session, 1, "Q1", STRONG_ANSWER, relevance=9, completeness=9)
    _add_turn(db_session, session, 2, "Q2", None, skipped=True)

    turns = load_turns(db_session, session.id)
    score, answered, skipped, scored = aggregate_content_score(turns)

    assert answered == 1
    assert skipped == 1
    assert scored == 1
    # Averaging the skip in as a zero would give 45.
    assert score == pytest.approx(90.0)


def test_all_skipped_yields_no_content_score(db_session):
    user = _make_user(db_session)
    session = _make_session(db_session, user)
    _add_turn(db_session, session, 1, "Q1", None, skipped=True)
    _add_turn(db_session, session, 2, "Q2", None, skipped=True)

    score, answered, skipped, scored = aggregate_content_score(load_turns(db_session, session.id))
    assert score is None
    assert answered == 0
    assert skipped == 2
    assert scored == 0


def test_unanswered_question_is_not_counted_either_way(db_session):
    user = _make_user(db_session)
    session = _make_session(db_session, user)
    _add_turn(db_session, session, 1, "Q1", STRONG_ANSWER, relevance=8, completeness=8)
    _add_turn(db_session, session, 2, "Q2", None)  # asked, never answered

    turns = load_turns(db_session, session.id)
    score, answered, skipped, scored = aggregate_content_score(turns)
    assert len(turns) == 2
    assert answered == 1
    assert skipped == 0
    assert score == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# Section 10.2 — weights and renormalization
# ---------------------------------------------------------------------------
def test_weights_come_from_the_config_table(db_session):
    db_session.add(
        ScoringWeights(
            id=uuid.uuid4(),
            is_active=True,
            note="test override",
            content_weight=0.70,
            communication_weight=0.30,
            confidence_weight=0.0,
            body_language_weight=0.0,
            index_mock_interview_weight=0.5,
            index_aptitude_weight=0.2,
            index_dsa_weight=0.2,
            index_resume_weight=0.1,
        )
    )
    db_session.commit()

    weights = load_category_weights(db_session)
    assert weights.source == "config_table"
    assert weights.content == pytest.approx(0.70)
    assert load_index_weights(db_session)["mock_interview_avg"] == pytest.approx(0.5)


def test_weights_fall_back_to_published_defaults_when_table_is_empty(db_session):
    weights = load_category_weights(db_session)
    assert weights.source == "defaults"
    assert weights.content == pytest.approx(DEFAULT_CATEGORY_WEIGHTS["content"])
    assert load_index_weights(db_session)["dsa_progress_pct"] == pytest.approx(0.25)


def test_full_formula_matches_section_10_2_when_everything_is_measured():
    weights = CategoryWeights(**DEFAULT_CATEGORY_WEIGHTS, source="defaults")
    scores = {"content": 80.0, "communication": 60.0, "confidence": 40.0, "body_language": 20.0}
    overall, measured, unmeasured, effective = weighted_overall(scores, weights)

    expected = 80 * 0.40 + 60 * 0.25 + 40 * 0.20 + 20 * 0.15
    assert overall == pytest.approx(expected)
    assert unmeasured == []
    assert effective["content"] == pytest.approx(0.40)


def test_unmeasured_categories_are_renormalized_not_defaulted():
    weights = CategoryWeights(**DEFAULT_CATEGORY_WEIGHTS, source="defaults")
    scores = {"content": 80.0, "communication": 60.0, "confidence": None, "body_language": None}
    overall, measured, unmeasured, effective = weighted_overall(scores, weights)

    # 0.40/0.25 renormalized over 0.65 => ~0.6154 / ~0.3846.
    assert set(unmeasured) == {"confidence", "body_language"}
    assert effective["content"] == pytest.approx(0.6154, abs=1e-3)
    assert overall == pytest.approx(80 * 0.6154 + 60 * 0.3846, abs=0.2)
    # Substituting a neutral 50 for the missing halves would give 63.0 — well
    # below a renormalized score that only reflects what was actually measured.
    assert overall > 70


def test_no_measured_category_yields_no_overall():
    weights = CategoryWeights(**DEFAULT_CATEGORY_WEIGHTS, source="defaults")
    overall, measured, unmeasured, effective = weighted_overall(
        {"content": None, "communication": None, "confidence": None, "body_language": None}, weights
    )
    assert overall is None
    assert measured == []
    assert effective == {}


def test_breakdown_leaves_phase5_categories_null(db_session):
    user = _make_user(db_session)
    session = _make_session(db_session, user)
    _add_turn(db_session, session, 1, "Q1", STRONG_ANSWER, relevance=8, completeness=7)

    breakdown = compute_breakdown(db_session, session.id)
    assert breakdown.content_score is not None
    assert breakdown.communication_score is not None
    assert breakdown.confidence_score is None
    assert breakdown.body_language_score is None
    assert set(breakdown.unmeasured_categories) == {"confidence", "body_language"}
    assert breakdown.overall_readiness_score is not None


def test_phase5_signal_rows_are_picked_up_without_code_changes(db_session):
    """
    The forward-compatibility contract: once Phase 5 writes `prosody_signals` /
    `expression_signals`, the same formula must start scoring those categories
    with no change to the scoring code.
    """
    user = _make_user(db_session)
    session = _make_session(db_session, user)
    _add_turn(db_session, session, 1, "Q1", STRONG_ANSWER, relevance=8, completeness=7)
    db_session.add(
        ProsodySignal(
            id=uuid.uuid4(),
            session_id=session.id,
            avg_pace_wpm=135.0,
            filler_word_count=2,
            pitch_variance_score=72.0,
            avg_pause_duration_ms=420.0,
        )
    )
    db_session.add(
        ExpressionSignal(
            id=uuid.uuid4(),
            session_id=session.id,
            eye_contact_percentage=68.0,
            smile_frequency_score=55.0,
            posture_flag_count=1,
        )
    )
    db_session.commit()

    breakdown = compute_breakdown(db_session, session.id)
    assert breakdown.confidence_score is not None
    assert breakdown.body_language_score is not None
    assert breakdown.unmeasured_categories == []
    assert breakdown.effective_weights["content"] == pytest.approx(0.40)


def test_readiness_labels_match_section_10_2_bands():
    assert readiness_label(None) == "Not enough data yet"
    assert readiness_label(12.0) == "Just Getting Started"
    assert readiness_label(34.0) == "Building Foundations"
    assert readiness_label(67.0) == "Interview Ready"


# ---------------------------------------------------------------------------
# A question that was planned but never asked is not part of the interview
# ---------------------------------------------------------------------------
def test_questions_never_asked_are_absent_from_the_transcript(db_session):
    """
    The session's planned questions are written up front, and the interviewer
    routinely does not reach them all -- it runs out of time, or spends turns
    on follow-ups instead. Those rows used to surface in the report as
    questions with "No answer recorded", which tells the candidate they failed
    to answer something that was never put to them.
    """
    user = _make_user(db_session)
    session = _make_session(db_session, user)
    _add_turn(db_session, session, 1, "Asked and answered", STRONG_ANSWER, relevance=8, completeness=8)
    _add_turn(db_session, session, 2, "Asked, ran out of time", None)
    _add_turn(db_session, session, 3, "Planned, never reached", None, asked=False)

    texts = [t.question_text for t in load_turns(db_session, session.id)]

    assert "Planned, never reached" not in texts
    # Asked-but-unanswered still belongs: that one really did happen.
    assert texts == ["Asked and answered", "Asked, ran out of time"]


def test_an_unasked_question_does_not_inflate_the_question_count(db_session):
    """It was counted in `question_count`, so the report overstated the interview."""
    user = _make_user(db_session)
    session = _make_session(db_session, user)
    _add_turn(db_session, session, 1, "Q1", STRONG_ANSWER, relevance=7, completeness=7)
    _add_turn(db_session, session, 2, "Never reached", None, asked=False)
    _add_turn(db_session, session, 3, "Also never reached", None, asked=False)

    assert len(load_turns(db_session, session.id)) == 1
