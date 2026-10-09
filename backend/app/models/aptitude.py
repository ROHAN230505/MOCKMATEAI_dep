"""aptitude_questions, aptitude_attempts, aptitude_attempt_answers (Section 8). Unused until Phase 7."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.timeutils import utcnow
from app.database import Base
from app.models.enums import AptitudeTopic, Difficulty
from app.models.types import GUID, pg_enum, TZDateTime


class AptitudeQuestion(Base):
    __tablename__ = "aptitude_questions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    topic: Mapped[AptitudeTopic] = mapped_column(pg_enum(AptitudeTopic, "aptitude_topic"), nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(pg_enum(Difficulty, "difficulty"), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict] = mapped_column(JSON, nullable=False)
    correct_option_index: Mapped[int] = mapped_column(Integer, nullable=False)
    company_pattern_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Curated rows have verified answer keys (executed in
    # `tests/test_content_banks.py`); generated rows have keys confirmed by an
    # independent re-solve. Both are checked, but not to the same standard, so
    # they stay distinguishable rather than being quietly merged.
    is_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, nullable=False)


class AptitudeAttempt(Base):
    __tablename__ = "aptitude_attempts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    test_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)  # null = practice mode
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    score: Mapped[float | None] = mapped_column(Integer, nullable=True)
    total_questions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    answers: Mapped[list["AptitudeAttemptAnswer"]] = relationship(back_populates="attempt", cascade="all, delete-orphan")


class AptitudeAttemptAnswer(Base):
    __tablename__ = "aptitude_attempt_answers"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("aptitude_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("aptitude_questions.id"), nullable=False)
    selected_option_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    attempt: Mapped["AptitudeAttempt"] = relationship(back_populates="answers")
