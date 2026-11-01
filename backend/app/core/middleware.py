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


# The only two routes that serve HTML rather than JSON. FastAPI builds both
# pages itself and loads their CSS and JS from jsDelivr.
_DOC_PATHS = frozenset({"/docs", "/redoc"})

# `default-src 'none'` is right for a JSON API and wrong for those two pages:
# it blocks the very bundle that renders them, and the result is a blank white
# screen with no error -- the HTML arrives, the script never does, and nothing
# in the UI says why. So the docs get a CSP that permits exactly their own
# assets and nothing else, rather than the API-wide policy being loosened for
# everyone or the pages being left broken.
_DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' https://fastapi.tiangolo.com data:; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    # Swagger's "Try it out" calls this API from the page itself.
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Sets the OWASP-aligned baseline from Section 12.7 on every response.

    CSP is intentionally conservative (same-origin only) since this API serves
    JSON, not HTML — the frontend app sets its own CSP separately. The two
    interactive documentation pages are the exception, and are narrowed to the
    sources they actually use rather than being exempted.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            _DOCS_CSP if request.url.path in _DOC_PATHS else "default-src 'none'; frame-ancestors 'none'"
        )
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
