"""
readiness_snapshots (Section 8) — periodic dashboard trend rollups.

**Still unwritten and unread as of Phase 8.** The docstring here previously said
"Unused until Phase 8", which Phase 8 did not make true: the resume analyzer
shipped without touching this table.

The dashboard does show a readiness trend, but it is computed live in the browser
(`useReportSeries`) from up to six `GET /feedback/:id` calls, which has two
consequences worth being explicit about rather than leaving for someone to
discover:

1. It plots **interview scores only**. The aptitude, DSA and resume columns below
   have no equivalent history, so the trend is narrower than the readiness index
   the dashboard shows beside it.
2. It is N+1 requests per dashboard load and reaches back only as far as the
   retained reports do.

Filling this table would need a scheduled job writing one row per user per day.
That is a deployment decision (where the scheduler runs) as much as a code one,
which is why it has not been done unilaterally.
"""
import uuid
from datetime import date

from sqlalchemy import Date, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.types import GUID


class ReadinessSnapshot(Base):
    __tablename__ = "readiness_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    readiness_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    mock_interview_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    aptitude_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    dsa_progress_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    resume_score: Mapped[float | None] = mapped_column(Float, nullable=True)
