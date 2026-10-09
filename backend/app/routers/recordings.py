"""
Transcript / recording endpoints (Section 7.4).

The transcript endpoints are real. The audio endpoint is deliberately and
explicitly *not*: this build performs ASR in the browser via the Web Speech API
and never uploads or stores audio, so there is no recording to serve. Returning
an empty file or a fake URL would be worse than a clear error — Section 1.2's
honesty rule applies to the API surface as much as to feedback copy, and a
frontend that gets `recording_unavailable` can hide its download button instead
of offering a link that breaks.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import STANDARD_RATE_LIMIT, limiter
from app.core.responses import ApiError
from app.database import get_db
from app.models.user import User
from app.redis_client import get_redis
from app.services import ai_quota, interview_service
from app.services.feedback import exports, generator
from app.services.feedback.scoring import load_turns

router = APIRouter(prefix="/recordings", tags=["recordings"])


@router.get("/{session_id}/transcript")
@limiter.limit(STANDARD_RATE_LIMIT)
def download_transcript(
    request: Request,
    session_id: UUID,
    format: str = Query(default="txt", pattern="^(txt|json)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis),
):
    """
    Section 7.4's `GET /recordings/:sessionId/transcript`.

    Both formats are served here rather than at two paths so the `format` query
    param is the only thing that varies — the transcript is one resource with two
    representations.
    """
    session = interview_service.get_session_for_user(db, user, session_id)
    ai_quota.consume_export(redis_client, str(user.id))

    turns = load_turns(db, session.id)
    report = generator.get_report(db, session.id)
    stem = exports.filename_stem(session)

    if format == "json":
        body = exports.transcript_json_bytes(session, turns, report)
        media_type = "application/json"
        filename = f"{stem}-transcript.json"
    else:
        body = exports.transcript_text(session, turns, report).encode("utf-8")
        media_type = "text/plain; charset=utf-8"
        filename = f"{stem}-transcript.txt"

    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{session_id}/audio")
@limiter.limit(STANDARD_RATE_LIMIT)
def download_audio(
    request: Request,
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Section 7.4's `GET /recordings/:sessionId/audio` — honestly unavailable.

    Ownership is still checked first, so this can't be used to probe which
    session IDs exist. The 404 is intentional over a 501: from the client's point
    of view there is no such resource for this session, and the error code says
    exactly why.
    """
    interview_service.get_session_for_user(db, user, session_id)
    raise ApiError(
        status_code=404,
        code="recording_unavailable",
        message=(
            "No audio recording exists for this interview. Speech recognition runs in your browser "
            "and no audio is uploaded or stored, so only the text transcript is available."
        ),
    )
