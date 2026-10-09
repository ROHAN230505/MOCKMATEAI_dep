"""
In-process registry enforcing "1 active connection per session per user"
(Section 12.1A). In-memory is a deliberate Phase-2-scale choice — a
multi-instance deployment would need this in Redis instead, same as the
rate limiter (Section 12.1A already notes per-instance memory is wrong for
rate limiting generally; this registry has the same constraint but isn't
on the critical security path the way rate limiting is, so it's deferred
until this actually runs behind more than one backend process).
"""
import time

_active_connections: dict[str, object] = {}
_event_timestamps: dict[str, list[float]] = {}


def try_register(session_id: str) -> bool:
    if session_id in _active_connections:
        return False
    _active_connections[session_id] = True
    return True


def is_registered(session_id: str) -> bool:
    """
    Whether a live socket currently holds this session.

    Read by the HTTP fallback transport, which has no connection of its own to
    register: without this, a session could be driven over a socket and over
    HTTP at the same time and the two clients would interleave turns.
    """
    return session_id in _active_connections


def unregister(session_id: str) -> None:
    _active_connections.pop(session_id, None)
    _event_timestamps.pop(session_id, None)


def allow_event(session_id: str, *, limit: int = 20, window_seconds: float = 60.0) -> bool:
    """Sliding-window limiter for low-cost control events (Section 12.1A: 20/min per session)."""
    now = time.monotonic()
    timestamps = [t for t in _event_timestamps.get(session_id, []) if now - t < window_seconds]
    if len(timestamps) >= limit:
        _event_timestamps[session_id] = timestamps
        return False
    timestamps.append(now)
    _event_timestamps[session_id] = timestamps
    return True
