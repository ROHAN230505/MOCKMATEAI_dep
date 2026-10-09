"""
Google OAuth 2.0 / OpenID Connect — Authorization Code + PKCE flow
(Section 6.5, 12.10).

Wire-level detail not spelled out verbatim in the spec: since the callback
(step 3-9 of 6.5) is a server-to-server redirect target, not something the
SPA calls with `fetch`, the backend hands the browser back to the frontend
via a short-lived, single-use "ticket" (stored in Redis, TTL 60s) rather
than putting the issued access/refresh tokens directly in a redirect URL
where they'd sit in browser history/referrer headers (Section 12.3). The
frontend's `/auth/google/complete` page immediately exchanges that ticket
for the real token pair via `POST /auth/google/exchange`.
"""
import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.responses import ApiError
from app.core.security import verify_password
from app.models.enums import AuthProvider
from app.models.user import User

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_ENDPOINT = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}

_PENDING_AUTH_TTL_SECONDS = 5 * 60  # Section 6.5 step 1
_TICKET_TTL_SECONDS = 60
_JWKS_CACHE_TTL_SECONDS = 3600

_jwks_cache: dict = {"fetched_at": 0.0, "keys": None}


def _pending_auth_key(state: str) -> str:
    return f"oauth:google:pending:{state}"


def _ticket_key(ticket: str) -> str:
    return f"oauth:google:ticket:{ticket}"


@dataclass
class PendingAuth:
    code_verifier: str
    intent: str  # "login" | "link"
    linking_user_id: str | None = None


def build_authorization_url(redis_client, *, intent: str = "login", linking_user_id: str | None = None) -> str:
    """
    Section 6.5 step 1: generate state + PKCE pair, stash server-side,
    return the Google URL.

    Google only ever redirects to one registered callback route, so both
    the anonymous login/signup button and the authenticated "link Google"
    action (Section 7.1A) share `GET /auth/google/callback` — the pending
    record's `intent` (and, for linking, the already-authenticated
    `linking_user_id` captured *before* the redirect) tells the callback
    which branch to run, since the redirect itself carries no auth header.
    """
    settings = get_settings()

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")

    record = json.dumps({"code_verifier": code_verifier, "intent": intent, "linking_user_id": linking_user_id})
    redis_client.setex(_pending_auth_key(state), _PENDING_AUTH_TTL_SECONDS, record)

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
    }
    return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"


def _consume_pending_auth(redis_client, state: str) -> PendingAuth:
    """Verifies + deletes the pending record atomically-enough for our threat model (single-use, Section 6.5 step 9)."""
    key = _pending_auth_key(state)
    raw = redis_client.get(key)
    if raw is None:
        raise ApiError(status_code=400, code="invalid_oauth_state", message="This sign-in attempt has expired. Please try again.")
    redis_client.delete(key)
    data = json.loads(raw)
    return PendingAuth(**data)


async def _exchange_code(*, code: str, code_verifier: str) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": settings.oauth_redirect_uri,
            },
        )
    if resp.status_code != 200:
        raise ApiError(status_code=502, code="google_token_exchange_failed", message="Google sign-in failed. Please try again.")
    return resp.json()


