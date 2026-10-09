import uuid
from datetime import datetime

from pydantic import EmailStr

from app.models.enums import AuthProvider, ExperienceLevel, PreferredMode, UserRole
from app.schemas.common import CamelModel


class UserPublic(CamelModel):
    """
    Public-facing user representation. Explicitly whitelisted — never a raw
    ORM dump — so fields like `password_hash` or `reset_token_hash` can
    never leak through a response model (Section 12.9 mass-assignment note
    applies symmetrically to output).
    """

    id: uuid.UUID
    name: str
    email: EmailStr
    email_verified: bool
    auth_provider: AuthProvider
    role: UserRole
    target_role: str | None = None
    experience_level: ExperienceLevel | None = None
    preferred_mode: PreferredMode | None = None
    created_at: datetime


class UserPreferencesUpdate(CamelModel):
    """
    Body for `PUT /users/preferences`. Every field is optional so the
    onboarding wizard (Section 4.4) can call this once at the end, or a
    later settings screen can patch a single field — but the set of
    updatable fields is a fixed whitelist (Section 12.9: mass-assignment
    prevention), never an arbitrary partial User update.
    """

    target_role: str | None = None
    experience_level: ExperienceLevel | None = None
    preferred_mode: PreferredMode | None = None
