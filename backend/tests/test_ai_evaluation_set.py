"""
The AI evaluation set (Section 15).

Section 15: "maintain a curated set of sample candidate answers
(strong/weak/vague) with expected follow-up-trigger outcomes, used to
regression-test the LLM prompt/guardrail logic (Section 10.3) whenever the
prompt is changed — this prevents silent quality regressions when you iterate
on prompts."

This is that curated set. It runs against the deterministic mock adapter, so
it pins the *guardrail* contract (Section 10.3's bands and cap) exactly. When
a real provider is configured, the same fixtures become the seed for a
provider-scoring harness: the expected outcome per answer stays valid, but the
assertion has to loosen from "always" to "in aggregate", because a live LLM's
scores are not reproducible turn to turn.

Adding an answer here is the intended workflow when a prompt change ships.
"""
import pytest

from app.services.ai.contracts import InternalEvaluation, TurnDecision, TurnDecisionResult
from app.services.ai.mock_adapter import detect_skip_intent, score_answer
from app.services.followup_guardrails import (
    DISALLOW_FOLLOWUP_AT_OR_ABOVE,
    MANDATORY_FOLLOWUP_BELOW,
    MAX_CONSECUTIVE_FOLLOWUPS,
    apply_guardrails,
)

# --------------------------------------------------------------------------
# The curated answer set. `expect_followup`:
#   True  -> must probe (weak/vague)
#   False -> must move on (strong)
# --------------------------------------------------------------------------
STRONG_ANSWERS = [
    (
        "star_with_metrics",
        "The situation was that our nightly Postgres reporting job took 40 minutes and kept timing "
        "out. My role was to own the fix. What I did was profile the query, add a composite index on "
        "the two columns we filtered on, and move the aggregation into a materialized view. As a "
        "result the job dropped to 90 seconds and we stopped paging on it.",
    ),
    (
        "technical_with_named_tech",
        "A hash map stores key-value pairs and gets O(1) average lookup by hashing the key to a bucket "
        "index. In Python that's a dict. The tradeoff is memory overhead and worst-case O(n) if every "
        "key collides, which is why the hash function matters. I used one to dedupe 50000 records "
        "instead of a nested loop, which took it from minutes to under a second.",
    ),
    (
        "conflict_with_outcome",
        "The challenge was that a teammate and I disagreed on whether to use REST or GraphQL for a new "
        "service. So I wrote up both options with the actual query patterns our frontend needed. The "
        "result was we found 3 of our 4 screens needed nested data, so we went with GraphQL, and he "
        "agreed once we looked at the real usage numbers.",
    ),
]

WEAK_OR_VAGUE_ANSWERS = [
    ("pure_vague_claim", "I'm a hard worker and a really good team player."),
    ("too_short", "I used Python."),
    ("no_specifics", "I've worked on lots of projects and they went pretty well overall."),
    ("generic_self_praise", "I'm very detail oriented and self motivated, I always try my best."),
    ("one_word", "Yes."),
]

SKIP_ANSWERS = [
    ("plain_dont_know", "I don't know."),
    ("skip_request", "Can we skip this one please?"),
    ("move_on", "Hmm, let's move on to the next question."),
    ("pass", "I'll pass on that one."),
    ("not_sure_next", "I'm not sure, next question?"),
    ("cannot_answer", "Sorry, I cannot answer that one."),
]

# Answers that must NOT be read as skips even though they contain
# near-miss wording. Section 9.3: "Do not infer skip intent from a merely
# short or hesitant answer — only from clear, explicit pass language."
NOT_SKIP_ANSWERS = [
    ("knows_it", "Oh, I know this one — it's a binary search tree."),
    ("hesitant_but_answers", "I'm not totally sure, but I think you'd use a hash map for that lookup."),
    ("mentions_knowing", "I don't know the exact syntax but the approach is to cache the result in Redis."),
    ("passing_reference", "We used a pass-through cache in front of the database."),
]


def _guardrail_for(answer_text: str, *, consecutive_followups: int = 0):
    """Runs the real scoring + guardrail path exactly as a live turn would."""
    if detect_skip_intent(answer_text):
        result = TurnDecisionResult(
            decision=TurnDecision.SKIP, utterance="No problem, let's move on.", internal_evaluation=None
        )
    else:
        relevance, completeness, reasoning = score_answer(answer_text)
        wants_followup = relevance < 6 or completeness < 6
        result = TurnDecisionResult(
            decision=TurnDecision.FOLLOWUP if wants_followup else TurnDecision.NEXT_QUESTION,
            utterance="...",
            internal_evaluation=InternalEvaluation(
                relevance_score=relevance, completeness_score=completeness, reasoning=reasoning
            ),
        )
    return result, apply_guardrails(result, consecutive_followups=consecutive_followups)


@pytest.mark.parametrize("label,answer", STRONG_ANSWERS, ids=[a[0] for a in STRONG_ANSWERS])
def test_strong_answers_move_on(label, answer):
    """A concrete, structured, outcome-bearing answer must not be over-probed (Section 10.3's pacing rule)."""
    result, outcome = _guardrail_for(answer)
    assert outcome.decision == TurnDecision.NEXT_QUESTION, (
        f"{label}: expected to advance, got {outcome.decision} ({outcome.reason})"
    )
    assert result.internal_evaluation is not None
    assert result.internal_evaluation.relevance_score >= DISALLOW_FOLLOWUP_AT_OR_ABOVE - 3


