"""
Single source of truth for "now" across the backend.

Timezone-AWARE UTC — matches what `TZDateTime` (app/models/types.py)
guarantees every timestamp column returns on read, on every dialect. Do
not switch this back to a naive datetime: comparing it against a
`TZDateTime` column would raise `TypeError` on whichever dialect doesn't
match (see TZDateTime's docstring for how this bit us once already).
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
