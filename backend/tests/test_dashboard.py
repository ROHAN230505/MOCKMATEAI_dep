def _signup_and_login(client):
    client.post(
        "/api/v1/auth/signup",
        json={"name": "Ada Candidate", "email": "candidate@example.com", "password": "Str0ng!Pass"},
    )
    resp = client.post("/api/v1/auth/login", json={"email": "candidate@example.com", "password": "Str0ng!Pass"})
    return resp.json()["data"]["accessToken"]


def test_dashboard_summary_is_honest_zero_state_for_new_user(client):
    access_token = _signup_and_login(client)
    resp = client.get("/api/v1/dashboard/summary", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["readinessIndex"] == 0.0
    assert data["readinessLabel"] == "Just Getting Started"
    assert data["mockInterviewsCount"] == 0
    assert data["mockInterviewsAvgScore"] is None
    assert data["dsaProblemsSolved"] == 0
    # Not empty, and that is the point: every module *is* empty for a new
    # account, which is a real measurement, not an absence of one. This line
    # asserted [] while `weekly_focus` was hardcoded to [] — the assertion was
    # pinning the bug rather than the behaviour (Section 4.5, feature 38).
    assert len(data["weeklyFocus"]) == 3
    assert data["weeklyFocus"][0]["route"] == "/interview/setup"
    assert all(item["reason"] for item in data["weeklyFocus"])


def test_dashboard_requires_auth(client):
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 401


def test_aggregates_survive_a_decimal_returning_dialect():
    """
    Regression guard for a bug the SQLite suite structurally could not catch.

    `func.avg()` over an Integer column returns `decimal.Decimal` on Postgres and
    `float` on SQLite, and the weighted readiness index multiplies that value by a
    float weight. The mismatch raised TypeError the first time a real aptitude
    attempt was scored against real Postgres - latent since Phase 1, because
    `aptitude_attempts` was empty until Phase 7 and the value was always None.

    Tested by calling the normaliser with a Decimal directly, since this suite's
    database will never produce one.
    """
    from decimal import Decimal

    from app.services.dashboard_service import _as_float

    assert _as_float(Decimal("83.5")) == 83.5
    assert isinstance(_as_float(Decimal("83.5")), float)
    assert _as_float(None) is None
    assert _as_float(42.0) == 42.0
    assert _as_float(7) == 7.0
    # The arithmetic that used to blow up.
    assert 0.25 * _as_float(Decimal("80")) == 20.0
