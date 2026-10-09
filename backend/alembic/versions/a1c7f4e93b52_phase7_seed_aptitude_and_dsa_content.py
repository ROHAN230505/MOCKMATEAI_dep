"""phase7 seed aptitude and dsa content

No schema change: `aptitude_questions` and `dsa_problems` were created by the
initial migration and have sat empty since. This seeds them from the curated
banks in `app/content/`, so a fresh database has a practisable module the moment
it has migrated rather than an empty list and a dead screen.

Seeded from the same modules the application reads, not a copy pasted in here.
That means the option shuffle is the identical deterministic one
(`aptitude_bank.build_rows`), and the DSA test cases are the ones
`tests/test_content_banks.py` verifies by executing each reference solution
against them.

Idempotent by content rather than by id: a question already present by its text
is skipped, so re-running against a database that was seeded by an earlier
version of the bank adds only what is new instead of duplicating everything.

Revision ID: a1c7f4e93b52
Revises: 39078676c470
Create Date: 2026-08-31 21:10:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.models.types

# revision identifiers, used by Alembic.
revision: str = "a1c7f4e93b52"
down_revision: Union[str, None] = "39078676c470"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Declared with the project's own TypeDecorators so the GUID, TZDateTime and JSON
# columns bind exactly as the models bind them. A raw textual INSERT hands
# Postgres a varchar for a uuid column and fails (see the Phase 4 seed migration).
def _aptitude_table():
    return sa.table(
        "aptitude_questions",
        sa.column("id", app.models.types.GUID()),
        sa.column("topic", sa.Enum(name="aptitude_topic", native_enum=True, create_type=False)),
        sa.column("difficulty", sa.Enum(name="difficulty", native_enum=True, create_type=False)),
        sa.column("question_text", sa.Text()),
        sa.column("options", sa.JSON()),
        sa.column("correct_option_index", sa.Integer()),
        sa.column("company_pattern_tag", sa.String()),
        sa.column("created_at", app.models.types.TZDateTime(timezone=True)),
    )


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
        sa.column("created_at", app.models.types.TZDateTime(timezone=True)),
    )


def upgrade() -> None:
    from app.content.aptitude_bank import build_rows as aptitude_rows
    from app.content.dsa_bank import build_rows as dsa_rows
    from app.core.timeutils import utcnow

    connection = op.get_bind()
    now = utcnow()

    existing_questions = {
        row[0]
        for row in connection.execute(sa.text("SELECT question_text FROM aptitude_questions"))
    }
    new_questions = [
        {
            "id": uuid.uuid4(),
            # Bound as the enum's *value*, matching how `pg_enum`'s
            # values_callable writes it everywhere else in the schema.
            "topic": row["topic"].value,
            "difficulty": row["difficulty"].value,
            "question_text": row["question_text"],
            "options": row["options"],
            "correct_option_index": row["correct_option_index"],
            "company_pattern_tag": row["company_pattern_tag"],
            "created_at": now,
        }
        for row in aptitude_rows()
        if row["question_text"] not in existing_questions
    ]
    if new_questions:
        op.bulk_insert(_aptitude_table(), new_questions)

    existing_titles = {
        row[0] for row in connection.execute(sa.text("SELECT title FROM dsa_problems"))
    }
    new_problems = [
        {
            "id": uuid.uuid4(),
            "title": row["title"],
            "topic": row["topic"].value,
            "difficulty": row["difficulty"].value,
            "statement_text": row["statement_text"],
            "constraints_text": row["constraints_text"],
            "starter_code": row["starter_code"],
            "test_cases": row["test_cases"],
            "created_at": now,
        }
        for row in dsa_rows()
        if row["title"] not in existing_titles
    ]
    if new_problems:
        op.bulk_insert(_dsa_table(), new_problems)


def downgrade() -> None:
    """
    Removes only the seeded rows, matched by the content that was inserted.

    A blanket DELETE would also discard anything added since, and an attempt
    answer referencing a deleted question would violate its foreign key. Rows
    still referenced by an attempt are therefore left in place.
    """
    from app.content.aptitude_bank import build_rows as aptitude_rows
    from app.content.dsa_bank import build_rows as dsa_rows

    connection = op.get_bind()

    questions = [row["question_text"] for row in aptitude_rows()]
    if questions:
        connection.execute(
            sa.text(
                "DELETE FROM aptitude_questions WHERE question_text = ANY(:texts) "
                "AND id NOT IN (SELECT question_id FROM aptitude_attempt_answers)"
            ).bindparams(sa.bindparam("texts", value=questions, expanding=False)),
        )

    titles = [row["title"] for row in dsa_rows()]
    if titles:
        connection.execute(
            sa.text(
                "DELETE FROM dsa_problems WHERE title = ANY(:titles) "
                "AND id NOT IN (SELECT problem_id FROM dsa_submissions)"
            ).bindparams(sa.bindparam("titles", value=titles, expanding=False)),
        )
