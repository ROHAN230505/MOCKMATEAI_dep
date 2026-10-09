"""Email/password auth endpoints (Section 7.1)."""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import get_current_user
from app.core.rate_limit import (
    STANDARD_RATE_LIMIT,
    CHECK_ACCOUNT_TYPE_RATE_LIMIT,
    FORGOT_PASSWORD_RATE_LIMIT,
    LOGIN_RATE_LIMIT,
    REFRESH_RATE_LIMIT,
    RESET_PASSWORD_RATE_LIMIT,
    SIGNUP_RATE_LIMIT,
    limiter,
)
from app.core.responses import success
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    CheckAccountTypeRequest,
    CheckAccountTypeResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenPairResponse,
)
from app.schemas.user import UserPublic
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("mockmateai.auth")


@router.post("/signup", status_code=201)
@limiter.limit(SIGNUP_RATE_LIMIT)
def signup(request: Request, body: SignupRequest, db: Session = Depends(get_db)):
    user = auth_service.create_user(db, name=body.name, email=body.email, password=body.password)
    access_token, refresh_token = auth_service.issue_token_pair(db, user)
    return success(
        TokenPairResponse(
            user=UserPublic.model_validate(user), access_token=access_token, refresh_token=refresh_token
        ).model_dump(by_alias=True)
    )


@router.post("/login")
@limiter.limit(LOGIN_RATE_LIMIT)
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    user = auth_service.authenticate_user(db, email=body.email, password=body.password)
    access_token, refresh_token = auth_service.issue_token_pair(db, user)
    return success(
        TokenPairResponse(
            user=UserPublic.model_validate(user), access_token=access_token, refresh_token=refresh_token
        ).model_dump(by_alias=True)
    )


@router.post("/check-account-type")
@limiter.limit(CHECK_ACCOUNT_TYPE_RATE_LIMIT)
def check_account_type(request: Request, body: CheckAccountTypeRequest, db: Session = Depends(get_db)):
    auth_method = auth_service.check_account_type(db, body.email)
    return success(CheckAccountTypeResponse(auth_method=auth_method).model_dump(by_alias=True))


@router.post("/refresh")
@limiter.limit(REFRESH_RATE_LIMIT)
def refresh(request: Request, body: RefreshRequest, db: Session = Depends(get_db)):
    access_token, refresh_token, _user = auth_service.rotate_refresh_token(db, body.refresh_token)
    return success({"accessToken": access_token, "refreshToken": refresh_token})


@router.post("/logout")
@limiter.limit(STANDARD_RATE_LIMIT)
def logout(request: Request, body: LogoutRequest, db: Session = Depends(get_db)):
    auth_service.logout(db, body.refresh_token)
    return success(None)


@router.post("/logout-all-devices")
@limiter.limit(STANDARD_RATE_LIMIT)
def logout_all_devices(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    auth_service.logout_all_devices(db, user)
    return success(None)


@router.post("/forgot-password")
@limiter.limit(FORGOT_PASSWORD_RATE_LIMIT)
def forgot_password(request: Request, body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Always the same response regardless of whether the email exists
    # (Section 7.1 / 12.3 — avoids both a message-content and a
    # response-shape enumeration oracle).
    raw_token = auth_service.request_password_reset(db, body.email)
    settings = get_settings()
    if raw_token is not None:
        logger.info("Password reset requested for %s — token (dev-visible only): %s", body.email, raw_token)
    payload = {}
    if not settings.is_production and raw_token is not None:
        # Convenience only: surfaces the token so local development can
        # exercise the reset flow without a real Notification Service
        # (Section 6.1) wired up yet. Never present outside development.
        payload["devResetToken"] = raw_token
    return success(payload or None)


@router.post("/reset-password")
@limiter.limit(RESET_PASSWORD_RATE_LIMIT)
def reset_password(request: Request, body: ResetPasswordRequest, db: Session = Depends(get_db)):
    auth_service.reset_password(db, token=body.token, new_password=body.new_password)
    return success(None)
