"""dsa_problems + dsa_submissions (Section 8). Unused until Phase 7."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.timeutils import utcnow
from app.database import Base
from app.models.enums import DSATopic, Difficulty, SubmissionStatus
from app.models.types import GUID, pg_enum, TZDateTime


class DSAProblem(Base):
    __tablename__ = "dsa_problems"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    topic: Mapped[DSATopic] = mapped_column(pg_enum(DSATopic, "dsa_topic"), nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(pg_enum(Difficulty, "dsa_difficulty"), nullable=False)
    statement_text: Mapped[str] = mapped_column(Text, nullable=False)
    constraints_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    starter_code: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # per-language templates
    test_cases: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # {"sample": [...], "hidden": [...]}

    # Curated problems have test cases verified by executing a reference
    # solution; generated ones have them verified by independent recomputation.
    # Both are checked, not to the same standard, so they stay separable.
    is_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, nullable=False)

    submissions: Mapped[list["DSASubmission"]] = relationship(back_populates="problem")


class DSASubmission(Base):
    __tablename__ = "dsa_submissions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("dsa_problems.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(pg_enum(SubmissionStatus, "submission_status"), nullable=False)
    runtime_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hints_used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, nullable=False)

    problem: Mapped["DSAProblem"] = relationship(back_populates="submissions")
