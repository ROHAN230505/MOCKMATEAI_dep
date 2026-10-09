"""
Resume analysis endpoints (Phase 8).

Metered against the same per-user AI budget as interviews and hints. Analysis is
deterministic today and costs no provider call, but it is the kind of endpoint a
loop can hammer, and Section 12.1A names resume analyses per day as one of its
cost-sensitive quotas alongside interview minutes.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import STANDARD_RATE_LIMIT, limiter
from app.core.responses import success
from app.database import get_db
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.resume import AnalyseResumeRequest, ResumeAnalysisOut, ResumeHistoryItem
from app.services import ai_quota
from app.services.resume import service as resume_service

router = APIRouter(prefix="/resume", tags=["resume"])


@router.post("/analyses")
@limiter.limit(STANDARD_RATE_LIMIT)
def analyse_resume(
    request: Request,
    body: AnalyseResumeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis),
):
    ai_quota.consume_resume_analysis(redis_client, str(user.id))
    row, _ = resume_service.analyse_and_store(db, user, body)
    return success(
        ResumeAnalysisOut(**resume_service.to_payload(row)).model_dump(by_alias=True, mode="json")
    )


@router.get("/analyses/{analysis_id}")
@limiter.limit(STANDARD_RATE_LIMIT)
def read_analysis(
    request: Request,
    analysis_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = resume_service.get_for_user(db, user, analysis_id)
    return success(
        ResumeAnalysisOut(**resume_service.to_payload(row)).model_dump(by_alias=True, mode="json")
    )


@router.get("/analyses")
@limiter.limit(STANDARD_RATE_LIMIT)
def list_analyses(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = resume_service.list_for_user(db, user, limit=limit)
    return success(
        [
            ResumeHistoryItem(
                id=row.id,
                ats_score=row.ats_score,
                had_job_description=bool(row.job_description_text),
                analyzed_at=row.analyzed_at,
            ).model_dump(by_alias=True, mode="json")
            for row in rows
        ]
    )
