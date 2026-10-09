"""
AI-cost-sensitive per-user quota (Section 12.1A).

Section 12.1A's AI-cost-sensitive tier calls for "a per-user quota (e.g. a
fixed number of interview minutes / resume analyses / hints per day on top of
raw rate limiting) — this is a **cost-control** limit, not just abuse
prevention."

That "on top of" matters: the Section 12.1A middleware already throttles
request *frequency* for `/interviews/start`. This is a different axis —
cumulative interview minutes per day — because a user can stay comfortably
under any per-minute request limit while still starting enough sessions to
run up a real LLM bill.

Redis-backed with an atomic INCRBY + EXPIRE so the count is correct across
backend instances and under concurrent starts (Section 12.1A: "Rate-limit
counters must be atomic ... to avoid race conditions under concurrent
requests undercounting the limit").
"""
import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.core.responses import ApiError

logger = logging.getLogger("mockmateai.ai_quota")

_QUOTA_TTL_SECONDS = 60 * 60 * 26  # a day plus slack, so the key outlives its window


def _quota_key(user_id: str) -> str:
    # Section 12.5's Redis-injection note: the user-supplied portion is a UUID
    # from a verified JWT, interpolated into a fixed template — never raw text.
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"ai_quota:interview_minutes:{day}:{user_id}"


def consume_interview_minutes(redis_client, user_id: str, minutes: int) -> None:
    """
    Reserves `minutes` against today's allowance, raising 429 if it would
    exceed the cap.

    Reserved up front at session start rather than metered as the interview
    runs: the cost is committed the moment the session begins generating LLM
    turns, and a mid-interview quota rejection would mean killing a session
    the candidate is partway through.
    """
    settings = get_settings()
    cap = settings.ai_daily_interview_minutes_per_user
    if cap <= 0:
        return  # quota disabled

    key = _quota_key(str(user_id))
    try:
        used = redis_client.incrby(key, minutes)
        # Only set the TTL on the first write of the day; re-setting it on
        # every call would slide the window forward indefinitely and the
        # allowance would never actually reset.
        if used == minutes:
            redis_client.expire(key, _QUOTA_TTL_SECONDS)
    except Exception:
        # Fail OPEN. A Redis outage must not stop candidates interviewing —
        # this is a cost-control limit, not a security boundary, and the
        # security-relevant limits (auth rate limiting, Section 12.1A's strict
        # tier) are enforced separately.
        logger.exception("AI quota check failed; allowing the request [user_id=%s]", user_id)
        return

    if used > cap:
        # Give back the reservation so a rejected attempt doesn't permanently
        # burn allowance the candidate never got to use.
        try:
            redis_client.incrby(key, -minutes)
        except Exception:
            logger.exception("Failed to refund AI quota reservation [user_id=%s]", user_id)
        raise ApiError(
            status_code=429,
            code="ai_quota_exceeded",
            message=(
                f"You've used your {cap} minutes of AI interview time for today. "
                "Please try again tomorrow."
            ),
        )


def _export_quota_key(user_id: str) -> str:
    hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    return f"quota:exports:{hour}:{user_id}"


def consume_export(redis_client, user_id: str) -> None:
    """
    Section 12.1A's export limit: 20 per hour per user.

    Keyed per user rather than per IP like the middleware tier, because the cost
    being controlled is server-side work (PDF rendering, full-transcript reads)
    attributable to an account — and a shared campus or office NAT would
    otherwise make one user's downloads exhaust everyone else's allowance.

    Same atomic INCRBY + first-write-only EXPIRE as the interview quota above,
    and the same fail-open posture: a Redis outage must not stop someone
    downloading their own interview transcript.
    """
    settings = get_settings()
    cap = settings.exports_per_hour_per_user
    if cap <= 0:
        return

    key = _export_quota_key(str(user_id))
    try:
        used = redis_client.incrby(key, 1)
        if used == 1:
            redis_client.expire(key, 60 * 60 * 2)
    except Exception:
        logger.exception("Export quota check failed; allowing the request [user_id=%s]", user_id)
        return

    if used > cap:
        raise ApiError(
            status_code=429,
            code="export_quota_exceeded",
            message=f"You've reached the limit of {cap} downloads per hour. Please try again shortly.",
        )


def _hint_quota_key(user_id: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"quota:dsa_hints:{day}:{user_id}"


def consume_hint(redis_client, user_id: str) -> None:
    """
    Section 12.1A's per-day hint allowance.

    A hint is a real provider call, so it is metered on the same axis as
    interview minutes rather than left to the per-IP request limiter: a candidate
    holding a hint button could otherwise stay under any frequency limit and
    still run up a bill, and the cost is attributable to an account.

    Same atomic INCRBY with a first-write-only EXPIRE, and the same fail-open
    posture as the other two quotas: if Redis is down, a candidate stuck on a
    problem still gets their nudge.
    """
    settings = get_settings()
    cap = settings.dsa_hints_per_day_per_user
    if cap <= 0:
        return

    key = _hint_quota_key(str(user_id))
    try:
        used = redis_client.incrby(key, 1)
        if used == 1:
            redis_client.expire(key, _QUOTA_TTL_SECONDS)
    except Exception:
        logger.exception("Hint quota check failed; allowing the request [user_id=%s]", user_id)
        return

    if used > cap:
        raise ApiError(
            status_code=429,
            code="hint_quota_exceeded",
            message=f"You've used all {cap} hints for today. They reset tomorrow.",
        )


def _resume_quota_key(user_id: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"quota:resume_analyses:{day}:{user_id}"


def consume_resume_analysis(redis_client, user_id: str) -> None:
    """
    Section 12.1A's per-day resume-analysis allowance.

    Deterministic analysis costs no provider call today, so this is a work limit
    rather than a bill limit -- but it is the third quota Section 12.1A names by
    example, and an endpoint that parses tens of thousands of characters is worth
    bounding per account rather than only per IP.

    Same atomic INCRBY, same fail-open posture as the other two.
    """
    settings = get_settings()
    cap = settings.resume_analyses_per_day_per_user
    if cap <= 0:
        return

    key = _resume_quota_key(str(user_id))
    try:
        used = redis_client.incrby(key, 1)
        if used == 1:
            redis_client.expire(key, _QUOTA_TTL_SECONDS)
    except Exception:
        logger.exception("Resume quota check failed; allowing the request [user_id=%s]", user_id)
        return

    if used > cap:
        raise ApiError(
            status_code=429,
            code="resume_quota_exceeded",
            message=f"You've analysed {cap} resumes today. The limit resets tomorrow.",
        )


def remaining_interview_minutes(redis_client, user_id: str) -> int | None:
    """Remaining allowance for display; None when the quota is disabled or unreadable."""
    settings = get_settings()
    cap = settings.ai_daily_interview_minutes_per_user
    if cap <= 0:
        return None
    try:
        used = int(redis_client.get(_quota_key(str(user_id))) or 0)
    except Exception:
        return None
    return max(0, cap - used)
