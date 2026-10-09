"""Integration tests for the email/password auth endpoints (Section 7.1)."""


def _signup(client, email="candidate@example.com", password="Str0ng!Pass", name="Ada Candidate"):
    return client.post("/api/v1/auth/signup", json={"name": name, "email": email, "password": password})


def test_signup_success_returns_tokens_and_user(client):
    resp = _signup(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == "candidate@example.com"
    assert "passwordHash" not in body["data"]["user"]
    assert body["data"]["accessToken"]
    assert body["data"]["refreshToken"]


def test_signup_rejects_weak_password(client):
    resp = _signup(client, password="weak")
    # min_length=8 is enforced by the Pydantic schema itself -> 422
    assert resp.status_code in (400, 422)
    assert resp.json()["success"] is False


def test_signup_rejects_password_missing_symbol(client):
    resp = _signup(client, password="password1")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "weak_password"


def test_signup_duplicate_email_rejected(client):
    _signup(client)
    resp = _signup(client)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "email_already_registered"


def test_signup_email_is_case_and_whitespace_normalized(client):
    _signup(client, email="  Candidate@Example.com  ")
    resp = client.post(
        "/api/v1/auth/login", json={"email": "candidate@example.com", "password": "Str0ng!Pass"}
    )
    assert resp.status_code == 200


def test_login_success(client):
    _signup(client)
    resp = client.post("/api/v1/auth/login", json={"email": "candidate@example.com", "password": "Str0ng!Pass"})
    assert resp.status_code == 200
    assert resp.json()["data"]["accessToken"]


def test_login_wrong_password_generic_error(client):
    _signup(client)
    resp = client.post("/api/v1/auth/login", json={"email": "candidate@example.com", "password": "wrong-pass1!"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"
    # Section 4.3/12.1: the exact same generic message regardless of
    # whether the email or the password was the wrong part.
    assert resp.json()["error"]["message"] == "Incorrect email or password."


def test_login_unknown_email_same_error_as_wrong_password(client):
    resp = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-pass1!"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def test_progressive_lockout_after_five_failed_attempts(db_session):
    """
    Exercised at the service layer, not over HTTP: Section 12.1A's per-IP
    login rate limit (5 / 15 min) and Section 12.1's per-account lockout
    threshold are both set to 5, so a same-IP HTTP client hits its own rate
    limit at the same point and never observes the 423 — that overlap is
    two independent guardrails both correctly firing, not a bug, but it
    means account lockout itself is best verified directly against
    auth_service, bypassing the IP-layer entirely.
    """
    import pytest

    from app.core.responses import ApiError
    from app.services import auth_service

    auth_service.create_user(db_session, name="Ada Candidate", email="candidate@example.com", password="Str0ng!Pass")

    for _ in range(5):
        with pytest.raises(ApiError) as exc_info:
            auth_service.authenticate_user(db_session, email="candidate@example.com", password="wrong-pass1!")
        assert exc_info.value.code == "invalid_credentials"

    with pytest.raises(ApiError) as exc_info:
        auth_service.authenticate_user(db_session, email="candidate@example.com", password="Str0ng!Pass")
    assert exc_info.value.code == "account_locked"


def test_login_rate_limit_returns_429_after_threshold(client):
    _signup(client)
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "candidate@example.com", "password": "wrong-pass1!"})

    resp = client.post("/api/v1/auth/login", json={"email": "candidate@example.com", "password": "Str0ng!Pass"})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in resp.headers


def test_check_account_type_password_account(client):
    _signup(client)
    resp = client.post("/api/v1/auth/check-account-type", json={"email": "candidate@example.com"})
    assert resp.json()["data"]["authMethod"] == "password"


def test_check_account_type_unknown_email(client):
    resp = client.post("/api/v1/auth/check-account-type", json={"email": "nobody@example.com"})
    assert resp.json()["data"]["authMethod"] == "unknown"


def test_refresh_rotates_token_and_invalidates_old_one(client):
    signup_resp = _signup(client)
    old_refresh = signup_resp.json()["data"]["refreshToken"]

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refreshToken": old_refresh})
    assert refresh_resp.status_code == 200
    new_refresh = refresh_resp.json()["data"]["refreshToken"]
    assert new_refresh != old_refresh

    replay_resp = client.post("/api/v1/auth/refresh", json={"refreshToken": old_refresh})
    assert replay_resp.status_code == 401

    # Replay detection revokes every token for the user — the freshly
    # rotated one must now be dead too (Section 12.1 stolen-token defense).
    reuse_new_resp = client.post("/api/v1/auth/refresh", json={"refreshToken": new_refresh})
    assert reuse_new_resp.status_code == 401


def test_logout_revokes_refresh_token(client):
    signup_resp = _signup(client)
    refresh_token = signup_resp.json()["data"]["refreshToken"]

    logout_resp = client.post("/api/v1/auth/logout", json={"refreshToken": refresh_token})
    assert logout_resp.status_code == 200

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refreshToken": refresh_token})
    assert refresh_resp.status_code == 401


def test_logout_all_devices_revokes_every_token(client):
    signup_resp = _signup(client)
    access_token = signup_resp.json()["data"]["accessToken"]
    refresh_token_1 = signup_resp.json()["data"]["refreshToken"]

    login_resp = client.post("/api/v1/auth/login", json={"email": "candidate@example.com", "password": "Str0ng!Pass"})
    refresh_token_2 = login_resp.json()["data"]["refreshToken"]

    logout_all_resp = client.post(
        "/api/v1/auth/logout-all-devices", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert logout_all_resp.status_code == 200

    assert client.post("/api/v1/auth/refresh", json={"refreshToken": refresh_token_1}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refreshToken": refresh_token_2}).status_code == 401


def test_forgot_password_returns_200_regardless_of_email_existing(client):
    _signup(client)
    known = client.post("/api/v1/auth/forgot-password", json={"email": "candidate@example.com"})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.status_code == 200
    assert unknown.status_code == 200


def test_reset_password_with_dev_token_then_login(client):
    _signup(client)
    forgot_resp = client.post("/api/v1/auth/forgot-password", json={"email": "candidate@example.com"})
    dev_token = forgot_resp.json()["data"]["devResetToken"]

    reset_resp = client.post(
        "/api/v1/auth/reset-password", json={"token": dev_token, "newPassword": "N3wPassword!"}
    )
    assert reset_resp.status_code == 200

    old_login = client.post("/api/v1/auth/login", json={"email": "candidate@example.com", "password": "Str0ng!Pass"})
    assert old_login.status_code == 401

    new_login = client.post("/api/v1/auth/login", json={"email": "candidate@example.com", "password": "N3wPassword!"})
    assert new_login.status_code == 200


def test_reset_password_rejects_invalid_token(client):
    resp = client.post("/api/v1/auth/reset-password", json={"token": "not-a-real-token", "newPassword": "N3wPassword!"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_reset_token"


def test_unauthenticated_me_requires_token(client):
    resp = client.get("/api/v1/users/me")
    assert resp.status_code == 401


def test_me_returns_current_user(client):
    signup_resp = _signup(client)
    access_token = signup_resp.json()["data"]["accessToken"]
    resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "candidate@example.com"
