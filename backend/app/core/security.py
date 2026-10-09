"""
Password hashing, JWT issuance/verification, and refresh-token hashing
(Section 12.1).

- Passwords: argon2id via `argon2-cffi` (the spec's preferred algorithm).
- Access tokens: short-lived JWTs signed RS256 (asymmetric — downstream
  services could verify with only the public key, Section 12.1).
- Refresh tokens: opaque random strings; only an HMAC-SHA256 digest (keyed
  by `MOCKMATEAI_REFRESH_TOKEN_SECRET`) is ever persisted, never the raw
  token — so a DB leak alone isn't enough to mint a valid session.
"""
import functools
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from app.config import get_settings
from app.core.password_blocklist import common_password_reason

_hasher = PasswordHasher()


# --------------------------------------------------------------------------
# Password hashing
# --------------------------------------------------------------------------
def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Call after a successful verify; re-hash+save if argon2 params have since been strengthened."""
    return _hasher.check_needs_rehash(password_hash)


# --------------------------------------------------------------------------
# Password policy (Section 12.1) — min 8 chars, >=1 digit, >=1 symbol
# --------------------------------------------------------------------------
_SYMBOLS = set("!@#$%^&*()_+-=[]{}|;:'\",.<>/?`~\\")


def validate_password_policy(
    password: str,
    *,
    email: str | None = None,
    name: str | None = None,
) -> list[str]:
    """
    Returns a list of human-readable violations; empty list == compliant.

    Composition rules alone are close to worthless, and this policy proved it:
    length-plus-digit-plus-symbol accepted `Password1!`, `Qwerty12!`,
    `letmein1!`, `iloveyou1!` and `P@ssw0rd`. Every one of those sits at the top
    of every published breach corpus. A rule that demands a symbol and then
    waves through `P@ssw0rd` has taught a ritual, not bought any safety.

    So composition is now the floor rather than the whole test, and the
    guessability check does the real work. `email` and `name` are optional
    because password *reset* has the account in hand and signup does not
    always; when they are supplied, a password containing the user's own
    identity is rejected too.
    """
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not any(ch.isdigit() for ch in password):
        errors.append("Password must contain at least one number.")
    if not any(ch in _SYMBOLS for ch in password):
        errors.append("Password must contain at least one symbol.")

    # Only when the shape is right: telling someone their 5-character password
    # is also a common one is two complaints about the same keystroke.
    if not errors:
        reason = common_password_reason(password, email=email, name=name)
        if reason:
            errors.append(reason)
    return errors


async def is_breached_password(password: str) -> bool:
    """
    Optional k-anonymity breached-password check (HaveIBeenPwned-style API),
    gated by MOCKMATEAI_ENABLE_BREACHED_PASSWORD_CHECK (default off — see
    app/config.py) so local dev/tests never require outbound network access.
    Only the first 5 hex chars of the SHA-1 hash ever leave this process.
    """
    settings = get_settings()
    if not settings.enable_breached_password_check:
        return False

    import httpx

    # `usedforsecurity=False` is required, not cosmetic. SHA-1 is mandated by
    # the HaveIBeenPwned range protocol -- it is a lookup key, never a stored
    # credential -- and the flag is what lets this run on a FIPS-mode build,
    # where an unflagged SHA-1 raises instead of hashing.
    sha1 = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"https://api.pwnedpasswords.com/range/{prefix}")
            resp.raise_for_status()
    except httpx.HTTPError:
        # Fail open: never block signup because a third-party API is down.
        return False

    for line in resp.text.splitlines():
        candidate_suffix, _, _count = line.partition(":")
        if candidate_suffix == suffix:
            return True
    return False


# --------------------------------------------------------------------------
# JWT access tokens (RS256)
# --------------------------------------------------------------------------
def _normalise_pem(raw: str) -> str:
    r"""
    Repair a PEM that has travelled through an environment variable.

    Hosting dashboards are inconsistent about multi-line secrets: some keep the
    newlines, some collapse them to a literal backslash-n, and a key with its
    line breaks lost is not a valid PEM -- the parser rejects it with a message
    about the DER encoding that says nothing about the real cause. Putting the
    repair here means that is a non-issue rather than an hour of confusion.
    """
    pem = raw.strip().strip('"').strip("'")
    if "\\n" in pem and "-----BEGIN" in pem:
        pem = pem.replace("\\n", chr(10))
    return pem if pem.endswith(chr(10)) else pem + chr(10)


@functools.lru_cache
def _load_private_key() -> str:
    """
    The signing key, from the environment first and the filesystem second.

    The order matters for deployment. A platform that builds from git has no
    `dev_keys/` directory -- the keypair is a secret and is correctly absent
    from the repository -- so a path-only loader means the app cannot start at
    all. Supplying the PEM as an environment variable is the standard way to
    get a secret onto such a platform, and locally the file path keeps working
    untouched.
    """
    settings = get_settings()
    if settings.jwt_private_key.strip():
        return _normalise_pem(settings.jwt_private_key)
    return Path(settings.jwt_private_key_path).read_text()


@functools.lru_cache
def _load_public_key() -> str:
    settings = get_settings()
    if settings.jwt_public_key.strip():
        return _normalise_pem(settings.jwt_public_key)
    return Path(settings.jwt_public_key_path).read_text()


def create_access_token(*, user_id: str, extra_claims: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _load_private_key(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.InvalidTokenError (or a subclass) on any failure — caller maps to 401."""
    settings = get_settings()
    payload = jwt.decode(token, _load_public_key(), algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return payload


# --------------------------------------------------------------------------
# Opaque tokens (refresh tokens, password-reset tokens) — a random string is
# handed to the client; only its HMAC-SHA256 digest (keyed by the server-side
# `refresh_token_secret` pepper) is ever persisted, never the raw value.
# Shared implementation, type-specific names at the call site for clarity.
# --------------------------------------------------------------------------
def _generate_opaque_token() -> str:
    return secrets.token_urlsafe(64)


def hash_opaque_token(raw_token: str) -> str:
    settings = get_settings()
    digest = hmac.new(settings.refresh_token_secret.encode("utf-8"), raw_token.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


def opaque_token_matches(raw_token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_opaque_token(raw_token), stored_hash)


generate_refresh_token = _generate_opaque_token
hash_refresh_token = hash_opaque_token
refresh_token_matches = opaque_token_matches
generate_password_reset_token = _generate_opaque_token
hash_password_reset_token = hash_opaque_token
password_reset_token_matches = opaque_token_matches


# --------------------------------------------------------------------------
# Misc timing-safe helpers (Section 12.9)
# --------------------------------------------------------------------------
def constant_time_str_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
