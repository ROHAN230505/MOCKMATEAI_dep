import time

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_matches,
    validate_password_policy,
    verify_password,
)


def test_hash_password_roundtrip():
    hashed = hash_password("Sup3r$ecret")
    assert hashed != "Sup3r$ecret"
    assert verify_password("Sup3r$ecret", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("Sup3r$ecret")
    assert verify_password("wrong-password", hashed) is False


def test_verify_password_rejects_garbage_hash():
    assert verify_password("anything", "not-a-real-argon2-hash") is False


@pytest.mark.parametrize(
    "password,expected_violation_count",
    [
        ("short1!", 1),  # too short (7 chars)
        ("nosymbolshere1", 1),  # missing symbol
        ("NoDigits!!", 1),  # missing digit
        ("ab", 3),  # fails all three
        ("Valid1Password!", 0),
    ],
)
def test_password_policy(password, expected_violation_count):
    assert len(validate_password_policy(password)) == expected_violation_count


def test_access_token_roundtrip():
    token = create_access_token(user_id="user-123")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_access_token_rejects_tampered_signature():
    token = create_access_token(user_id="user-123")
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered)


def test_access_token_rejects_expired(monkeypatch):
    import app.core.security as security_module

    # Force a token that expired 1 second ago by monkeypatching the expiry window to a negative value indirectly:
    # simplest reliable approach is to build one with a tiny lib call and sleep past it.
    monkeypatch.setattr(security_module.get_settings(), "jwt_access_token_expire_minutes", 0)
    token = security_module.create_access_token(user_id="user-123")
    time.sleep(1.1)
    with pytest.raises(jwt.InvalidTokenError):
        security_module.decode_access_token(token)


def test_refresh_token_hash_is_deterministic_and_matches():
    raw = generate_refresh_token()
    hashed_once = hash_refresh_token(raw)
    hashed_twice = hash_refresh_token(raw)
    assert hashed_once == hashed_twice
    assert refresh_token_matches(raw, hashed_once) is True


def test_refresh_token_wrong_value_does_not_match():
    raw = generate_refresh_token()
    other = generate_refresh_token()
    assert refresh_token_matches(other, hash_refresh_token(raw)) is False
