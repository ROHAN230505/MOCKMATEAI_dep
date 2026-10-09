"""
interview_sessions, interview_questions, interview_answers, answer_evaluations
(Section 8). Not exercised by any Phase 1 endpoint yet — created now so the
schema is complete and Phase 2+ can build directly on top of it without a
disruptive migration later.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutils import utcnow
from app.database import Base
from app.models.enums import (
    InterviewMode,
    InterviewType,
    LLMProvider,
    QuestionType,
    SessionStatus,
    TransportMode,
    TTSProvider,
)
from app.models.types import GUID, pg_enum, TZDateTime


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_target: Mapped[str] = mapped_column(String(255), nullable=False)
    interview_type: Mapped[InterviewType] = mapped_column(pg_enum(InterviewType, "interview_type"), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[InterviewMode] = mapped_column(pg_enum(InterviewMode, "interview_mode"), nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        pg_enum(SessionStatus, "session_status"), nullable=False, default=SessionStatus.IN_PROGRESS
    )
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recording_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("recordings.id"), nullable=True)
    job_description_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transport_mode: Mapped[TransportMode | None] = mapped_column(pg_enum(TransportMode, "transport_mode"), nullable=True)
    llm_provider_used: Mapped[LLMProvider | None] = mapped_column(pg_enum(LLMProvider, "llm_provider"), nullable=True)
    tts_provider_used: Mapped[TTSProvider | None] = mapped_column(pg_enum(TTSProvider, "tts_provider"), nullable=True)
    total_tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )

    questions: Mapped[list["InterviewQuestion"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(pg_enum(QuestionType, "question_type"), nullable=False)
    parent_question_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("interview_questions.id"), nullable=True
    )
    asked_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    interrupted_at_char_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, nullable=False)

    session: Mapped["InterviewSession"] = relationship(back_populates="questions")
    answer: Mapped["InterviewAnswer | None"] = relationship(back_populates="question", uselist=False, cascade="all, delete-orphan")


class InterviewAnswer(Base):
    __tablename__ = "interview_answers"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("interview_questions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_started_at: Mapped[float | None] = mapped_column(Float, nullable=True)  # seconds offset into recording
    answer_ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    asr_confidence_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    code_panel_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, nullable=False)

    question: Mapped["InterviewQuestion"] = relationship(back_populates="answer")
    evaluation: Mapped["AnswerEvaluation | None"] = relationship(back_populates="answer", uselist=False, cascade="all, delete-orphan")


class AnswerEvaluation(Base):
    __tablename__ = "answer_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    answer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("interview_answers.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    relevance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completeness_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    followup_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    followup_reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    answer: Mapped["InterviewAnswer"] = relationship(back_populates="evaluation")
