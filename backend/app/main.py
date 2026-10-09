"""
MockMateAI backend — FastAPI application entrypoint.

Phase 1 (see MASTER_PROMPT.md Section 18): auth (email/password + Google
OAuth), user profile/preferences, and a dashboard summary endpoint backed
by the complete Section 8 schema.

Phase 2: the core voice interview loop — setup, a fixed pre-planned
question list (app/content/question_bank.py), and the live WebSocket
protocol (app/routers/interviews.py) — proving the real-time session
pipeline before Phase 3 adds the LLM follow-up engine on top.

Phase 3: the intelligence layer — the AI provider gateway with failover
(app/services/ai/), the LLM question/follow-up engine, and Section 10.3's
deterministic guardrails.

Phase 4: the feedback engine — deterministic scoring (Section 10.2), grounded
report generation (Section 9.8), and transcript/PDF exports (Section 7.4).

Phase 5: multimodal signals (Section 9.7) — voice prosody
(app/services/prosody_service.py) and expression signals
(app/services/expression_service.py), exposed via app/routers/signals.py and the
interview WebSocket. Together they turn the confidence and body-language
categories from unmeasured into real scores, so Section 10.2's weighted formula
now runs at its full four categories. Neither audio nor video leaves the browser:
both are analysed client-side and only aggregates are submitted.
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.core.middleware import RequestCorrelationMiddleware, SecurityHeadersMiddleware
from app.core.rate_limit import limiter
from app.core.responses import error_body, register_exception_handlers
from app.routers import (
    admin,
    aptitude,
    auth,
    auth_google,
    dashboard,
    dsa,
    feedback,
    interviews,
    recordings,
    resume,
    signals,
    users,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()

app = FastAPI(
    title="MockMateAI API",
    version="0.1.0",
    description="Phase 1 — Foundation: auth, profile/onboarding, dashboard shell.",
)

# --- Rate limiting (Section 12.1A) ---
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    # Section 12.1A: 429 + Retry-After on breach, never a silent drop or a
    # generic 500, so the frontend can show "Too many attempts, try again
    # in Xs" instead of a confusing failure. `get_expiry()` is the window
    # size (e.g. 900s for "5/15minutes") — a conservative upper bound on
    # wait time, not the precise remaining time within the current window.
    response = JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=error_body("rate_limited", "Too many requests. Please try again shortly."),
    )
    retry_after = exc.limit.limit.get_expiry() if exc.limit is not None else None
    if retry_after is not None:
        response.headers["Retry-After"] = str(int(retry_after))
    return response


app.add_middleware(SlowAPIMiddleware)

# --- CORS (Section 12.7 — explicit allowlist, never "*") ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Security headers + request correlation (Section 12.7) ---
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestCorrelationMiddleware)

register_exception_handlers(app)

API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(auth_google.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(dashboard.router, prefix=API_PREFIX)
app.include_router(interviews.router, prefix=API_PREFIX)
app.include_router(feedback.router, prefix=API_PREFIX)
app.include_router(recordings.router, prefix=API_PREFIX)
app.include_router(signals.router, prefix=API_PREFIX)
app.include_router(aptitude.router, prefix=API_PREFIX)
app.include_router(dsa.router, prefix=API_PREFIX)
app.include_router(resume.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)


@app.get("/health")
def health_check():
    return {"success": True, "data": {"status": "ok", "env": settings.env}}
