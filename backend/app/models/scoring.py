"""
scoring_weights — runtime-tunable weights for Section 10.2's formulas.

Not in Section 8's table list, but Section 10.2 is explicit and says it twice:
"Weights are configurable (store in a config table, not hardcoded) so they can
be tuned later without a redeploy — flag this explicitly in code comments."

An env var wouldn't satisfy that: changing one needs a process restart, which
is a redeploy in every deployment model this project targets. A table lets the
weights change while the app runs, which is the actual requirement. Phase 1
left `READINESS_INDEX_WEIGHTS` in `core/constants.py` with a note deferring
this table; that note is now discharged and both weight sets live here.

Single-row design: exactly one row is active at a time (`is_active`), so
"which weights produced this score" stays answerable — an update inserts a new
active row rather than mutating history, since a report generated last week
was scored under whatever weights were active then.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import utcnow
from app.database import Base
from app.models.types import GUID, TZDateTime


class ScoringWeights(Base):
    __tablename__ = "scoring_weights"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Section 10.2's overall_readiness_score weights (per interview) ---
    content_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.40)
    communication_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.25)
    confidence_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.20)
    body_language_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.15)

    # --- Section 10.2's readiness_index weights (dashboard, across modules) ---
    index_mock_interview_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.45)
    index_aptitude_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.20)
    index_dsa_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.25)
    index_resume_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)

    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, nullable=False)
