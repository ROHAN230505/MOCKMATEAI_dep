"""
Deterministic score computation (Section 10.2).

Section 9.8 step 5 draws the line this module sits on: "LLM handles qualitative
content, deterministic code handles the score." Nothing here calls a model —
the same transcript always produces the same numbers, which is what makes a
score defensible when a candidate asks why they got it.

Two rules shape everything below.

**Skips are excluded, not zeroed.** Section 9.8: questions with
`is_skipped = true` "are excluded from the relevance/completeness scoring
average entirely (not counted as zero)". Passing on one question out of eight
is not the same as answering it terribly, and averaging in a zero would say it
was worse.

**Unmeasured categories stay NULL and their weight is redistributed.** Any of
the four can be absent in a given session: a muted microphone leaves
`confidence_score` with no inputs, a covered camera leaves `body_language_score`
with none, and before Phase 5 shipped neither had any at all. The formula
renormalizes over the categories that *were* measured instead of substituting
a neutral 50 — a fabricated midpoint would read as a real measurement of poise
nobody observed, which Section 1.2's "Honesty over flattery" rules out. The
response reports which categories were measured so the UI can say so.

Because the weights are read from `scoring_weights` (Section 10.2: "store in a
config table, not hardcoded ... so they can be tuned later without a
redeploy"), and the unmeasured categories are discovered from the data rather
than hardcoded, Phase 5 was picked up here with no change to this file at all:
`prosody_signals` and `expression_signals` rows now exist, they enter the
average, and with all four present the renormalization is a no-op.
"""
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import InterviewMode
from app.models.interview import (
    AnswerEvaluation,
    InterviewAnswer,
    InterviewQuestion,
    InterviewSession,
)
from app.models.scoring import ScoringWeights
from app.models.signals import ExpressionSignal, ProsodySignal
from app.services.feedback.transcript_signals import (
    TranscriptSignals,
    communication_score,
    extract_signals,
)

# Section 9.4's evaluation scale. relevance_score/completeness_score are 0-10
# (see services/ai/schema.py), and the report exposes 0-100.
EVALUATION_SCALE_MAX = 10
REPORT_SCALE_MAX = 100

# Section 10.2's published defaults, used only when `scoring_weights` has no
# active row — a fresh database that skipped the seed still scores rather than
# refusing to produce a report.
DEFAULT_CATEGORY_WEIGHTS = {
    "content": 0.40,
    "communication": 0.25,
    "confidence": 0.20,
    "body_language": 0.15,
}
DEFAULT_INDEX_WEIGHTS = {
    "mock_interview_avg": 0.45,
    "aptitude_avg": 0.20,
    "dsa_progress_pct": 0.25,
    "resume_ats_score": 0.10,
}


def readiness_label(score: float | None) -> str:
    """
    Section 10.2's readiness bands, in one place.

    Shared by the dashboard's cross-module index and the per-interview report so
    a candidate never sees the same number labelled two different ways in two
    parts of the product.
    """
    if score is None:
        return "Not enough data yet"
    if score >= 67:
        return "Interview Ready"
    if score >= 34:
        return "Building Foundations"
    return "Just Getting Started"


@dataclass
class CategoryWeights:
    """The four Section 10.2 category weights, plus where they came from."""

    content: float
    communication: float
    confidence: float
    body_language: float
    source: str  # "config_table" or "defaults", surfaced for auditability

    def as_dict(self) -> dict[str, float]:
        return {
            "content": self.content,
            "communication": self.communication,
            "confidence": self.confidence,
            "body_language": self.body_language,
        }


@dataclass
class ScoreBreakdown:
    """Everything the report needs about the numbers and their provenance."""

    content_score: float | None = None
    communication_score: float | None = None
    confidence_score: float | None = None
    body_language_score: float | None = None
    overall_readiness_score: float | None = None

    # Which categories contributed. `unmeasured` is the honest part of the
    # report: these are NULL because nothing measured them, not because the
    # candidate scored zero.
    measured_categories: list[str] = field(default_factory=list)
    unmeasured_categories: list[str] = field(default_factory=list)
    # Weights actually applied after renormalization.
    effective_weights: dict[str, float] = field(default_factory=dict)
    weights_source: str = "defaults"

    # Section 9.8's skip accounting, kept for the report and the prompt.
    answered_count: int = 0
    skipped_count: int = 0
    scored_count: int = 0  # answered AND evaluated
    signals: TranscriptSignals | None = None


