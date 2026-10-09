"""
Feedback report response schemas (Section 7.4, Section 4.11).

The report deliberately ships more than the four numbers. Section 4.11's screen
needs the evidence behind each item, and the honest presentation of a partial
report needs `measured` / `unmeasured` to be explicit on the wire rather than
inferred from nulls — a client that sees `confidenceScore: null` shouldn't have
to guess whether that means "zero", "loading", or "never measured".
"""
from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.enums import FeedbackCategory, FeedbackGenerationStatus, FeedbackItemType
from app.schemas.common import CamelModel


class CategoryScoreOut(CamelModel):
    category: FeedbackCategory
    score: float | None
    # The weight actually applied after renormalization over measured
    # categories (Section 10.2), so the UI can show how the overall was built.
    weight: float | None
    measured: bool
    label: str


class FeedbackItemOut(CamelModel):
    category: FeedbackCategory
    type: FeedbackItemType
    text: str
    evidence_reference: str | None = None


class TranscriptTurnOut(CamelModel):
    number: int
    question_id: UUID
    question_text: str
    is_followup: bool
    answer_text: str | None = None
    is_skipped: bool = False
    relevance_score: int | None = None
    completeness_score: int | None = None
    # None means "the browser reported no confidence", not "confidence was
    # zero" -- the UI distinguishes the two and must be able to.
    asr_confidence_avg: float | None = None


class TranscriptSignalsOut(CamelModel):
    """Section 9.7's transcript-derived signals, shown as evidence not as a score."""

    answer_count: int
    total_words: int
    filler_count: int
    filler_rate_per_100_words: float
    average_answer_words: float
    quantified_answers: int
    under_elaborated_answers: int
    well_developed_answers: int
    speaking_pace_wpm: float | None = None


class CategoryDeltaOut(CamelModel):
    category: str
    previous: float | None
    current: float | None
    delta: float | None
    direction: str


class ComparisonOut(CamelModel):
    """Section 4.11A's Before & After block."""

    previous_session_id: UUID
    previous_role_target: str
    previous_completed_at: datetime | None = None
    same_role: bool
    headline: str
    deltas: list[CategoryDeltaOut] = Field(default_factory=list)


class FeedbackReportOut(CamelModel):
    session_id: UUID
    status: FeedbackGenerationStatus
    generated_at: datetime | None = None
    # "anthropic" / "openai" / "deterministic" — Section 4.11 tells the
    # candidate which, so rule-based prose is never mistaken for model analysis.
    generated_by: str | None = None

    role_target: str
    interview_type: str
    # Carried so "Retake this interview" can pre-fill the setup screen with the
    # same configuration, which the Phase 2 summary screen did from the session
    # detail endpoint.
    duration_minutes: int
    mode: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    target_company_name: str | None = None

    overall_readiness_score: float | None = None
    readiness_label: str
    category_scores: list[CategoryScoreOut] = Field(default_factory=list)
    measured_categories: list[str] = Field(default_factory=list)
    unmeasured_categories: list[str] = Field(default_factory=list)

    summary_text: str | None = None
    strengths: list[FeedbackItemOut] = Field(default_factory=list)
    improvements: list[FeedbackItemOut] = Field(default_factory=list)

    answered_count: int = 0
    skipped_count: int = 0
    question_count: int = 0
    turns: list[TranscriptTurnOut] = Field(default_factory=list)
    signals: TranscriptSignalsOut | None = None

    comparison: ComparisonOut | None = None
    disclaimer: str


class FeedbackStatusOut(CamelModel):
    """
    The lightweight shape Section 4.10's processing screen polls.

    Separate from the full report so a client polling every second isn't pulling
    the entire transcript down each time.
    """

    session_id: UUID
    status: FeedbackGenerationStatus
    generated_at: datetime | None = None
    # Populated only when `status` is FAILED — see the note in the route.
    error: str | None = None
