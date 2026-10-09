"""
Follow-up trigger logic — the deterministic guardrail layer from Section 10.3.

Section 10.3: "Even though the LLM decides follow-ups contextually (Section
9.3), add a deterministic guardrail so behavior is consistent and testable."

This module is pure and side-effect free: same inputs -> same decision, no DB,
no network, no clock. That is what makes Section 15's AI evaluation set a
genuine regression test — the guardrail's behavior is pinned even though the
LLM's own judgment underneath it is not.

The rules, verbatim from Section 10.3:
- relevance < 5 OR completeness < 5  -> follow-up MANDATORY
- both >= 8                          -> follow-up DISALLOWED (protects pacing)
- in between                         -> the LLM's own judgment applies freely
- cap: no more than 2 consecutive follow-ups on the same original question
- skip exception: `decision: skip` bypasses all of the above entirely
"""
from dataclasses import dataclass

from app.services.ai.contracts import TurnDecision, TurnDecisionResult

MANDATORY_FOLLOWUP_BELOW = 5
DISALLOW_FOLLOWUP_AT_OR_ABOVE = 8
MAX_CONSECUTIVE_FOLLOWUPS = 2


@dataclass
class GuardrailOutcome:
    """
    The post-guardrail decision plus why it landed there.

    `reason` is persisted to `answer_evaluations.followup_reason_text`, so a
    later reviewer can tell an LLM-chosen follow-up from a guardrail-forced
    one — which matters when tuning the prompt, since only the former is
    evidence about the prompt's quality.
    """

    decision: TurnDecision
    reason: str
    overridden: bool


def apply_guardrails(
    result: TurnDecisionResult, *, consecutive_followups: int
) -> GuardrailOutcome:
    """
    `consecutive_followups` is how many follow-ups have already been asked in
    an unbroken chain on the CURRENT original question (0 on a fresh planned
    question).
    """
    # --- Skip exception (Section 10.3) ---
    # Checked first and unconditionally: "a skip is never converted into a
    # mandatory follow-up regardless of what score band it might otherwise
    # fall into, since no evaluable answer was actually given."
    if result.decision == TurnDecision.SKIP:
        return GuardrailOutcome(
            decision=TurnDecision.SKIP,
            reason="Candidate explicitly passed on the question; skip bypasses all follow-up guardrails.",
            overridden=False,
        )

    evaluation = result.internal_evaluation
    relevance = evaluation.relevance_score if evaluation else None
    completeness = evaluation.completeness_score if evaluation else None

    # --- Consecutive follow-up cap (Section 10.3) ---
    # Checked before the mandatory band, because the cap is what stops a
    # persistently weak answer from being probed forever: a candidate who
    # keeps scoring < 5 would otherwise trigger "mandatory follow-up" on
    # every turn and never advance. "Mirrors real interview behavior; an
    # interviewer doesn't interrogate one topic forever."
    if result.decision == TurnDecision.FOLLOWUP and consecutive_followups >= MAX_CONSECUTIVE_FOLLOWUPS:
        return GuardrailOutcome(
            decision=TurnDecision.NEXT_QUESTION,
            reason=(
                f"Follow-up cap reached ({MAX_CONSECUTIVE_FOLLOWUPS} consecutive on this question); "
                "moving on regardless of scores."
            ),
            overridden=True,
        )

    # Missing scores (a provider returned no evaluation on a non-skip turn)
    # leave the LLM's choice alone — there's nothing to band it against, and
    # inventing a score to force a branch would be worse than deferring.
    if relevance is None or completeness is None:
        return GuardrailOutcome(
            decision=result.decision,
            reason="No numeric evaluation available; deferred to the model's own decision.",
            overridden=False,
        )

    # --- Mandatory band ---
    if relevance < MANDATORY_FOLLOWUP_BELOW or completeness < MANDATORY_FOLLOWUP_BELOW:
        overridden = result.decision != TurnDecision.FOLLOWUP
        return GuardrailOutcome(
            decision=TurnDecision.FOLLOWUP,
            reason=(
                f"Follow-up mandatory: relevance={relevance}, completeness={completeness} "
                f"(one or both below {MANDATORY_FOLLOWUP_BELOW})."
            ),
            overridden=overridden,
        )

    # --- Disallowed band ---
    if relevance >= DISALLOW_FOLLOWUP_AT_OR_ABOVE and completeness >= DISALLOW_FOLLOWUP_AT_OR_ABOVE:
        overridden = result.decision == TurnDecision.FOLLOWUP
        return GuardrailOutcome(
            decision=TurnDecision.NEXT_QUESTION,
            reason=(
                f"Follow-up disallowed: relevance={relevance}, completeness={completeness} "
                f"(both at or above {DISALLOW_FOLLOWUP_AT_OR_ABOVE}); protects interview pacing."
            ),
            overridden=overridden,
        )

    # --- Mid band: the LLM's judgment stands ---
    return GuardrailOutcome(
        decision=result.decision,
        reason=(
            f"Model judgment applied within the mid band "
            f"(relevance={relevance}, completeness={completeness})."
        ),
        overridden=False,
    )
