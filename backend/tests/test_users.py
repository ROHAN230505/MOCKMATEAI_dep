from sqlalchemy import select

from app.models.user import RefreshToken, User


def _signup_and_login(client):
    client.post(
        "/api/v1/auth/signup",
        json={"name": "Ada Candidate", "email": "candidate@example.com", "password": "Str0ng!Pass"},
    )
    resp = client.post("/api/v1/auth/login", json={"email": "candidate@example.com", "password": "Str0ng!Pass"})
    return resp.json()["data"]["accessToken"]


def test_update_preferences_whitelisted_fields_only(client):
    access_token = _signup_and_login(client)
    resp = client.put(
        "/api/v1/users/preferences",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"targetRole": "SDE", "experienceLevel": "student_fresher", "preferredMode": "voice"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["targetRole"] == "SDE"
    assert data["experienceLevel"] == "student_fresher"
    assert data["preferredMode"] == "voice"


def test_update_preferences_rejects_unknown_fields_silently_ignored(client):
    access_token = _signup_and_login(client)
    # `role` is not in the whitelist (Section 12.9 mass-assignment prevention)
    # — Pydantic's extra="ignore"-free CamelModel simply won't map it to any
    # field, so it can never reach the ORM update.
    resp = client.put(
        "/api/v1/users/preferences",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"targetRole": "SDE", "role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["role"] == "candidate"


def test_delete_account_cascades_refresh_tokens(client, db_session):
    access_token = _signup_and_login(client)

    user = db_session.execute(select(User).where(User.email == "candidate@example.com")).scalar_one()
    user_id = user.id
    tokens_before = db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id)).scalars().all()
    assert len(tokens_before) >= 1

    resp = client.delete("/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200

    db_session.expire_all()
    assert db_session.get(User, user_id) is None
    tokens_after = db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id)).scalars().all()
    assert tokens_after == []


def test_deleted_account_token_no_longer_authenticates(client):
    access_token = _signup_and_login(client)
    client.delete("/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"})
    resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 401
