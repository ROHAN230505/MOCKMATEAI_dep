"""
Admin / TnP aggregate dashboard (Sections 7.9, 16).

Role-gated server-side via `require_admin`, not by hiding a nav link: Section 12.2
requires every admin endpoint to verify the role independently, because a client
that simply requests the URL must be refused.

Everything returned is aggregate. See `services/admin_analytics.py` for why
individual drill-down is absent rather than merely hidden, and for the
small-cohort suppression that keeps a four-person "average" from being one
person's data.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.rate_limit import STANDARD_RATE_LIMIT, limiter
from app.core.responses import success
from app.database import get_db
from app.models.user import User
from app.schemas.admin import AdminAnalyticsOut
from app.services import admin_analytics

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/analytics")
@limiter.limit(STANDARD_RATE_LIMIT)
def analytics(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    return success(
        AdminAnalyticsOut(**admin_analytics.build_analytics(db)).model_dump(
            by_alias=True, mode="json"
        )
    )