def load_category_weights(db: Session) -> CategoryWeights:
    """
    Read the active row from `scoring_weights`.

    Called per report generation rather than cached at import, so an operator
    editing the row takes effect on the next report — the whole reason
    Section 10.2 wanted a table instead of a constant. One indexed
    single-row lookup per report is not worth a cache that would defeat that.
    """
    row = db.scalars(
        select(ScoringWeights).where(ScoringWeights.is_active.is_(True)).order_by(ScoringWeights.created_at.desc())
    ).first()
    if row is None:
        return CategoryWeights(**DEFAULT_CATEGORY_WEIGHTS, source="defaults")
    return CategoryWeights(
        content=row.content_weight,
        communication=row.communication_weight,
        confidence=row.confidence_weight,
        body_language=row.body_language_weight,
        source="config_table",
    )


def load_index_weights(db: Session) -> dict[str, float]:
    """
    The Section 10.2 readiness_index weights, from the same active row.

    Consumed by `services/dashboard_service.py`, which keeps its existing
    zero-fill behavior rather than renormalizing like `weighted_overall` does.
    The difference is deliberate: a missing `confidence_score` means *this build
    cannot measure poise yet*, so renormalizing avoids punishing the candidate
    for our gap — whereas a missing `aptitude_avg` means *the candidate has not
    taken an aptitude test*, which is a real readiness gap and should pull the
    index down.
    """
    row = db.scalars(
        select(ScoringWeights).where(ScoringWeights.is_active.is_(True)).order_by(ScoringWeights.created_at.desc())
    ).first()
    if row is None:
        return dict(DEFAULT_INDEX_WEIGHTS)
    return {
        "mock_interview_avg": row.index_mock_interview_weight,
        "aptitude_avg": row.index_aptitude_weight,
        "dsa_progress_pct": row.index_dsa_weight,
        "resume_ats_score": row.index_resume_weight,
    }


@dataclass
class TurnRecord:
    """One question/answer/evaluation triple, flattened for scoring."""

    question_id: str
    sequence_order: int
    question_text: str
    question_type: str
    is_followup: bool
    transcript_text: str | None
    is_skipped: bool
    answer_started_at: float | None
    answer_ended_at: float | None
    relevance_score: int | None
    completeness_score: int | None
    followup_reason_text: str | None
    # Carried into the report so a candidate can see when a low score was
    # computed from a transcript the recogniser itself was unsure of. Stays
    # None when the browser reported no confidence -- an unmeasured turn must
    # not be shown as a badly-heard one.
    asr_confidence_avg: float | None = None

    @property
    def has_evaluation(self) -> bool:
        return self.relevance_score is not None or self.completeness_score is not None

    @property
    def turn_score_0_100(self) -> float | None:
        """This turn's content score on the report's 0-100 scale."""
        parts = [s for s in (self.relevance_score, self.completeness_score) if s is not None]
        if not parts:
            return None
        return (sum(parts) / len(parts)) * (REPORT_SCALE_MAX / EVALUATION_SCALE_MAX)


