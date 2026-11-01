"""
Settings parsing that a deploy depends on.

Hosted Postgres hands out a bare `postgresql://` URL; pasted as given it would
make SQLAlchemy reach for psycopg2, which is not installed, and the service
would fail on its first query rather than at configuration time.
"""
import pytest

from app.config import Settings


@pytest.mark.parametrize(
    "given",
    [
        "postgresql://u:p@host:5432/db?sslmode=require",
        "postgres://u:p@host:5432/db?sslmode=require",
        "postgresql+psycopg://u:p@host:5432/db?sslmode=require",
    ],
)
def test_hosted_postgres_urls_are_given_the_psycopg_driver(given):
    settings = Settings(db_url=given)
    assert settings.db_url == "postgresql+psycopg://u:p@host:5432/db?sslmode=require"


def test_sqlite_urls_are_left_alone():
    assert Settings(db_url="sqlite:///./x.db").db_url == "sqlite:///./x.db"
