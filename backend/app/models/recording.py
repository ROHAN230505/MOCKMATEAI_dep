"""
recordings (Section 8).

**Deliberately never written**, and that is not a gap waiting to be filled. Phase
2 chose browser-native ASR precisely so audio is never uploaded, Phase 5B does
the same for video, and Phase 8 for the resume file. There is no media to record
a row about, and `GET /recordings/:sessionId/audio` returns an explicit
`recording_unavailable` rather than an empty file.

The table stays because Section 8 defines it and because a future build that does
store media would need it. The old docstring said "Unused until Phase 2", which
read as pending when the truth is the opposite: Phase 2 is the reason it is empty.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import utcnow
from app.database import Base
from app.models.types import GUID, TZDateTime


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # Nullable + no FK constraint to interview_sessions here to avoid a
    # circular FK cycle (interview_sessions.recording_id -> recordings.id
    # already exists); the session<->recording relationship is 1:1 and
    # owned by interview_sessions.recording_id.
    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, unique=True, index=True)
    storage_url: Mapped[str] = mapped_column(String(1024), nullable=False)  # encrypted reference, never a public URL
    duration_seconds: Mapped[float | None] = mapped_column(Integer, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, nullable=False)
