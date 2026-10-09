"""
Standard response envelope (`{success, data?, error?}`, Section 7) plus the
exception type/handlers that produce it consistently for every route.
"""
import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("mockmateai")


class ApiError(Exception):
    """Raise from any route/service to produce the standard error envelope."""

    def __init__(self, *, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def success(data: Any = None) -> dict:
    return {"success": True, "data": data}


def error_body(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_body("validation_error", "One or more fields are invalid."),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content=error_body("http_error", str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        # Section 12.9: never leak stack traces/internals to the client —
        # log the full exception server-side against a correlation ID and
        # return only that ID to the caller.
        correlation_id = str(uuid.uuid4())
        logger.exception("Unhandled exception [correlation_id=%s]", correlation_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body("internal_error", f"Something went wrong. Reference: {correlation_id}"),
        )
