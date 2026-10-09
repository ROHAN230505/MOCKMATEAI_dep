"""User profile/preferences business logic (Section 7.2, 4.4 onboarding wizard)."""
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserPreferencesUpdate


def update_preferences(db: Session, user: User, data: UserPreferencesUpdate) -> User:
    """
    Only ever touches the fixed whitelist below (Section 12.9 mass-assignment
    prevention) — `data` is already a validated Pydantic model with no other
    fields possible, but `exclude_unset` additionally means an omitted field
    leaves the existing value untouched rather than being reset to null.
    """
    updates = data.model_dump(exclude_unset=True)
    for field in ("target_role", "experience_level", "preferred_mode"):
        if field in updates:
            setattr(user, field, updates[field])
    db.commit()
    db.refresh(user)
    return user


def delete_account(db: Session, user: User) -> None:
    """
    Section 12.4: full deletion must cascade across every table, regardless
    of auth method (a Google-linked account is not special-cased). All
    Section 8 tables that reference `users.id` declare `ondelete="CASCADE"`
    (see app/models/), so a single delete here is sufficient for every
    table currently in the schema.

    NOTE for Phase 2+: `recordings` intentionally has no DB-level FK back to
    interview_sessions (see models/recording.py) to avoid a circular FK at
    the schema level — once the Recording/Storage Service (Section 6.1)
    exists, this function must also explicitly purge the candidate's
    recordings from object storage before/after this commit.
    """
    db.delete(user)
    db.commit()
