"""
users + refresh_tokens (Section 8).

Design notes vs. the spec's literal column list:
- `email` is stored **lowercased** by the application layer (see
  schemas/auth.py normalization) instead of relying on Postgres `citext`.
  This keeps the model portable across SQLite (tests) and Postgres
  (production) while achieving the same case-insensitive-uniqueness goal.
- `reset_token_hash` / `reset_token_expires_at` are additions not listed
  verbatim in Section 8 but required to implement the forgot/reset-password
  endpoints from Section 7.1 — kept minimal (two nullable columns) rather
  than a separate table, and never exposed via any API response.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutils import utcnow
from app.database import Base
from app.models.enums import AuthProvider, ExperienceLevel, PreferredMode, UserRole
from app.models.types import GUID, pg_enum, TZDateTime


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Nullable for Google-only accounts; a user must always have at least
    # one of (password_hash, google_sub) — enforced in app/services/auth_service.py
    # and app/services/google_oauth_service.py on every write path, including unlink.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_provider: Mapped[AuthProvider] = mapped_column(
        pg_enum(AuthProvider, "auth_provider"), nullable=False, default=AuthProvider.PASSWORD
    )
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)

    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), nullable=False, default=UserRole.CANDIDATE)
    target_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    experience_level: Mapped[ExperienceLevel | None] = mapped_column(
        pg_enum(ExperienceLevel, "experience_level"), nullable=True
    )
    preferred_mode: Mapped[PreferredMode | None] = mapped_column(
        pg_enum(PreferredMode, "preferred_mode"), nullable=True
    )

    # Progressive lockout (Section 12.1)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    # Reminder preferences (Section 4.19 / feature 43). Stored on `users` rather
    # than a separate table: three scalar flags with no history and no
    # per-channel fan-out do not earn a join, and Section 8 defines no
    # notification table to put them in.
    notify_practice_reminders: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_weekly_summary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Idle days before a practice nudge is shown. Configurable because "consistent
    # practice" means something different to a student and to someone in a job.
    reminder_cadence_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Forgot/reset-password support (see module docstring)
    reset_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(TZDateTime(), server_default=None, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def has_usable_auth_method(self) -> bool:
        return bool(self.password_hash) or bool(self.google_sub)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")
