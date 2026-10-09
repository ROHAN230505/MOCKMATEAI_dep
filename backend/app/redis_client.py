"""
Redis client wiring.

Exposed as a FastAPI dependency (`get_redis`) rather than a bare module
singleton so tests can swap in a fakeredis instance via
`app.dependency_overrides[get_redis] = ...` without touching real Redis.
"""
from collections.abc import Generator
from functools import lru_cache

import redis

from app.config import get_settings


@lru_cache
def _client() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.effective_redis_url, decode_responses=True)


def get_redis() -> Generator[redis.Redis, None, None]:
    yield _client()
