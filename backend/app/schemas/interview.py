from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.enums import InterviewMode, InterviewType, QuestionType, SessionStatus, TransportMode
from app.schemas.common import CamelModel


class StartInterviewRequest(CamelModel):
    # Section 4.6: "If a JD is entered, the role dropdown becomes
    # optional-but-still-shown". So an empty role is valid here, and the
    # role-or-JD requirement is enforced in interview_service where both
    # fields are visible together — a per-field validator can't see the JD.
    role: str = Field(default="", max_length=255)
    type: InterviewType
    duration_minutes: int = Field(ge=1, le=180)
    mode: InterviewMode
    # Section 4.7: recording/consent must be explicit and granted before the
    # session is created — the precheck screen's checkbox is what sets this.
    consent_given: bool
    # Accepted/persisted per Section 4.6 even though Phase 2's static
    # question bank doesn't use them yet — Phase 3's LLM engine (Section
    # 9.3) reads these directly once it exists, no schema change needed.
    job_description_text: str | None = Field(default=None, max_length=5000)
    target_company_name: str | None = Field(default=None, max_length=255)


class StartInterviewResponse(CamelModel):
    session_id: UUID
    ws_url: str
    transport_mode: TransportMode


class InterviewAnswerOut(CamelModel):
    transcript_text: str | None
    is_skipped: bool
    asr_confidence_avg: float | None


class AnswerEvaluationOut(CamelModel):
    """
    Section 9.3's `internal_evaluation`, surfaced for the candidate's own
    post-session review.

    Deliberately excludes nothing the spec protects: Section 9.3 forbids
    showing this *during* the live interview ("never spoken/shown live") and
    forbids revealing the rubric to the candidate mid-interview — it does not
    make the scores secret afterward, and Section 4.11 requires the
    question-by-question breakdown to carry "a per-question score". `reasoning`
    is folded into `followup_reason_text` rather than exposed as a separate
    field, matching Section 8's column list.
    """

    relevance_score: int | None
    completeness_score: int | None
    followup_triggered: bool
    followup_reason_text: str | None


class InterviewQuestionOut(CamelModel):
    id: UUID
    sequence_order: int
    question_text: str
    question_type: QuestionType
    interrupted_at_char_offset: int | None
    # Phase 3 additions — the follow-up chain (Section 8) and the live
    # evaluation (Section 9.3) the feedback report will build on in Phase 4.
    parent_question_id: UUID | None = None
    answer: InterviewAnswerOut | None
    evaluation: AnswerEvaluationOut | None = None


class InterviewSessionDetail(CamelModel):
    id: UUID
    role_target: str
    interview_type: InterviewType
    duration_minutes: int
    mode: InterviewMode
    status: SessionStatus
    started_at: datetime | None
    ended_at: datetime | None
    transport_mode: TransportMode | None
    # Phase 3: Section 9.3A's cost accounting, surfaced so it's visible in the
    # admin/ops view (Section 16) rather than only sitting in the table.
    total_tokens_used: int = 0
    llm_provider_used: str | None = None
    job_description_text: str | None = None
    target_company_name: str | None = None
    questions: list[InterviewQuestionOut]


class InterviewHistoryItem(CamelModel):
    id: UUID
    role_target: str
    interview_type: InterviewType
    duration_minutes: int
    mode: InterviewMode
    status: SessionStatus
    started_at: datetime | None
    ended_at: datetime | None


class LiveEventsIn(CamelModel):
    """
    A batch of client events for the HTTP fallback transport (Section 6.6).

    The events stay untyped `dict`s on purpose. Over the WebSocket they are
    validated per branch — `submit_answer` by hand, prosody and expression by
    their own models — and the whole point of this transport is that it runs the
    same handler rather than a parallel one. Parsing them into a union here would
    put a second, subtly different contract in front of the same code, which is
    exactly the drift this fallback is built to avoid.

    The cap is on batch size rather than content: a turn is a handful of events,
    and a client sending hundreds is either broken or probing.
    """

    events: list[dict] = Field(default_factory=list, max_length=32)
