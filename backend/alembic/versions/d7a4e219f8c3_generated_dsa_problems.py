"""Mark DSA problems that were generated rather than curated.

Revision ID: d7a4e219f8c3
Revises: c3f81a2d4b60
Create Date: 2026-09-28

Same reasoning as the aptitude column, and the stakes are higher here. A
curated problem's test cases are verified by executing a reference solution
(`tests/test_content_banks.py`); a generated one's are verified by independent
recomputation, which catches arithmetic slips but is not proof. Those are
different guarantees, so the rows stay distinguishable -- and a wrong hidden
case fails a CORRECT submission, which is the one failure a candidate cannot
diagnose for themselves.

No column for the entry point: the runner reads it from
`starter_code["functionName"]`, which is how the curated bank already stores it,
so a generated problem stores it there too rather than introducing a second
convention for the same fact.
"""
import sqlalchemy as sa
from alembic import op

revision = "d7a4e219f8c3"
down_revision = "c3f81a2d4b60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dsa_problems",
        sa.Column("is_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("dsa_problems", "is_generated", server_default=None)
    op.create_index("ix_dsa_problems_is_generated", "dsa_problems", ["is_generated"])


def downgrade() -> None:
    op.drop_index("ix_dsa_problems_is_generated", table_name="dsa_problems")
    op.drop_column("dsa_problems", "is_generated")
