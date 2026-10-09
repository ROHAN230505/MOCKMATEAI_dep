"""
Auth business logic (Section 7.1, 12.1). Kept independent of FastAPI
request/response types so it's directly unit-testable (see tests/).
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FAILED_LOGIN_LOCKOUT_THRESHOLD, LOCKOUT_LADDER_MINUTES
from app.core.responses import ApiError
from app.core.security import (
    create_access_token,
    generate_password_reset_token,
    generate_refresh_token,
    hash_password,
    hash_password_reset_token,
    hash_refresh_token,
    validate_password_policy,
    common_password_reason,
    verify_password,
)
from app.core.timeutils import utcnow
from app.config import get_settings
from app.models.enums import AuthProvider
from app.models.user import RefreshToken, User


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email.strip().lower())).scalar_one_or_none()


def create_user(db: Session, *, name: str, email: str, password: str) -> User:
    email = email.strip().lower()
    existing = get_user_by_email(db, email)
    if existing is not None:
        if existing.auth_provider == AuthProvider.GOOGLE and not existing.password_hash:
            raise ApiError(
                status_code=409,
                code="google_account_exists",
                message="This email is registered via Google. Try 'Continue with Google' instead.",
            )
        raise ApiError(status_code=409, code="email_already_registered", message="Email already registered.")

    policy_errors = validate_password_policy(password, email=email, name=name)
    if policy_errors:
        raise ApiError(status_code=400, code="weak_password", message=" ".join(policy_errors))

    user = User(
        name=name.strip(),
        email=email,
        password_hash=hash_password(password),
        auth_provider=AuthProvider.PASSWORD,
        email_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _lockout_duration_minutes(failed_attempts: int) -> int:
    overflow = failed_attempts - FAILED_LOGIN_LOCKOUT_THRESHOLD
    index = min(max(overflow, 0), len(LOCKOUT_LADDER_MINUTES) - 1)
    return LOCKOUT_LADDER_MINUTES[index]


def authenticate_user(db: Session, *, email: str, password: str) -> User:
    """
    Raises ApiError on any failure. Error messages deliberately avoid
    revealing whether the email exists (Section 12.1/12.3), except for the
    one intentional, spec-called-out exception: a Google-only account gets
    a distinguishing message rather than a generic wrong-password error.
    """
    user = get_user_by_email(db, email)

    if user is not None and user.locked_until is not None and user.locked_until > utcnow():
        raise ApiError(
            status_code=423,
            code="account_locked",
            message="Too many failed attempts. Please try again later.",
        )

    if user is not None and user.auth_provider == AuthProvider.GOOGLE and not user.password_hash:
        raise ApiError(
            status_code=401,
            code="google_only_account",
            message="This account uses Google sign-in. Continue with Google above.",
        )

    password_ok = user is not None and user.password_hash is not None and verify_password(password, user.password_hash)

    if not password_ok:
        if user is not None:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= FAILED_LOGIN_LOCKOUT_THRESHOLD:
                minutes = _lockout_duration_minutes(user.failed_login_attempts)
                user.locked_until = utcnow() + timedelta(minutes=minutes)
            db.commit()
        raise ApiError(status_code=401, code="invalid_credentials", message="Incorrect email or password.")

    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    return user


def issue_token_pair(db: Session, user: User) -> tuple[str, str]:
    settings = get_settings()
    access_token = create_access_token(user_id=str(user.id))
    raw_refresh_token = generate_refresh_token()

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh_token),
            expires_at=utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )
    db.commit()
    return access_token, raw_refresh_token


def rotate_refresh_token(db: Session, raw_refresh_token: str) -> tuple[str, str, User]:
    """
    Validates + rotates a refresh token (Section 12.1: "rotated on every
    use; old token invalidated the instant a new one is issued"). If a
    token that was already revoked is presented again — a signal that a
    stolen token is being replayed after the legitimate client already
    rotated past it — every refresh token for that user is revoked as a
    precaution, forcing a fresh login everywhere.
    """
    token_hash = hash_refresh_token(raw_refresh_token)
    token_row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).scalar_one_or_none()

    invalid = ApiError(status_code=401, code="invalid_refresh_token", message="Please log in again.")

    if token_row is None:
        raise invalid

    if token_row.revoked:
        db.execute(
            RefreshToken.__table__.update().where(RefreshToken.user_id == token_row.user_id).values(revoked=True)
        )
        db.commit()
        raise invalid

    if token_row.expires_at < utcnow():
        raise invalid

    user = db.get(User, token_row.user_id)
    if user is None:
        raise invalid

    token_row.revoked = True
    db.commit()

    access_token, new_raw_refresh = issue_token_pair(db, user)
    return access_token, new_raw_refresh, user


def logout(db: Session, raw_refresh_token: str) -> None:
    token_hash = hash_refresh_token(raw_refresh_token)
    token_row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).scalar_one_or_none()
    if token_row is not None:
        token_row.revoked = True
        db.commit()


def logout_all_devices(db: Session, user: User) -> None:
    db.execute(RefreshToken.__table__.update().where(RefreshToken.user_id == user.id).values(revoked=True))
    db.commit()


def request_password_reset(db: Session, email: str) -> None:
    """
    Always a no-op from the caller's perspective on success/failure alike —
    the router returns the same 200 regardless (Section 7.1, 12.3). Emailing
    the raw token is a Notification Service concern (Section 6.1) not yet
    built in Phase 1, so for local development the raw token is logged
    server-side instead of sent — see routers/auth.py.
    """
    settings = get_settings()
    user = get_user_by_email(db, email)
    if user is None:
        return None

    raw_token = generate_password_reset_token()
    user.reset_token_hash = hash_password_reset_token(raw_token)
    user.reset_token_expires_at = utcnow() + timedelta(
        minutes=settings.password_reset_token_expire_minutes
    )
    db.commit()
    return raw_token


def reset_password(db: Session, *, token: str, new_password: str) -> None:
    # Checked BEFORE the token is looked up, deliberately. The identity-aware
    # half runs afterwards, once the token is known good -- see below for why
    # the split matters.
    policy_errors = validate_password_policy(new_password)
    if policy_errors:
        raise ApiError(status_code=400, code="weak_password", message=" ".join(policy_errors))

    token_hash = hash_password_reset_token(token)
    user = db.execute(select(User).where(User.reset_token_hash == token_hash)).scalar_one_or_none()

    invalid = ApiError(status_code=400, code="invalid_reset_token", message="This reset link is invalid or has expired.")
    if user is None or user.reset_token_expires_at is None:
        raise invalid
    if user.reset_token_expires_at < utcnow():
        raise invalid

    """
    The identity check, and the reason it is down here rather than above.

    Rejecting a password for containing the user's own name needs the user,
    and the user needs a valid token. The tempting fix -- move the whole policy
    check below the lookup -- would build a token oracle: an attacker submits a
    deliberately weak password with a guessed token, and a `weak_password`
    reply rather than `invalid_reset_token` confirms the guess was right.

    Splitting it keeps that shut. A weak password always fails above,
    regardless of the token, so the response says nothing about token validity;
    and by the time this runs, the caller already holds a valid token for the
    account whose name it is being compared against.
    """
    identity_reason = common_password_reason(new_password, email=user.email, name=user.name)
    if identity_reason:
        raise ApiError(status_code=400, code="weak_password", message=identity_reason)

    user.password_hash = hash_password(new_password)
    if user.auth_provider == AuthProvider.GOOGLE:
        user.auth_provider = AuthProvider.BOTH
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    # Section 12.1: rotating credentials invalidates existing sessions.
    logout_all_devices(db, user)


def check_account_type(db: Session, email: str) -> str:
    """Returns 'password' | 'google' | 'unknown' — never anything else (Section 7.1)."""
    user = get_user_by_email(db, email)
    if user is None:
        return "unknown"
    if user.auth_provider == AuthProvider.GOOGLE and not user.password_hash:
        return "google"
    return "password"
