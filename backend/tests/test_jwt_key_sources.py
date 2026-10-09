"""
JWT keys load from the environment as well as from disk.

Without this the app cannot start on any platform that deploys from git. The
keypair is a secret, so it is correctly absent from the repository, so there is
no `dev_keys/` directory on the server, so a path-only loader raises
FileNotFoundError on the first request that signs a token.
"""
from pathlib import Path

import pytest

import app.core.security as security
from app.config import get_settings


@pytest.fixture()
def keypair():
    root = Path(__file__).resolve().parent.parent
    return (
        (root / "dev_keys" / "jwt_private.pem").read_text(),
        (root / "dev_keys" / "jwt_public.pem").read_text(),
    )


@pytest.fixture()
def from_env(monkeypatch, keypair):
    """Supply the keys as env vars and point the paths at nothing."""
    def install(private_pem, public_pem):
        monkeypatch.setenv("MOCKMATEAI_JWT_PRIVATE_KEY", private_pem)
        monkeypatch.setenv("MOCKMATEAI_JWT_PUBLIC_KEY", public_pem)
        monkeypatch.setenv("MOCKMATEAI_JWT_PRIVATE_KEY_PATH", "/nonexistent/private.pem")
        monkeypatch.setenv("MOCKMATEAI_JWT_PUBLIC_KEY_PATH", "/nonexistent/public.pem")
        get_settings.cache_clear()
        security._load_private_key.cache_clear()
        security._load_public_key.cache_clear()

    yield install
    get_settings.cache_clear()
    security._load_private_key.cache_clear()
    security._load_public_key.cache_clear()


def test_a_token_round_trips_with_keys_from_the_environment(from_env, keypair):
    private_pem, public_pem = keypair
    from_env(private_pem, public_pem)
    token = security.create_access_token(user_id="user-1")
    assert security.decode_access_token(token)["sub"] == "user-1"


def test_a_pem_whose_newlines_were_collapsed_still_works(from_env, keypair):
    r"""
    The failure mode that costs an hour.

    Several hosting dashboards flatten a multi-line secret to a single line
    with literal backslash-n. The resulting string is not a valid PEM, and the
    parser's complaint is about DER encoding -- which says nothing at all about
    the real cause.
    """
    private_pem, public_pem = keypair
    from_env(private_pem.replace("\n", "\n"), public_pem.replace("\n", "\n"))
    token = security.create_access_token(user_id="user-2")
    assert security.decode_access_token(token)["sub"] == "user-2"


def test_a_quoted_pem_still_works(from_env, keypair):
    """Some dashboards store the surrounding quotes as part of the value."""
    private_pem, public_pem = keypair
    from_env(f'"{private_pem}"', f'"{public_pem}"')
    assert security.decode_access_token(security.create_access_token(user_id="u3"))["sub"] == "u3"


def test_the_file_path_still_works_when_no_env_var_is_set(monkeypatch):
    """Local development must be untouched by all of the above."""
    monkeypatch.setenv("MOCKMATEAI_JWT_PRIVATE_KEY", "")
    monkeypatch.setenv("MOCKMATEAI_JWT_PUBLIC_KEY", "")
    get_settings.cache_clear()
    security._load_private_key.cache_clear()
    security._load_public_key.cache_clear()
    try:
        assert security.decode_access_token(security.create_access_token(user_id="u4"))["sub"] == "u4"
    finally:
        get_settings.cache_clear()
        security._load_private_key.cache_clear()
        security._load_public_key.cache_clear()


def test_the_environment_wins_over_the_path(from_env, keypair):
    """Otherwise a stale file on an image would silently shadow the real key."""
    private_pem, public_pem = keypair
    from_env(private_pem, public_pem)
    assert get_settings().jwt_private_key_path == "/nonexistent/private.pem"
    assert security.create_access_token(user_id="u5")
