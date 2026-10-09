"""
Test configuration. Environment variables MUST be set before anything under
`app/` is imported (several modules read settings at import time, e.g. the
rate limiter's storage backend) — hence this runs at module top, ahead of
any `from app...` import.

DB: a throwaway SQLite file (not `:memory:`, so every thread FastAPI's
threadpool spins up shares the same data — see app/database.py's
check_same_thread handling) created fresh per test session.
Redis: fakeredis, swapped in via FastAPI's dependency_overrides.
Rate limiting: in-memory backend (`limits`' `memory://`) so tests don't
need a real Redis instance either.
"""
import os
import pathlib
import uuid

_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
_TEST_DB_PATH = _BACKEND_DIR / f"_test_{uuid.uuid4().hex}.db"

os.environ["MOCKMATEAI_ENV"] = "development"
os.environ["MOCKMATEAI_DB_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["MOCKMATEAI_REDIS_URL"] = "redis://localhost:6379/15"
os.environ["MOCKMATEAI_RATE_LIMIT_STORAGE_URI"] = "memory://"
os.environ["MOCKMATEAI_JWT_PRIVATE_KEY_PATH"] = str(_BACKEND_DIR / "dev_keys" / "jwt_private.pem")
os.environ["MOCKMATEAI_JWT_PUBLIC_KEY_PATH"] = str(_BACKEND_DIR / "dev_keys" / "jwt_public.pem")
os.environ["MOCKMATEAI_REFRESH_TOKEN_SECRET"] = "test-only-refresh-secret"
os.environ["MOCKMATEAI_GOOGLE_CLIENT_ID"] = "test-google-client-id"
os.environ["MOCKMATEAI_GOOGLE_CLIENT_SECRET"] = "test-google-client-secret"
# --- The LLM must never be real in tests -------------------------------
#
# Pinned here for the same reason the Google credentials above are: whatever is
# in .env would otherwise leak in, and the moment a developer configures a
# working API key the suite stops being a test suite. It becomes a live
# integration run against a rate-limited third party -- non-deterministic,
# billable, and slow.
#
# That is not hypothetical. Adding a Groq key took this suite from 60 seconds
# and 545 passes to seven minutes and 16 failures, all of them rate-limit
# cascades, and every one of those tests passed in isolation. Section 15 says
# "don't hit real paid AI APIs in CI"; this is the line that enforces it.
#
# `mock` is a real deterministic adapter, so nothing is stubbed out or lost --
# the full downstream path still runs, it just runs predictably.
os.environ["MOCKMATEAI_LLM_PROVIDER_ORDER"] = "mock"
os.environ["MOCKMATEAI_LLM_API_KEY"] = ""
os.environ["MOCKMATEAI_LLM_FALLBACK_API_KEY_1"] = ""
os.environ["MOCKMATEAI_LLM_FALLBACK_API_KEY_2"] = ""

os.environ["MOCKMATEAI_CORS_ALLOWED_ORIGINS"] = "http://localhost:5173"
os.environ["MOCKMATEAI_FRONTEND_URL"] = "http://localhost:5173"

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401 — populates Base.metadata before create_all
from app.core.rate_limit import limiter  # noqa: E402
from app.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.redis_client import get_redis  # noqa: E402

if not (_BACKEND_DIR / "dev_keys" / "jwt_private.pem").exists():
    raise RuntimeError(
        "Missing dev JWT keys — run `python scripts/generate_dev_keys.py` from backend/ before testing."
    )

Base.metadata.create_all(bind=engine)


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    _TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncates every table after each test so tests stay isolated without paying for a fresh schema each time."""
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """
    Every test hits auth endpoints from the same TestClient "IP", so without
    a reset the in-memory rate-limit storage (Section 12.1A) would carry
    counts across tests and produce spurious 429s unrelated to what any
    individual test is actually checking.
    """
    limiter.reset()
    yield


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def fake_redis():
    server = fakeredis.FakeServer()
    return fakeredis.FakeRedis(server=server, decode_responses=True)


@pytest.fixture()
def client(fake_redis):
    def _get_db_override():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def _get_redis_override():
        yield fake_redis

    fastapi_app.dependency_overrides[get_db] = _get_db_override
    fastapi_app.dependency_overrides[get_redis] = _get_redis_override
    with TestClient(fastapi_app, raise_server_exceptions=True) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