def load_turns(db: Session, session_id) -> list[TurnRecord]:
    """
    Load the session's turns in ask order.

    Left joins throughout: a question asked but never answered (the candidate
    ran out of time mid-interview) still belongs in the transcript export, it
    just contributes nothing to the score.

    **Only questions that were actually asked.** A session's planned questions
    are written to the table up front, and the interviewer routinely does not
    reach all of them -- it runs out of time, or it spends turns on follow-ups
    instead. Without the `asked_at` filter every one of those unasked rows
    appeared in the report as a question with "No answer recorded", which tells
    the candidate they failed to answer something that was never put to them,
    and inflated `question_count` with questions that never happened. Both are
    the report claiming something it has no basis for.
    """
    rows = db.execute(
        select(InterviewQuestion, InterviewAnswer, AnswerEvaluation)
        .outerjoin(InterviewAnswer, InterviewAnswer.question_id == InterviewQuestion.id)
        .outerjoin(AnswerEvaluation, AnswerEvaluation.answer_id == InterviewAnswer.id)
        .where(InterviewQuestion.session_id == session_id)
        .where(InterviewQuestion.asked_at.isnot(None))
        .order_by(InterviewQuestion.sequence_order)
    ).all()

    turns: list[TurnRecord] = []
    for question, answer, evaluation in rows:
        turns.append(
            TurnRecord(
                question_id=str(question.id),
                sequence_order=question.sequence_order,
                question_text=question.question_text,
                question_type=question.question_type.value,
                is_followup=question.parent_question_id is not None,
                transcript_text=answer.transcript_text if answer else None,
                is_skipped=bool(answer.is_skipped) if answer else False,
                answer_started_at=answer.answer_started_at if answer else None,
                answer_ended_at=answer.answer_ended_at if answer else None,
                relevance_score=evaluation.relevance_score if evaluation else None,
                completeness_score=evaluation.completeness_score if evaluation else None,
                followup_reason_text=evaluation.followup_reason_text if evaluation else None,
                asr_confidence_avg=answer.asr_confidence_avg if answer else None,
            )
        )
    return turns


def aggregate_content_score(turns: list[TurnRecord]) -> tuple[float | None, int, int, int]:
    """
    Section 9.8's skip-aware content average.

    Returns (content_score, answered_count, skipped_count, scored_count).
    Skipped turns are dropped from the average entirely rather than counted as
    zero, and a session where every question was skipped yields None — there is
    no content to score, and 0 would be a claim about answers that were never
    given.
    """
    answered = 0
    skipped = 0
    turn_scores: list[float] = []

    for turn in turns:
        if turn.is_skipped:
            skipped += 1
            continue
        if not (turn.transcript_text or "").strip():
            # Asked but never answered — not a skip the candidate chose, and
            # not evidence either way.
            continue
        answered += 1
        score = turn.turn_score_0_100
        if score is not None:
            turn_scores.append(score)

    if not turn_scores:
        return None, answered, skipped, 0
    return round(sum(turn_scores) / len(turn_scores), 1), answered, skipped, len(turn_scores)


def _prosody_confidence_score(prosody: ProsodySignal | None) -> float | None:
    """
    Section 9.7's confidence proxy, from `prosody_signals` (Phase 5A).

    Returns None when there is no row, or when the row exists but its audio
    figures were discarded as too short a sample to measure — which keeps
    `confidence_score` NULL rather than invented.
    """
    if prosody is None:
        return None
    parts: list[float] = []
    if prosody.pitch_variance_score is not None:
        # An expressive delivery reads as more confident than a monotone one.
        parts.append(max(0.0, min(100.0, prosody.pitch_variance_score)))
    if prosody.avg_pause_duration_ms is not None:
        # Long hesitation pauses read as uncertainty; ~400ms is conversational.
        pause = prosody.avg_pause_duration_ms
        if pause <= 500:
            parts.append(85.0)
        elif pause <= 900:
            parts.append(65.0)
        elif pause <= 1500:
            parts.append(45.0)
        else:
            parts.append(30.0)
    if not parts:
        return None
    return round(sum(parts) / len(parts), 1)


def _expression_body_language_score(expression: ExpressionSignal | None) -> float | None:
    """
    Section 9.7's body-language proxy, from `expression_signals` (Phase 5B).

    Returns None when there is no row, or when the row exists with its scores
    withheld because the video coverage could not support them — a covered lens,
    a dark room, or a candidate outside frame.
    """
    if expression is None:
        return None
    parts: list[float] = []
    if expression.eye_contact_percentage is not None:
        parts.append(max(0.0, min(100.0, expression.eye_contact_percentage)))
    if expression.smile_frequency_score is not None:
        parts.append(max(0.0, min(100.0, expression.smile_frequency_score)))
    if expression.posture_flag_count is not None:
        parts.append(max(0.0, 100.0 - expression.posture_flag_count * 10))
    if not parts:
        return None
    return round(sum(parts) / len(parts), 1)


