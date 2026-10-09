"""
Platform-wide rate limiting (Section 12.1A).

Implemented as shared middleware (`slowapi`, a Starlette/FastAPI port of
Flask-Limiter) backed by Redis via the `limits` library, so counters are
correct across multiple backend instances rather than per-process memory —
exactly what Section 12.1A calls for. Each route in app/routers/ applies
its own `@limiter.limit(...)` decorator using the named constants below,
matched 1:1 to the table in Section 12.1A.

Per-account lockout (on top of this per-IP layer) lives separately in
app/services/auth_service.py, per the spec's "on top of, not instead of"
requirement for login specifically.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings


def _storage_uri() -> str:
    return get_settings().effective_rate_limit_storage_uri


limiter = Limiter(key_func=get_remote_address, storage_uri=_storage_uri())

# --- Auth (Section 7.1 / 12.1A) — keyed by IP via `limiter`'s default key_func ---
SIGNUP_RATE_LIMIT = "5/hour"
LOGIN_RATE_LIMIT = "5/15minutes"
CHECK_ACCOUNT_TYPE_RATE_LIMIT = "10/minute"
REFRESH_RATE_LIMIT = "30/hour"
FORGOT_PASSWORD_RATE_LIMIT = "3/hour"
RESET_PASSWORD_RATE_LIMIT = "5/hour"

# --- Google OAuth (Section 7.1A / 12.1A) ---
GOOGLE_INIT_RATE_LIMIT = "20/hour"
GOOGLE_CALLBACK_RATE_LIMIT = "20/hour"
GOOGLE_LINK_RATE_LIMIT = "5/hour"
GOOGLE_UNLINK_RATE_LIMIT = "5/hour"

# The OAuth ticket exchange. Tight, because it is an authentication endpoint
# that takes an opaque ticket and returns a token pair -- exactly the shape you
# brute-force. It had no limit at all, which made it the softest target in the
# auth surface.
GOOGLE_EXCHANGE_RATE_LIMIT = "20/hour"

# --- Destructive account actions ---
# Deleting an account is irreversible and cascades. There is no legitimate
# reason to issue it repeatedly, and a low ceiling costs a real user nothing.
ACCOUNT_DELETE_RATE_LIMIT = "5/hour"

# Writing a fresh problem is two provider round trips and several seconds.
# The standard tier would allow a hundred a minute, which is neither
# affordable nor anything a person does deliberately.
GENERATE_PROBLEM_RATE_LIMIT = "10/hour"

# --- Everything else authenticated (Section 12.1A "Standard" tier) ---
STANDARD_RATE_LIMIT = "100/minute"
