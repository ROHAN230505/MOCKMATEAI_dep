"""Shared FastAPI dependencies: current-user resolution and role gating."""
import jwt
from fastapi import Depends, Query, WebSocket, WebSocketException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.responses import ApiError
from app.core.security import decode_access_token
from app.database import get_db
from app.models.enums import UserRole
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise ApiError(status_code=401, code="unauthorized", message="Authentication required.")

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise ApiError(status_code=401, code="invalid_token", message="Your session has expired. Please log in again.")

    user = db.get(User, payload["sub"])
    if user is None:
        raise ApiError(status_code=401, code="invalid_token", message="Your session has expired. Please log in again.")
    return user


def get_current_user_ws(
    websocket: WebSocket,
    token: str = Query(...),
    db: Session = Depends(get_db),
) -> User:
    """
    Browsers' native WebSocket API can't set an Authorization header, so
    the access token travels as a query param instead (Section 7.3's
    `WS /interviews/:sessionId/live`). Raising `WebSocketException` here
    rejects the handshake before `.accept()` is ever called, same effect
    as a 401 for a normal HTTP request.
    """
    try:
        payload = decode_access_token(token)
    except jwt.InvalidTokenError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="invalid_token")

    user = db.get(User, payload["sub"])
    if user is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="invalid_token")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    # Object/role-level authorization enforced server-side (Section 12.2) —
    # never trust a client-side "is admin" flag alone.
    if user.role != UserRole.ADMIN:
        raise ApiError(status_code=403, code="forbidden", message="Admin access required.")
    return user