def weighted_overall(
    scores: dict[str, float | None], weights: CategoryWeights
) -> tuple[float | None, list[str], list[str], dict[str, float]]:
    """
    Section 10.2's weighted formula, renormalized over the measured categories.

    With all four present this is exactly the spec's formula. With only content
    and communication measured (Phase 4's reality) their 0.40/0.25 become
    0.62/0.38 of a score that still means "out of 100", instead of an overall
    capped at 65 that would understate every candidate for reasons that have
    nothing to do with them.

    Returns (overall, measured, unmeasured, effective_weights).
    """
    weight_map = weights.as_dict()
    measured = [name for name, value in scores.items() if value is not None]
    unmeasured = [name for name, value in scores.items() if value is None]

    total_weight = sum(weight_map[name] for name in measured)
    if not measured or total_weight <= 0:
        return None, measured, unmeasured, {}

    effective = {name: weight_map[name] / total_weight for name in measured}
    overall = sum(scores[name] * effective[name] for name in measured)  # type: ignore[operator]
    return round(overall, 1), measured, unmeasured, {k: round(v, 4) for k, v in effective.items()}


def compute_breakdown(db: Session, session_id, turns: list[TurnRecord] | None = None) -> ScoreBreakdown:
    """
    The full deterministic score for one interview session.

    This is the single place the four sub-scores and the overall are decided;
    the generator persists what this returns and the prompt is grounded in it,
    so the narrative and the number can never disagree.
    """
    if turns is None:
        turns = load_turns(db, session_id)

    content, answered, skipped, scored = aggregate_content_score(turns)

    signals = extract_signals(
        [
            {
                "text": turn.transcript_text,
                "is_skipped": turn.is_skipped,
                "started_at": turn.answer_started_at,
                "ended_at": turn.answer_ended_at,
            }
            for turn in turns
        ]
    )
    # Phase 6: which communication terms apply depends on how the candidate
    # answered. Read from the session rather than passed in, so both callers get
    # it right without either having to know it matters.
    modality = db.scalars(
        select(InterviewSession.mode).where(InterviewSession.id == session_id)
    ).first() or InterviewMode.VOICE

    communication = communication_score(signals, modality=modality)

    prosody = db.scalars(select(ProsodySignal).where(ProsodySignal.session_id == session_id)).first()
    expression = db.scalars(select(ExpressionSignal).where(ExpressionSignal.session_id == session_id)).first()

    # Phase 5's prosody service supersedes the transcript-only estimate for
    # pace/fillers when it has real audio measurements. Skipped for a signed
    # session: there is no audio to have measured a pace from, and pace is not a
    # term of that session's score anyway.
    if (
        modality is not InterviewMode.SIGN
        and prosody is not None
        and prosody.avg_pace_wpm is not None
        and signals.speaking_pace_wpm is None
    ):
        signals.speaking_pace_wpm = prosody.avg_pace_wpm
        communication = communication_score(signals, modality=modality)

    weights = load_category_weights(db)
    scores: dict[str, float | None] = {
        "content": content,
        "communication": communication,
        "confidence": _prosody_confidence_score(prosody),
        "body_language": _expression_body_language_score(expression),
    }
    overall, measured, unmeasured, effective = weighted_overall(scores, weights)

    return ScoreBreakdown(
        content_score=scores["content"],
        communication_score=scores["communication"],
        confidence_score=scores["confidence"],
        body_language_score=scores["body_language"],
        overall_readiness_score=overall,
        measured_categories=measured,
        unmeasured_categories=unmeasured,
        effective_weights=effective,
        weights_source=weights.source,
        answered_count=answered,
        skipped_count=skipped,
        scored_count=scored,
        signals=signals,
    )


