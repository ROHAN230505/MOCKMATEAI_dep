"""feedback_reports + feedback_details (Section 8), driven by Phase 4's Feedback Generation Service."""
import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutils import utcnow
from app.database import Base
from app.models.enums import FeedbackCategory, FeedbackGenerationStatus, FeedbackItemType
from app.models.types import GUID, pg_enum, TZDateTime


class FeedbackReport(Base):
    __tablename__ = "feedback_reports"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    overall_readiness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    communication_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_language_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    # --- Phase 4 generation bookkeeping (see FeedbackGenerationStatus) ---
    generation_status: Mapped[FeedbackGenerationStatus] = mapped_column(
        pg_enum(FeedbackGenerationStatus, "feedback_generation_status"),
        nullable=False,
        default=FeedbackGenerationStatus.PENDING,
        index=True,
    )
    # Provider that wrote the narrative ("anthropic", "openai") or
    # "deterministic" when no provider was available. Section 4.11's report
    # tells the candidate which, so rule-based prose is never mistaken for
    # analysis a model actually did.
    generated_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, nullable=False)

    details: Mapped[list["FeedbackDetail"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class FeedbackDetail(Base):
    __tablename__ = "feedback_details"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("feedback_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[FeedbackCategory] = mapped_column(pg_enum(FeedbackCategory, "feedback_category"), nullable=False)
    type: Mapped[FeedbackItemType] = mapped_column(pg_enum(FeedbackItemType, "feedback_item_type"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    report: Mapped["FeedbackReport"] = relationship(back_populates="details")
