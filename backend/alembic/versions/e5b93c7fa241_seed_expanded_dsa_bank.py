"""Seed the 42 DSA problems added to the curated bank.

Revision ID: e5b93c7fa241
Revises: d7a4e219f8c3
Create Date: 2026-10-05

No schema change. The bank grew from 8 problems to 50, and three topics that
had nothing at all -- linked lists, trees, recursion/backtracking -- now have
coverage. A practice module that offers eight problems is a demo; fifty is
something a candidate can actually work through.

Seeded from `app.content.dsa_bank.build_rows()`, the same module the
application reads, so the rows inserted here are the ones
`tests/test_content_banks.py` verifies by executing each reference solution
against its 355 stored test cases. Nothing in this file restates a problem,
because a copy would be a second source of truth that no test checks.

Idempotent by title, matching the Phase 7 seed it follows: a problem already
present is skipped, so this adds only what is new whether it runs against a
fresh database or one seeded before the bank grew.
"""
import uuid

import sqlalchemy as sa
from alembic import op

import app.models.types

revision = "e5b93c7fa241"
down_revision = "d7a4e219f8c3"
branch_labels = None
depends_on = None


def _dsa_table():
    return sa.table(
        "dsa_problems",
        sa.column("id", app.models.types.GUID()),
        sa.column("title", sa.String()),
        sa.column("topic", sa.Enum(name="dsa_topic", native_enum=True, create_type=False)),
        sa.column("difficulty", sa.Enum(name="dsa_difficulty", native_enum=True, create_type=False)),
        sa.column("statement_text", sa.Text()),
        sa.column("constraints_text", sa.Text()),
        sa.column("starter_code", sa.JSON()),
        sa.column("test_cases", sa.JSON()),
        sa.column("is_generated", sa.Boolean()),
        sa.column("created_at", app.models.types.TZDateTime(timezone=True)),
    )


def upgrade() -> None:
    from app.content.dsa_bank import build_rows
    from app.core.timeutils import utcnow

    connection = op.get_bind()
    now = utcnow()

    existing = {row[0] for row in connection.execute(sa.text("SELECT title FROM dsa_problems"))}
    new_problems = [
        {
            "id": uuid.uuid4(),
            "title": row["title"],
            # Bound as the enum's *value*, matching how pg_enum's
            # values_callable writes it everywhere else in the schema.
            "topic": row["topic"].value,
            "difficulty": row["difficulty"].value,
            "statement_text": row["statement_text"],
            "constraints_text": row["constraints_text"],
            "starter_code": row["starter_code"],
            "test_cases": row["test_cases"],
            # Curated, not written by a model: these have execution-verified
            # test cases, which is a stronger guarantee than the generated path
            # can offer and the reason the two stay distinguishable.
            "is_generated": False,
            "created_at": now,
        }
        for row in build_rows()
        if row["title"] not in existing
    ]
    if new_problems:
        op.bulk_insert(_dsa_table(), new_problems)


def downgrade() -> None:
    """
    Deliberately not implemented.

    Removing seeded content would orphan any `dsa_submissions` that reference
    it, and the rows are harmless to leave in place -- a downgrade is about
    schema, and this migration changes none.
    """
