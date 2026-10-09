"""Dashboard summary endpoint (Section 7.9)."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import limiter, STANDARD_RATE_LIMIT
from app.core.responses import success
from app.database import get_db
from app.models.user import User
from app.services.dashboard_service import get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
@limiter.limit(STANDARD_RATE_LIMIT)
def dashboard_summary(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    summary = get_dashboard_summary(db, user)
    return success(summary.model_dump(by_alias=True))
