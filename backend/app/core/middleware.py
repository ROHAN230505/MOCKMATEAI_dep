"""
Cross-cutting HTTP middleware (Section 12.7):
- Security headers on every response.
- A request-correlation ID for traceability in logs (Section 12.7).
"""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("mockmateai.access")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Sets the OWASP-aligned baseline from Section 12.7 on every response.
    CSP is intentionally conservative (same-origin only) since this API
    serves JSON, not HTML — the frontend app sets its own CSP separately.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Stamps every request with an ID, exposed both in logs and the response header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.correlation_id = correlation_id
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = correlation_id
        logger.info(
            "%s %s -> %s (%.1fms) [request_id=%s]",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            correlation_id,
        )
        return response