@pytest.mark.parametrize("label,answer", WEAK_OR_VAGUE_ANSWERS, ids=[a[0] for a in WEAK_OR_VAGUE_ANSWERS])
def test_weak_answers_trigger_followup(label, answer):
    """Vague or thin answers must be probed — Section 9.4's strongest follow-up signal."""
    _result, outcome = _guardrail_for(answer)
    assert outcome.decision == TurnDecision.FOLLOWUP, (
        f"{label}: expected a follow-up, got {outcome.decision} ({outcome.reason})"
    )


@pytest.mark.parametrize("label,answer", SKIP_ANSWERS, ids=[a[0] for a in SKIP_ANSWERS])
def test_skip_phrases_are_detected_and_bypass_guardrails(label, answer):
    result, outcome = _guardrail_for(answer)
    assert outcome.decision == TurnDecision.SKIP, f"{label}: expected skip, got {outcome.decision}"
    # Section 9.3: a skip carries no scores — never a scored zero.
    assert result.internal_evaluation is None


@pytest.mark.parametrize("label,answer", NOT_SKIP_ANSWERS, ids=[a[0] for a in NOT_SKIP_ANSWERS])
def test_near_miss_phrases_are_not_treated_as_skips(label, answer):
    assert not detect_skip_intent(answer), f"{label}: must not be read as a skip"


def test_skip_bypasses_guardrails_even_in_the_mandatory_band():
    """
    Section 10.3's skip exception: "a skip is never converted into a mandatory
    follow-up regardless of what score band it might otherwise fall into".
    """
    result = TurnDecisionResult(
        decision=TurnDecision.SKIP,
        utterance="No problem.",
        # Scores that would otherwise force a follow-up.
        internal_evaluation=InternalEvaluation(relevance_score=0, completeness_score=0),
    )
    outcome = apply_guardrails(result, consecutive_followups=0)
    assert outcome.decision == TurnDecision.SKIP
    assert not outcome.overridden


def test_weak_answer_still_advances_once_the_cap_is_reached():
    """
    The cap must beat the mandatory band, or a persistently weak candidate is
    probed forever and the interview never progresses (Section 10.3).
    """
    _result, outcome = _guardrail_for(
        "I'm a hard worker.", consecutive_followups=MAX_CONSECUTIVE_FOLLOWUPS
    )
    assert outcome.decision == TurnDecision.NEXT_QUESTION
    assert outcome.overridden
    assert "cap" in outcome.reason.lower()


def test_mandatory_band_overrides_a_model_that_wanted_to_move_on():
    result = TurnDecisionResult(
        decision=TurnDecision.NEXT_QUESTION,
        utterance="Great, thanks!",
        internal_evaluation=InternalEvaluation(relevance_score=2, completeness_score=9),
    )
    outcome = apply_guardrails(result, consecutive_followups=0)
    assert outcome.decision == TurnDecision.FOLLOWUP
    assert outcome.overridden


def test_disallowed_band_overrides_a_model_that_wanted_to_probe():
    result = TurnDecisionResult(
        decision=TurnDecision.FOLLOWUP,
        utterance="Tell me more.",
        internal_evaluation=InternalEvaluation(relevance_score=9, completeness_score=8),
    )
    outcome = apply_guardrails(result, consecutive_followups=0)
    assert outcome.decision == TurnDecision.NEXT_QUESTION
    assert outcome.overridden


def test_mid_band_defers_to_the_model():
    """Between the bands, Section 10.3 says "the LLM's own judgment applies freely"."""
    for wanted in (TurnDecision.FOLLOWUP, TurnDecision.NEXT_QUESTION):
        result = TurnDecisionResult(
            decision=wanted,
            utterance="...",
            internal_evaluation=InternalEvaluation(relevance_score=6, completeness_score=7),
        )
        outcome = apply_guardrails(result, consecutive_followups=0)
        assert outcome.decision == wanted
        assert not outcome.overridden


def test_band_boundaries_are_exactly_as_specified():
    """Pins the literal thresholds from Section 10.3 so a refactor can't quietly move them."""
    assert MANDATORY_FOLLOWUP_BELOW == 5
    assert DISALLOW_FOLLOWUP_AT_OR_ABOVE == 8
    assert MAX_CONSECUTIVE_FOLLOWUPS == 2

    # 4 is below 5 -> mandatory. 5 is not.
    just_below = TurnDecisionResult(
        decision=TurnDecision.NEXT_QUESTION,
        utterance="...",
        internal_evaluation=InternalEvaluation(relevance_score=4, completeness_score=10),
    )
    assert apply_guardrails(just_below, consecutive_followups=0).decision == TurnDecision.FOLLOWUP

    at_threshold = TurnDecisionResult(
        decision=TurnDecision.NEXT_QUESTION,
        utterance="...",
        internal_evaluation=InternalEvaluation(relevance_score=5, completeness_score=5),
    )
    assert apply_guardrails(at_threshold, consecutive_followups=0).decision == TurnDecision.NEXT_QUESTION


def test_scoring_is_deterministic():
    """
    Determinism is what makes this file a regression test rather than a flaky
    one — see the module docstring.
    """
    answer = STRONG_ANSWERS[0][1]
    assert score_answer(answer) == score_answer(answer)
