"""phase4 feedback report generation bookkeeping

Adds the Phase 4 lifecycle columns to `feedback_reports`:
`generation_status`, `generated_by`, `generation_error`, `created_at`.

The two NOT NULL columns are added WITH a server_default and then have it
dropped. `feedback_reports` is empty today (Phase 4 is its first writer), but a
migration that only works on an empty table is a trap for anyone who runs it
after a real deployment — and dropping the default afterwards keeps the model's
Python-side default as the single source of truth for new rows.

Revision ID: 39078676c470
Revises: 36470d2702d6
Create Date: 2026-08-13 19:04:52.481371

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.models.types


# revision identifiers, used by Alembic.
revision: str = '39078676c470'
down_revision: Union[str, None] = '36470d2702d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Values are spelled out literally rather than derived from the Python enum:
# a migration must keep describing the schema it created even if the enum class
# later gains members (and see the house rule behind app.models.types.pg_enum —
# `values_callable` exists so Postgres stores these lowercase values, not the
# Python member names).
generation_status = sa.Enum(
    'pending', 'processing', 'ready', 'failed', name='feedback_generation_status'
)


def upgrade() -> None:
    generation_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'feedback_reports',
        sa.Column('generation_status', generation_status, nullable=False, server_default='pending'),
    )
    op.add_column('feedback_reports', sa.Column('generated_by', sa.String(length=50), nullable=True))
    op.add_column('feedback_reports', sa.Column('generation_error', sa.Text(), nullable=True))
    op.add_column(
        'feedback_reports',
        sa.Column(
            'created_at',
            app.models.types.TZDateTime(timezone=True),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
    )
    op.create_index(
        op.f('ix_feedback_reports_generation_status'), 'feedback_reports', ['generation_status'], unique=False
    )

    op.alter_column('feedback_reports', 'generation_status', server_default=None)
    op.alter_column('feedback_reports', 'created_at', server_default=None)


def downgrade() -> None:
    op.drop_index(op.f('ix_feedback_reports_generation_status'), table_name='feedback_reports')
    op.drop_column('feedback_reports', 'created_at')
    op.drop_column('feedback_reports', 'generation_error')
    op.drop_column('feedback_reports', 'generated_by')
    op.drop_column('feedback_reports', 'generation_status')
    generation_status.drop(op.get_bind(), checkfirst=True)
