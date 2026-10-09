"""
Multimodal signal endpoints (Section 9.7, Phase 5).

Two families, one shape. The browser measures what only the raw media can tell it
— pitch and pauses from the waveform, gaze and posture from the video frame — and
posts the aggregate here; the server derives everything the transcript can
already answer. Neither the audio nor the video ever leaves the device. See
`services/prosody_service.py` and `services/expression_service.py` for why each
split falls where it does.

Ownership is checked on every route through `interview_service.get_session_for_user`
— Section 12.2's object-level authorization. A session id in the URL is not
permission to write signals against it.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import STANDARD_RATE_LIMIT, limiter
from app.core.responses import ApiError, success
from app.database import get_db
from app.models.enums import SessionStatus
from app.models.user import User
from app.schemas.signals import (
    ExpressionSignalIn,
    ExpressionSignalOut,
    ProsodySignalIn,
    ProsodySignalOut,
)
from app.services import expression_service, interview_service, prosody_service

router = APIRouter(prefix="/interviews", tags=["signals"])


def _prosody_out(session_id, row) -> dict:
    return ProsodySignalOut(
        session_id=str(session_id),
        avg_pace_wpm=row.avg_pace_wpm,
        filler_word_count=row.filler_word_count,
        pitch_variance_score=row.pitch_variance_score,
        avg_pause_duration_ms=row.avg_pause_duration_ms,
    ).model_dump(by_alias=True, mode="json")


@router.post("/{session_id}/signals/prosody")
@limiter.limit(STANDARD_RATE_LIMIT)
def submit_prosody(
    request: Request,
    session_id: UUID,
    body: ProsodySignalIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Record the session's voice prosody, after the fact.

    This is the *secondary* channel. During a live interview the client streams
    its running aggregate over the interview WebSocket (`prosody_update`), which
    is what gets the row in place before the server ends the session and
    schedules report generation. This endpoint exists for the cases where there
    is no socket to send on: the REST `/interviews/:id/end` path, and recovery
    after a connection that dropped before the last update landed.

    Hence the 409 while the session is still running — mid-interview updates
    belong on the socket that is already open, not on a separate HTTP request
    racing it. A submission here always describes a finished recording.
    """
    session = interview_service.get_session_for_user(db, user, session_id)

    if session.status == SessionStatus.IN_PROGRESS:
        raise ApiError(
            status_code=409,
            code="interview_in_progress",
            message="Prosody can only be recorded once the interview has finished.",
        )

    if not prosody_service.accepts_prosody(session):
        raise ApiError(
            status_code=409,
            code="modality_has_no_audio",
            message="This was a signed interview, which has no audio to measure prosody from.",
        )

    row = prosody_service.submit_prosody(db, session, body)
    return success(_prosody_out(session.id, row))


@router.get("/{session_id}/signals/prosody")
@limiter.limit(STANDARD_RATE_LIMIT)
def read_prosody(
    request: Request,
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = interview_service.get_session_for_user(db, user, session_id)
    row = prosody_service.get_prosody(db, session.id)
    if row is None:
        raise ApiError(
            status_code=404,
            code="prosody_not_recorded",
            message="No prosody was recorded for this interview.",
        )
    return success(_prosody_out(session.id, row))


def _expression_out(session_id, row) -> dict:
    return ExpressionSignalOut(
        session_id=str(session_id),
        eye_contact_percentage=row.eye_contact_percentage,
        smile_frequency_score=row.smile_frequency_score,
        posture_flag_count=row.posture_flag_count,
    ).model_dump(by_alias=True, mode="json")


@router.post("/{session_id}/signals/expression")
@limiter.limit(STANDARD_RATE_LIMIT)
def submit_expression(
    request: Request,
    session_id: UUID,
    body: ExpressionSignalIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Record the session's expression signals, after the fact.

    The secondary channel, exactly as for prosody: during a live interview the
    client streams its running aggregate over the interview WebSocket
    (`expression_update`), because the server ends the session and starts report
    generation in the same breath and anything sent afterwards loses that race.
    This endpoint covers the cases with no socket to send on — the REST
    `/interviews/:id/end` path, and recovery after a dropped connection.
    """
    session = interview_service.get_session_for_user(db, user, session_id)

    if session.status == SessionStatus.IN_PROGRESS:
        raise ApiError(
            status_code=409,
            code="interview_in_progress",
            message="Expression signals can only be recorded once the interview has finished.",
        )

    row = expression_service.submit_expression(db, session, body)
    return success(_expression_out(session.id, row))


@router.get("/{session_id}/signals/expression")
@limiter.limit(STANDARD_RATE_LIMIT)
def read_expression(
    request: Request,
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = interview_service.get_session_for_user(db, user, session_id)
    row = expression_service.get_expression(db, session.id)
    if row is None:
        raise ApiError(
            status_code=404,
            code="expression_not_recorded",
            message="No expression signals were recorded for this interview.",
        )
    return success(_expression_out(session.id, row))
