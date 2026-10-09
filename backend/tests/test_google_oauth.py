"""
Google OAuth tests (Section 6.5, 12.10). Network calls to Google itself
(_exchange_code, _verify_id_token) are monkeypatched — this is exactly the
"don't hit real paid/external APIs in CI" guidance from Section 15,
applied to a free-but-still-external dependency.
"""
import pytest

from app.core.responses import ApiError
from app.core.security import hash_password
from app.models.enums import AuthProvider
from app.models.user import User
from app.services import google_oauth_service


def _fake_claims(*, sub="google-sub-123", email="candidate@example.com", email_verified=True, name="Ada Candidate"):
    return {"sub": sub, "email": email, "email_verified": email_verified, "name": name, "iss": "accounts.google.com"}


def _patch_google_network(monkeypatch, claims):
    async def _fake_exchange(*, code, code_verifier):
        assert code == "auth-code"
        return {"id_token": "fake-id-token"}

    async def _fake_verify(id_token_str):
        assert id_token_str == "fake-id-token"
        return claims

    monkeypatch.setattr(google_oauth_service, "_exchange_code", _fake_exchange)
    monkeypatch.setattr(google_oauth_service, "_verify_id_token", _fake_verify)


def test_authorization_url_contains_pkce_and_state(fake_redis):
    url = google_oauth_service.build_authorization_url(fake_redis, intent="login")
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert "state=" in url
    assert "scope=openid+email+profile" in url or "scope=openid%20email%20profile" in url


def test_consume_pending_auth_is_single_use(fake_redis):
    url = google_oauth_service.build_authorization_url(fake_redis, intent="login")
    state = url.split("state=")[1].split("&")[0]

    pending = google_oauth_service._consume_pending_auth(fake_redis, state)
    assert pending.intent == "login"

    with pytest.raises(ApiError) as exc_info:
        google_oauth_service._consume_pending_auth(fake_redis, state)
    assert exc_info.value.code == "invalid_oauth_state"


def test_consume_pending_auth_rejects_unknown_state(fake_redis):
    with pytest.raises(ApiError) as exc_info:
        google_oauth_service._consume_pending_auth(fake_redis, "not-a-real-state")
    assert exc_info.value.code == "invalid_oauth_state"


@pytest.mark.anyio
async def test_handle_callback_creates_new_user(db_session, fake_redis, monkeypatch):
    _patch_google_network(monkeypatch, _fake_claims())
    url = google_oauth_service.build_authorization_url(fake_redis, intent="login")
    state = url.split("state=")[1].split("&")[0]

    result = await google_oauth_service.handle_callback(db_session, fake_redis, code="auth-code", state=state)

    assert result["kind"] == "login"
    assert result["is_new_user"] is True
    assert result["user"].email == "candidate@example.com"
    assert result["user"].auth_provider == AuthProvider.GOOGLE
    assert result["user"].email_verified is True
    assert result["user"].password_hash is None


@pytest.mark.anyio
async def test_handle_callback_matches_existing_google_user(db_session, fake_redis, monkeypatch):
    claims = _fake_claims()
    _patch_google_network(monkeypatch, claims)
    existing = User(
        name="Ada Candidate",
        email="candidate@example.com",
        auth_provider=AuthProvider.GOOGLE,
        google_sub=claims["sub"],
        email_verified=True,
    )
    db_session.add(existing)
    db_session.commit()

    url = google_oauth_service.build_authorization_url(fake_redis, intent="login")
    state = url.split("state=")[1].split("&")[0]
    result = await google_oauth_service.handle_callback(db_session, fake_redis, code="auth-code", state=state)

    assert result["is_new_user"] is False
    assert result["user"].id == existing.id


@pytest.mark.anyio
async def test_handle_callback_refuses_to_automerge_password_account(db_session, fake_redis, monkeypatch):
    claims = _fake_claims(email="candidate@example.com")
    _patch_google_network(monkeypatch, claims)
    password_user = User(
        name="Ada Candidate",
        email="candidate@example.com",
        auth_provider=AuthProvider.PASSWORD,
        password_hash=hash_password("Str0ng!Pass"),
        email_verified=False,
    )
    db_session.add(password_user)
    db_session.commit()

    url = google_oauth_service.build_authorization_url(fake_redis, intent="login")
    state = url.split("state=")[1].split("&")[0]

    with pytest.raises(ApiError) as exc_info:
        await google_oauth_service.handle_callback(db_session, fake_redis, code="auth-code", state=state)
    assert exc_info.value.code == "email_exists_as_password_account"

    db_session.refresh(password_user)
    assert password_user.google_sub is None


@pytest.mark.anyio
async def test_handle_callback_rejects_unverified_email(db_session, fake_redis, monkeypatch):
    _patch_google_network(monkeypatch, _fake_claims(email_verified=False))
    url = google_oauth_service.build_authorization_url(fake_redis, intent="login")
    state = url.split("state=")[1].split("&")[0]

    with pytest.raises(ApiError) as exc_info:
        await google_oauth_service.handle_callback(db_session, fake_redis, code="auth-code", state=state)
    assert exc_info.value.code == "google_email_unverified"


def test_unlink_blocked_without_password_set(db_session):
    user = User(
        name="Ada Candidate",
        email="candidate@example.com",
        auth_provider=AuthProvider.GOOGLE,
        google_sub="google-sub-123",
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        google_oauth_service.unlink_google_account(db_session, user)
    assert exc_info.value.code == "password_required_before_unlink"


def test_unlink_succeeds_when_password_is_set(db_session):
    user = User(
        name="Ada Candidate",
        email="candidate@example.com",
        auth_provider=AuthProvider.BOTH,
        google_sub="google-sub-123",
        password_hash=hash_password("Str0ng!Pass"),
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()

    updated = google_oauth_service.unlink_google_account(db_session, user)
    assert updated.google_sub is None
    assert updated.auth_provider == AuthProvider.PASSWORD


@pytest.fixture
def anyio_backend():
    return "asyncio"
