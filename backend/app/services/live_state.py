"""
The scratch state a live interview carries between client events.

Only one thing lives here: the shared code panel's latest content (Section 9.9).
It is deliberately not a database column per update — Section 8 stores the
snapshot on `interview_answers`, so what matters is the content at the moment an
answer is submitted, not every intermediate keystroke.

Two implementations, because the transports differ in what they can hold:

  - Over a WebSocket the connection itself is the scope, so an attribute is
    exactly right and costs nothing.
  - Over HTTP there is no connection to hang it on. A candidate can share code
    in one request and answer in a later one, so it has to outlive the request.

Redis rather than a module-level dict: a dict is wrong the moment there is more
than one worker process, and it would fail in the way that is hardest to spot —
correct on a developer's machine, intermittently empty in production.
"""
from typing import Protocol

# Comfortably longer than the longest interview (Section 4.3 caps at 45 minutes)
# so the key cannot expire mid-session, but not unbounded.
PANEL_TTL_SECONDS = 4 * 60 * 60


class LiveState(Protocol):
    def get_panel(self) -> str | None: ...

    def set_panel(self, value: str | None) -> None: ...


class MemoryLiveState:
    """Scoped to one WebSocket connection."""

    def __init__(self) -> None:
        self._panel: str | None = None

    def get_panel(self) -> str | None:
        return self._panel

    def set_panel(self, value: str | None) -> None:
        self._panel = value


class RedisLiveState:
    """Scoped to the session, so it survives between HTTP requests."""

    def __init__(self, redis, session_id) -> None:
        self._redis = redis
        self._key = f"interview:{session_id}:code_panel"

    def get_panel(self) -> str | None:
        return self._redis.get(self._key) or None

    def set_panel(self, value: str | None) -> None:
        if value is None:
            self._redis.delete(self._key)
        else:
            self._redis.set(self._key, value, ex=PANEL_TTL_SECONDS)
