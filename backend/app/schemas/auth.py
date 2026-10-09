from pydantic import EmailStr, Field, field_validator

from app.schemas.common import CamelModel
from app.schemas.user import UserPublic


def _normalize_email(value: str) -> str:
    return value.strip().lower()


class SignupRequest(CamelModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)

    _normalize = field_validator("email")(lambda v: _normalize_email(v))


class LoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)

    _normalize = field_validator("email")(lambda v: _normalize_email(v))


class CheckAccountTypeRequest(CamelModel):
    email: EmailStr

    _normalize = field_validator("email")(lambda v: _normalize_email(v))


class CheckAccountTypeResponse(CamelModel):
    # Deliberately narrow: only the auth method, never whether the account
    # exists at all (Section 7.1 / 12.3 — avoid an enumeration oracle).
    auth_method: str  # "password" | "google" | "unknown"


class RefreshRequest(CamelModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(CamelModel):
    refresh_token: str = Field(min_length=1)


class ForgotPasswordRequest(CamelModel):
    email: EmailStr

    _normalize = field_validator("email")(lambda v: _normalize_email(v))


class ResetPasswordRequest(CamelModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=256)


class TokenPairResponse(CamelModel):
    user: UserPublic
    access_token: str
    refresh_token: str


class AccessTokenResponse(CamelModel):
    access_token: str


class GoogleAuthUrlResponse(CamelModel):
    auth_url: str


class GoogleLinkInitRequest(CamelModel):
    """
    `POST /auth/google/link/init` — the step-up-auth half of Section 7.1A's
    `/auth/google/link`. Split into its own init step because the OAuth
    redirect that follows can't carry a Bearer token; see
    services/google_oauth_service.py's `build_authorization_url` docstring
    for the full rationale.
    """

    current_password: str = Field(min_length=1)


class GoogleExchangeRequest(CamelModel):
    """
    Exchanges the one-time ticket issued at the end of the redirect-based
    Google OAuth flow (see routers/auth_google.py) for our own first-party
    token pair. Not a literal endpoint name from Section 7.1A, but a
    necessary wire-level detail: the spec states the callback is
    "server-to-server ... not called by frontend directly", so the SPA
    needs *some* way to pick up the issued tokens after the browser
    redirect completes without them ever appearing in a URL/browser
    history (Section 12.3).
    """

    ticket: str = Field(min_length=1)
