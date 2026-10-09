"""
prosody_signals + expression_signals (Section 8).

`prosody_signals` is populated as of Phase 5A -- pitch variance and pause
patterns measured in the browser (`useProsodyAnalyser`), speaking pace and filler
count derived server-side from the transcript. See `services/prosody_service.py`.

`expression_signals` is populated as of Phase 5B -- eye contact, smile frequency
and posture flags, measured by MediaPipe's Face Landmarker in the browser
(`useExpressionAnalyser`). The video frame never leaves the device; only the three
aggregate scores are submitted. See `services/expression_service.py`, and note
that its coverage gates mean these columns stay NULL for a session where the
camera was off or the face was not visible, rather than holding a plausible
number nobody measured.
"""
import uuid

from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.types import GUID


class ProsodySignal(Base):
    __tablename__ = "prosody_signals"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    avg_pace_wpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    filler_word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pitch_variance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_pause_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class ExpressionSignal(Base):
    __tablename__ = "expression_signals"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    eye_contact_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    smile_frequency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    posture_flag_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
