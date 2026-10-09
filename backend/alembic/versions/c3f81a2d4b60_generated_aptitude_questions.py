"""Mark aptitude questions that were generated rather than curated.

Revision ID: c3f81a2d4b60
Revises: fcc5cbc4307e
Create Date: 2026-09-28

Generated questions are persisted so an attempt's answers can reference them
like any other row. Without a marker they would be indistinguishable from the
curated bank, which matters for two reasons: the bank's guarantee is that every
answer key has been verified by executing a reference
(`tests/test_content_banks.py`), and a generated question -- however well
verified by re-solve -- has not met that bar. Mixing them silently would dilute
a guarantee the rest of the system relies on, and leave no way to find, audit or
sweep generated rows later.

NOT NULL with a server_default, then the default dropped: existing rows need a
value, and leaving the default in place would let application code omit the
column silently from then on.
"""
import sqlalchemy as sa
from alembic import op

revision = "c3f81a2d4b60"
down_revision = "fcc5cbc4307e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "aptitude_questions",
        sa.Column("is_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("aptitude_questions", "is_generated", server_default=None)
    # Selection filters on this on every practice attempt, and the table grows
    # with every generated test.
    op.create_index(
        "ix_aptitude_questions_is_generated", "aptitude_questions", ["is_generated"]
    )


def downgrade() -> None:
    op.drop_index("ix_aptitude_questions_is_generated", table_name="aptitude_questions")
    op.drop_column("aptitude_questions", "is_generated")