async def _fetch_jwks() -> list[dict]:
    now = time.time()
    if _jwks_cache["keys"] is not None and now - _jwks_cache["fetched_at"] < _JWKS_CACHE_TTL_SECONDS:
        return _jwks_cache["keys"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(GOOGLE_JWKS_ENDPOINT)
        resp.raise_for_status()
    keys = resp.json()["keys"]
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


async def _verify_id_token(id_token_str: str) -> dict:
    """Section 6.5 step 5 / 12.10: verify signature against Google's JWKS + validate claims."""
    settings = get_settings()
    try:
        unverified_header = jwt.get_unverified_header(id_token_str)
    except jwt.InvalidTokenError:
        raise ApiError(status_code=401, code="invalid_google_token", message="Google sign-in failed. Please try again.")

    keys = await _fetch_jwks()
    jwk = next((k for k in keys if k["kid"] == unverified_header.get("kid")), None)
    if jwk is None:
        # Keys may have rotated since our cache was populated — refresh once and retry.
        _jwks_cache["keys"] = None
        keys = await _fetch_jwks()
        jwk = next((k for k in keys if k["kid"] == unverified_header.get("kid")), None)
        if jwk is None:
            raise ApiError(status_code=401, code="invalid_google_token", message="Google sign-in failed. Please try again.")

    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
    try:
        claims = jwt.decode(
            id_token_str,
            key=public_key,
            algorithms=["RS256"],
            audience=settings.google_client_id,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.InvalidTokenError:
        raise ApiError(status_code=401, code="invalid_google_token", message="Google sign-in failed. Please try again.")

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise ApiError(status_code=401, code="invalid_google_token", message="Google sign-in failed. Please try again.")
    return claims


def _require_verified_email(claims: dict) -> None:
    """
    Section 6.5 step 6 / 12.10: "`email_verified` must be `true` — reject
    sign-in otherwise". Kept as its own step (called from handle_callback,
    not inlined into _verify_id_token) so the business rule is exercised
    identically regardless of which JWT/JWKS-verification internals are
    mocked out in tests (see tests/test_google_oauth.py).
    """
    if not claims.get("email_verified"):
        raise ApiError(
            status_code=401,
            code="google_email_unverified",
            message="Your Google email isn't verified. Please verify it with Google and try again.",
        )


async def handle_callback(db: Session, redis_client, *, code: str, state: str) -> dict:
    """
    Single entry point for `GET /auth/google/callback` (Section 6.5 steps
    3-9) — dispatches on the pending record's `intent` since Google only
    redirects to one registered URI (see build_authorization_url).

    Returns a dict describing what the router should do next:
      {"kind": "login", "user": User, "is_new_user": bool}
      {"kind": "link", "user": User}
    """
    pending = _consume_pending_auth(redis_client, state)
    token_response = await _exchange_code(code=code, code_verifier=pending.code_verifier)
    claims = await _verify_id_token(token_response["id_token"])
    _require_verified_email(claims)

    if pending.intent == "link":
        user = _apply_google_link(db, user_id=pending.linking_user_id, google_sub=claims["sub"])
        return {"kind": "link", "user": user}

    user, is_new_user = _match_or_create_user(db, claims)
    return {"kind": "login", "user": user, "is_new_user": is_new_user}


def _match_or_create_user(db: Session, claims: dict) -> tuple[User, bool]:
    """
    Runs steps 6-7 of Section 6.5 for the anonymous sign-in/signup button.
    Returns (user, is_new_user). Raises ApiError(code="email_exists_as_password_account")
    on the no-auto-merge collision case (Section 6.5 step 7 / 12.10).
    """
    google_sub = claims["sub"]
    email = claims["email"].strip().lower()
    name = claims.get("name") or email.split("@")[0]

    existing_by_sub = db.execute(select(User).where(User.google_sub == google_sub)).scalar_one_or_none()
    if existing_by_sub is not None:
        return existing_by_sub, False

    existing_by_email = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing_by_email is not None:
        # Section 6.5 step 7 / 12.10: never auto-merge by email alone — this
        # blocks the classic OAuth account-takeover pattern where an
        # attacker controls a Google account matching a victim's email.
        raise ApiError(
            status_code=409,
            code="email_exists_as_password_account",
            message="An account with this email already exists. Log in with your password to link Google, or contact support.",
        )

    user = User(
        name=name,
        email=email,
        auth_provider=AuthProvider.GOOGLE,
        google_sub=google_sub,
        email_verified=True,
        password_hash=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, True


def issue_login_ticket(redis_client, *, access_token: str, refresh_token: str) -> str:
    ticket = secrets.token_urlsafe(32)
    redis_client.setex(
        _ticket_key(ticket), _TICKET_TTL_SECONDS, json.dumps({"accessToken": access_token, "refreshToken": refresh_token})
    )
    return ticket


def redeem_login_ticket(redis_client, ticket: str) -> dict:
    key = _ticket_key(ticket)
    payload = redis_client.get(key)
    if payload is None:
        raise ApiError(status_code=400, code="invalid_ticket", message="This sign-in link has expired. Please try again.")
    redis_client.delete(key)
    return json.loads(payload)


def _apply_google_link(db: Session, *, user_id: str, google_sub: str) -> User:
    """Second half of `POST /auth/google/link` (Section 7.1A), run from the shared callback (see handle_callback)."""
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(status_code=400, code="invalid_oauth_state", message="This linking attempt has expired. Please try again.")

    conflict = db.execute(select(User).where(User.google_sub == google_sub)).scalar_one_or_none()
    if conflict is not None and conflict.id != user.id:
        raise ApiError(status_code=409, code="google_account_already_linked", message="This Google account is already linked to another user.")

    user.google_sub = google_sub
    user.auth_provider = AuthProvider.BOTH if user.password_hash else AuthProvider.GOOGLE
    db.commit()
    db.refresh(user)
    return user


def begin_link_flow(redis_client, *, user: User, current_password: str) -> str:
    """
    `POST /auth/google/link/init` (Section 7.1A's step-up-auth requirement,
    implemented as its own init step since the OAuth redirect that follows
    can't carry a Bearer token — see build_authorization_url's docstring).
    """
    if not user.password_hash or not verify_password(current_password, user.password_hash):
        raise ApiError(status_code=401, code="invalid_password", message="Incorrect password.")

    return build_authorization_url(redis_client, intent="link", linking_user_id=str(user.id))


def unlink_google_account(db: Session, user: User) -> User:
    """`DELETE /auth/google/unlink` — blocked if it would leave the account with zero auth methods (Section 8, 12.10)."""
    if not user.password_hash:
        raise ApiError(
            status_code=400,
            code="password_required_before_unlink",
            message="Set a password before unlinking Google, so you don't lose access to your account.",
        )
    user.google_sub = None
    user.auth_provider = AuthProvider.PASSWORD
    db.commit()
    db.refresh(user)
    return user
