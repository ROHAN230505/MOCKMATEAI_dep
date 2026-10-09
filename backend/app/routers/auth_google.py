"""Google OAuth 2.0 / OpenID Connect endpoints (Section 7.1A, 6.5, 12.10)."""
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import get_current_user
from app.core.rate_limit import (
    GOOGLE_EXCHANGE_RATE_LIMIT,
    GOOGLE_CALLBACK_RATE_LIMIT,
    GOOGLE_INIT_RATE_LIMIT,
    GOOGLE_LINK_RATE_LIMIT,
    GOOGLE_UNLINK_RATE_LIMIT,
    limiter,
)
from app.core.responses import ApiError, success
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.auth import (
    GoogleAuthUrlResponse,
    GoogleExchangeRequest,
    GoogleLinkInitRequest,
    TokenPairResponse,
)
from app.schemas.user import UserPublic
from app.services import auth_service, google_oauth_service

router = APIRouter(prefix="/auth/google", tags=["auth-google"])
logger = logging.getLogger("mockmateai.auth_google")


@router.get("/init")
@limiter.limit(GOOGLE_INIT_RATE_LIMIT)
def google_init(request: Request, redis_client=Depends(get_redis)):
    auth_url = google_oauth_service.build_authorization_url(redis_client, intent="login")
    return success(GoogleAuthUrlResponse(auth_url=auth_url).model_dump(by_alias=True))


@router.get("/callback")
@limiter.limit(GOOGLE_CALLBACK_RATE_LIMIT)
async def google_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis),
):
    """
    Server-to-server redirect target from Google (Section 6.5 step 3) —
    never called by the frontend directly. Always ends in a browser
    redirect back to the SPA, success or failure, so the candidate never
    sees a bare JSON error page mid-OAuth-flow.
    """
    settings = get_settings()

    if error is not None or code is None or state is None:
        return RedirectResponse(f"{settings.frontend_url}/auth/google/complete?error=google_denied_or_missing_code")

    try:
        result = await google_oauth_service.handle_callback(db, redis_client, code=code, state=state)
    except ApiError as exc:
        logger.info("Google OAuth callback failed: %s", exc.code)
        return RedirectResponse(f"{settings.frontend_url}/auth/google/complete?error={exc.code}")

    if result["kind"] == "link":
        return RedirectResponse(f"{settings.frontend_url}/dashboard?googleLinked=true")

    user: User = result["user"]
    access_token, refresh_token = auth_service.issue_token_pair(db, user)
    ticket = google_oauth_service.issue_login_ticket(redis_client, access_token=access_token, refresh_token=refresh_token)
    is_new_user = "true" if result["is_new_user"] else "false"
    return RedirectResponse(
        f"{settings.frontend_url}/auth/google/complete?ticket={ticket}&isNewUser={is_new_user}"
    )


@router.post("/exchange")
@limiter.limit(GOOGLE_EXCHANGE_RATE_LIMIT)
def google_exchange(request: Request, body: GoogleExchangeRequest, db: Session = Depends(get_db), redis_client=Depends(get_redis)):
    """
    Not a literal Section 7.1A endpoint — the wire-level completion of the
    redirect-based flow described in google_oauth_service.py's module
    docstring. Trades the one-time ticket for our first-party token pair.
    """
    tokens = google_oauth_service.redeem_login_ticket(redis_client, body.ticket)
    payload = decode_access_token(tokens["accessToken"])
    user = db.get(User, payload["sub"])
    if user is None:
        raise ApiError(status_code=400, code="invalid_ticket", message="This sign-in link has expired. Please try again.")
    return success(
        TokenPairResponse(
            user=UserPublic.model_validate(user),
            access_token=tokens["accessToken"],
            refresh_token=tokens["refreshToken"],
        ).model_dump(by_alias=True)
    )


@router.post("/link/init")
@limiter.limit(GOOGLE_LINK_RATE_LIMIT)
def google_link_init(
    request: Request,
    body: GoogleLinkInitRequest,
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis),
):
    auth_url = google_oauth_service.begin_link_flow(redis_client, user=user, current_password=body.current_password)
    return success(GoogleAuthUrlResponse(auth_url=auth_url).model_dump(by_alias=True))


@router.delete("/unlink")
@limiter.limit(GOOGLE_UNLINK_RATE_LIMIT)
def google_unlink(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    updated_user = google_oauth_service.unlink_google_account(db, user)
    return success(UserPublic.model_validate(updated_user).model_dump(by_alias=True))
