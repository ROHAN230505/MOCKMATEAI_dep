"""User profile, preferences, notification and privacy endpoints (Sections 7.2, 4.17-4.19)."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import limiter, ACCOUNT_DELETE_RATE_LIMIT, STANDARD_RATE_LIMIT
from app.core.responses import success
from app.database import get_db
from app.models.user import User
from app.schemas.settings import (
    NotificationPreferences,
    PrivacyInventory,
    ProfileOut,
    UpdateProfileRequest,
)
from app.schemas.user import UserPreferencesUpdate, UserPublic
from app.services import settings_service, user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
@limiter.limit(STANDARD_RATE_LIMIT)
def get_me(request: Request, user: User = Depends(get_current_user)):
    return success(UserPublic.model_validate(user).model_dump(by_alias=True))


@router.put("/preferences")
@limiter.limit(STANDARD_RATE_LIMIT)
def update_preferences(
    request: Request,
    body: UserPreferencesUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    updated = user_service.update_preferences(db, user, body)
    return success(UserPublic.model_validate(updated).model_dump(by_alias=True))


@router.delete("/me")
@limiter.limit(ACCOUNT_DELETE_RATE_LIMIT)
def delete_me(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    user_service.delete_account(db, user)
    return success(None)


@router.get("/profile")
@limiter.limit(STANDARD_RATE_LIMIT)
def get_profile(request: Request, user: User = Depends(get_current_user)):
    """
    Section 4.18's profile screen, including which auth methods are attached.

    `hasPassword`/`hasGoogle` are derived rather than exposing `password_hash` or
    `google_sub` — the screen needs to know whether unlinking Google is allowed
    (Section 12.10's "at least one auth method" rule), which is a boolean, not a
    credential.
    """
    return success(
        ProfileOut(
            id=str(user.id),
            name=user.name,
            email=user.email,
            email_verified=user.email_verified,
            auth_provider=user.auth_provider.value,
            has_password=bool(user.password_hash),
            has_google=bool(user.google_sub),
            role=user.role.value,
            target_role=user.target_role,
            experience_level=user.experience_level,
            preferred_mode=user.preferred_mode,
            created_at=user.created_at,
        ).model_dump(by_alias=True, mode="json")
    )


@router.put("/profile")
@limiter.limit(STANDARD_RATE_LIMIT)
def update_profile(
    request: Request,
    body: UpdateProfileRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    user.name = body.name.strip()
    db.commit()
    db.refresh(user)
    return success(UserPublic.model_validate(user).model_dump(by_alias=True))


@router.get("/notifications")
@limiter.limit(STANDARD_RATE_LIMIT)
def get_notifications(request: Request, user: User = Depends(get_current_user)):
    return success(
        NotificationPreferences(
            practice_reminders=user.notify_practice_reminders,
            weekly_summary=user.notify_weekly_summary,
            reminder_cadence_days=user.reminder_cadence_days,
        ).model_dump(by_alias=True)
    )


@router.put("/notifications")
@limiter.limit(STANDARD_RATE_LIMIT)
def update_notifications(
    request: Request,
    body: NotificationPreferences,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user.notify_practice_reminders = body.practice_reminders
    user.notify_weekly_summary = body.weekly_summary
    user.reminder_cadence_days = body.reminder_cadence_days
    db.commit()
    return success(body.model_dump(by_alias=True))


@router.get("/privacy")
@limiter.limit(STANDARD_RATE_LIMIT)
def get_privacy_inventory(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Section 4.17's data inventory, counted from real rows.

    Section 4.17 asks for a list of stored recordings with per-item delete. There
    are no recordings to list, so rather than an empty list under a heading that
    implies otherwise, this returns what the account actually holds per category
    plus an explicit list of what is never stored at all.
    """
    return success(
        PrivacyInventory(**settings_service.build_inventory(db, user)).model_dump(by_alias=True)
    )
