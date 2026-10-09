"""
Shared Pydantic base: internal fields stay snake_case in Python, but every
request/response body speaks camelCase on the wire (matching Section 7's
API examples — `accessToken`, `targetRole`, `authMethod`, etc.) without
hand-writing an alias per field.

It also strips characters Postgres refuses to store from every incoming string.
See `_strip_unstorable` for why that belongs here rather than on individual
fields.
"""
from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel

# Postgres `text`/`varchar` cannot hold a NUL byte at all — psycopg raises
# `DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes`. The other
# C0 control characters below are storable but carry no meaning in any field this
# API accepts, and they corrupt transcripts, PDF exports and CSV-ish output.
# Tab, newline and carriage return are kept: job descriptions and resumes are
# multi-line by nature.
_UNSTORABLE = {code: None for code in range(0x20) if code not in (0x09, 0x0A, 0x0D)}
_UNSTORABLE[0x7F] = None


def strip_unstorable(value: str) -> str:
    """Exported so the raw WebSocket path can apply the same rule."""
    return value.translate(_UNSTORABLE)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _strip_unstorable(cls, data):
        """
        Remove NUL and other C0 control characters from every incoming string.

        Applied on the base model rather than per field, because the failure this
        prevents is not field-specific and was found the hard way: a NUL byte in
        `jobDescriptionText` reached Postgres unvalidated and raised an unhandled
        `psycopg.DataError`, which is a 500 with a SQL statement in the
        traceback — a Section 12.5 validation gap producing a Section 12.9
        information-disclosure risk from one pasted byte.

        Doing it here means every current *and future* request schema inherits
        the protection, rather than someone having to remember a validator on the
        next free-text field they add. That is the same argument Section 12.2
        makes for a shared authorization decorator over per-controller checks.

        Stripped rather than rejected: a NUL in a pasted job description is
        almost always an artefact of the copy, not an attack, and failing a
        candidate's interview setup over an invisible character would be a worse
        outcome than silently dropping it. Length limits still apply afterwards.
        """
        if isinstance(data, dict):
            return {
                key: strip_unstorable(value) if isinstance(value, str) else value
                for key, value in data.items()
            }
        return data
