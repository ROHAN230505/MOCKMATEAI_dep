"""
Settings schemas (Sections 4.17-4.19, features 42-43).

`PrivacyInventory` is the one worth explaining. Section 4.17 requires the privacy
screen to list "all stored recordings/data with per-item Delete buttons". This
build stores no recordings, so a literal implementation would be an empty list
under a heading promising something that does not exist.

Instead the screen shows what the account *actually* holds, counted per category,
alongside a plain statement of what is never stored at all. That is more useful
than an empty list and more honest than a heading with nothing under it — a
candidate asking "what do you have on me?" gets a real answer either way.
"""
from datetime import datetime

from pydantic import Field

from app.models.enums import ExperienceLevel, PreferredMode
from app.schemas.common import CamelModel


class ProfileOut(CamelModel):
    id: str
    name: str
    email: str
    email_verified: bool
    auth_provider: str
    has_password: bool
    has_google: bool
    role: str
    target_role: str | None
    experience_level: ExperienceLevel | None
    preferred_mode: PreferredMode | None
    created_at: datetime


class UpdateProfileRequest(CamelModel):
    """
    Name only.

    Email is deliberately not editable here: changing it would need re-verification
    and would break the Google account-matching in Section 6.5 step 7. Role is
    absent for the reason Section 12.9 gives — a profile update must never be a
    path to `role: admin`.
    """

    name: str = Field(min_length=1, max_length=255)


class NotificationPreferences(CamelModel):
    practice_reminders: bool = True
    weekly_summary: bool = True
    # Idle days before a nudge appears. Bounded so it stays a reminder rather
    # than either nagging daily or never firing.
    reminder_cadence_days: int = Field(default=3, ge=1, le=30)


class DataCategory(CamelModel):
    key: str
    label: str
    count: int
    #: What deleting the account does to this category.
    detail: str


class PrivacyInventory(CamelModel):
    categories: list[DataCategory]
    #: Categories the product never stores at all, each with the reason.
    never_stored: list[DataCategory]
