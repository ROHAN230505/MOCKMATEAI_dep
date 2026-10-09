"""
SQLAlchemy engine/session wiring.

The engine URL is read lazily (via get_settings()) rather than at import
time so tests can point MOCKMATEAI_DB_URL at a throwaway SQLite file before
the engine is ever created.
"""
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in app/models/."""


def _make_engine():
    settings = get_settings()
    connect_args = {}
    if settings.db_url.startswith("sqlite"):
        # Needed for SQLite when the same connection is shared across
        # FastAPI's request threads in tests.
        connect_args["check_same_thread"] = False
    engine = create_engine(settings.db_url, pool_pre_ping=True, connect_args=connect_args)
    if settings.db_url.startswith("sqlite"):
        # SQLite ignores FK constraints unless explicitly told otherwise per
        # connection — required for the Section 12.4 cascade-delete
        # behavior (e.g. deleting a user cascades to refresh_tokens,
        # interview_sessions, etc.) to actually work under the SQLite
        # backend used by the test suite.
        @event.listens_for(engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
