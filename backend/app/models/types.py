"""
Portable column types shared by every model.

`GUID` renders as a native `UUID` on PostgreSQL (the production target per
Section 8) and as `CHAR(36)` on any other dialect — this lets the exact same
model definitions back both the real Postgres deployment and fast in-memory
SQLite used by the test suite (see backend/tests/conftest.py), without a
second "test schema" to keep in sync.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, DateTime, TypeDecorator


def pg_enum(enum_cls, name: str) -> SAEnum:
    """
    Every enum column in this schema must go through this helper, not a
    bare `sa.Enum(...)` call. Without `values_callable`, SQLAlchemy stores
    a native Postgres enum's labels as the Python member *names*
    (`AuthProvider.PASSWORD` -> `'PASSWORD'`) rather than their `.value`
    (`'password'`) — silently inconsistent with the lowercase values
    Section 8's schema, every Pydantic schema, and the SQLite test suite
    all use. `values_callable` forces `.value` to be the actual stored/DDL
    string on every dialect.
    """
    return SAEnum(enum_cls, name=name, values_callable=lambda cls: [member.value for member in cls])


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        return value


class TZDateTime(TypeDecorator):
    """
    Guarantees a timezone-AWARE UTC `datetime` on every read, and normalizes
    to UTC on every write, regardless of dialect.

    Found the hard way (live-tested against real Postgres in Phase 2, not
    just the SQLite-backed test suite): Postgres's `TIMESTAMP WITH TIME
    ZONE` always round-trips a timezone-aware datetime, but SQLite always
    round-trips naive, even on a column declared `DateTime(timezone=True)`.
    A bare `DateTime(timezone=True)` column is therefore silently
    inconsistent across dialects — `utcnow() - session.started_at` raises
    `TypeError: can't subtract offset-naive and offset-aware datetimes` on
    Postgres while working fine against SQLite (or vice versa, depending on
    which helper produced which side). Every timestamp column in this
    schema must use `TZDateTime()`, never a bare `DateTime(timezone=True)`
    — same rule as `pg_enum` above for enum columns.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
