"""
Settings, privacy inventory, admin analytics and `compareRole` (Sections 4.17-4.19, 16, 7.3).
"""
import uuid

import pytest

from app.models.enums import UserRole
from app.models.user import User
from app.services import admin_analytics

PASSWORD = "Str0ng!Pass"


def _login(client, email=None):
    email = email or f"s-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/v1/auth/signup", json={"name": "Ada", "email": email, "password": PASSWORD})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["data"]["accessToken"]
    return {"Authorization": "Bearer " + token}, email


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
def test_profile_reports_which_auth_methods_are_attached(client, db_session):
    headers, email = _login(client)
    data = client.get("/api/v1/users/profile", headers=headers).json()["data"]
    assert data["email"] == email
    assert data["hasPassword"] is True
    assert data["hasGoogle"] is False
    # Derived booleans, never the credentials themselves.
    assert "passwordHash" not in data
    assert "googleSub" not in data


def test_profile_name_can_be_changed(client, db_session):
    headers, _ = _login(client)
    client.put("/api/v1/users/profile", json={"name": "Ada Lovelace"}, headers=headers)
    assert client.get("/api/v1/users/profile", headers=headers).json()["data"]["name"] == "Ada Lovelace"


def test_profile_update_cannot_change_email_or_role(client, db_session):
    """
    Section 12.9's mass-assignment rule. Email is excluded because changing it
    would need re-verification and would break Google account matching.
    """
    headers, email = _login(client)
    client.put(
        "/api/v1/users/profile",
        json={"name": "Ada", "email": "attacker@example.com", "role": "admin"},
        headers=headers,
    )
    data = client.get("/api/v1/users/profile", headers=headers).json()["data"]
    assert data["email"] == email
    assert data["role"] != "admin"


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
def test_notification_preferences_round_trip(client, db_session):
    headers, _ = _login(client)
    defaults = client.get("/api/v1/users/notifications", headers=headers).json()["data"]
    assert defaults == {"practiceReminders": True, "weeklySummary": True, "reminderCadenceDays": 3}

    client.put(
        "/api/v1/users/notifications",
        json={"practiceReminders": False, "weeklySummary": True, "reminderCadenceDays": 7},
        headers=headers,
    )
    saved = client.get("/api/v1/users/notifications", headers=headers).json()["data"]
    assert saved["practiceReminders"] is False
    assert saved["reminderCadenceDays"] == 7


@pytest.mark.parametrize("days", [0, 31, -1])
def test_reminder_cadence_is_bounded(client, db_session, days):
    """Bounded so it stays a reminder rather than nagging daily or never firing."""
    headers, _ = _login(client)
    resp = client.put(
        "/api/v1/users/notifications",
        json={"practiceReminders": True, "weeklySummary": True, "reminderCadenceDays": days},
        headers=headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Privacy inventory
# ---------------------------------------------------------------------------
def test_privacy_inventory_counts_real_rows(client, db_session):
    headers, _ = _login(client)
    before = client.get("/api/v1/users/privacy", headers=headers).json()["data"]
    sessions = next(c for c in before["categories"] if c["key"] == "sessions")
    assert sessions["count"] == 0

    client.post(
        "/api/v1/interviews/start",
        json={"role": "SDE", "type": "behavioral", "durationMinutes": 15,
              "mode": "voice", "consentGiven": True},
        headers=headers,
    )
    after = client.get("/api/v1/users/privacy", headers=headers).json()["data"]
    assert next(c for c in after["categories"] if c["key"] == "sessions")["count"] == 1


def test_privacy_inventory_states_what_is_never_stored(client, db_session):
    """
    Section 4.17 asks for a list of stored recordings. There are none, so rather
    than an empty list under a misleading heading, the screen says plainly what
    is never kept — which is the answer a candidate actually wants.
    """
    headers, _ = _login(client)
    data = client.get("/api/v1/users/privacy", headers=headers).json()["data"]
    keys = {c["key"] for c in data["neverStored"]}
    assert keys == {"audio", "video", "resume_file", "code_execution"}
    assert all(c["count"] == 0 and len(c["detail"]) > 30 for c in data["neverStored"])


def test_privacy_inventory_is_scoped_to_the_caller(client, db_session):
    owner, _ = _login(client)
    client.post(
        "/api/v1/interviews/start",
        json={"role": "SDE", "type": "behavioral", "durationMinutes": 15,
              "mode": "voice", "consentGiven": True},
        headers=owner,
    )
    other, _ = _login(client)
    data = client.get("/api/v1/users/privacy", headers=other).json()["data"]
    assert all(c["count"] == 0 for c in data["categories"])


def test_settings_endpoints_require_authentication(client):
    for path in ("/api/v1/users/profile", "/api/v1/users/notifications", "/api/v1/users/privacy"):
        assert client.get(path).status_code == 401


# ---------------------------------------------------------------------------
# Admin analytics (Section 16)
# ---------------------------------------------------------------------------
def _fill_cohort(db_session, count):
    """
    Add accounts directly rather than through signup.

    Signup is rate limited to 5/hour per IP (Section 12.1A) and every test here
    shares one TestClient address, so looping the API to build a cohort trips the
    limiter rather than testing analytics. These rows only need to exist to be
    counted.
    """
    from app.core.security import hash_password

    for _ in range(count):
        db_session.add(
            User(
                name="Cohort Member",
                email=f"cohort-{uuid.uuid4().hex[:10]}@example.com",
                password_hash=hash_password(PASSWORD),
            )
        )
    db_session.commit()


def _make_admin(client, db_session):
    headers, email = _login(client)
    user = db_session.query(User).filter(User.email == email).one()
    user.role = UserRole.ADMIN
    db_session.commit()
    return headers


def test_admin_analytics_is_refused_to_candidates(client, db_session):
    """
    Section 12.2: every admin endpoint verifies the role server-side. Hiding the
    nav link is not authorization.
    """
    headers, _ = _login(client)
    resp = client.get("/api/v1/admin/analytics", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_admin_analytics_requires_authentication(client):
    assert client.get("/api/v1/admin/analytics").status_code == 401


def test_a_small_cohort_is_suppressed_rather_than_averaged(client, db_session):
    """
    With four accounts an "average" is effectively individual data — anyone who
    knows three of them can solve for the fourth. The response says it is being
    withheld rather than returning a number that looks aggregate and is not.
    """
    headers = _make_admin(client, db_session)
    data = client.get("/api/v1/admin/analytics", headers=headers).json()["data"]

    assert data["suppressed"] is True
    assert data["cohortSize"] < admin_analytics.MIN_COHORT
    assert "withheld" in data["suppressionReason"]
    assert data["engagement"] == []
    assert data["categoryAverages"] == []


def test_a_large_enough_cohort_reports_aggregates(client, db_session):
    headers = _make_admin(client, db_session)
    _fill_cohort(db_session, admin_analytics.MIN_COHORT)

    data = client.get("/api/v1/admin/analytics", headers=headers).json()["data"]
    assert data["suppressed"] is False
    assert data["cohortSize"] >= admin_analytics.MIN_COHORT
    assert len(data["engagement"]) == 4
    assert all(0 <= row["percentage"] <= 100 for row in data["engagement"])


def test_analytics_never_identifies_anyone(client, db_session):
    """
    Section 16 is aggregate-only, and the organisation rule is absolute: no
    candidate PII in a response. Checked against the raw body so a field added
    later cannot quietly start carrying it.
    """
    headers = _make_admin(client, db_session)
    _fill_cohort(db_session, admin_analytics.MIN_COHORT)

    body = client.get("/api/v1/admin/analytics", headers=headers).text
    assert "@example.com" not in body
    for token in ("email", "userId", "user_id", "name"):
        assert token not in body, f"analytics leaked {token!r}"


def test_individual_drilldown_is_absent_and_says_why(client, db_session):
    """
    Section 16 allows drill-down only for candidates who opted into sharing. No
    opt-in exists here, so it is not built — and the response states that rather
    than leaving a reader to assume it is coming.
    """
    headers = _make_admin(client, db_session)
    data = client.get("/api/v1/admin/analytics", headers=headers).json()["data"]
    metrics = {row["metric"] for row in data["notMeasured"]}
    assert "Individual candidate drill-down" in metrics
    assert "Sign-language recognition accuracy" in metrics
    for row in data["notMeasured"]:
        assert len(row["reason"]) > 40


# ---------------------------------------------------------------------------
# Section 7.3 — ?compareRole=
# ---------------------------------------------------------------------------
def test_compare_role_returns_the_most_recent_completed_session(client, db_session):
    from datetime import timedelta

    from app.core.timeutils import utcnow
    from app.models.enums import SessionStatus
    from tests.feedback_factories import make_session

    headers, email = _login(client)
    user = db_session.query(User).filter(User.email == email).one()
    older = make_session(db_session, user, role="Backend Engineer")
    newer = make_session(db_session, user, role="Backend Engineer")
    make_session(db_session, user, role="Data Analyst")
    assert older.status is SessionStatus.COMPLETED

    # Both rows are written inside one tick of a ~15ms clock, so as created they
    # share a `started_at` and "most recent" has no answer. The query breaks the
    # tie deterministically, but on the id -- which is random, so the assertion
    # below would be a coin flip. Backdating the older one gives the ordering
    # something real to sort on, which is the behaviour under test.
    older.started_at = utcnow() - timedelta(hours=1)
    db_session.commit()

    data = client.get(
        "/api/v1/interviews/history?compareRole=Backend Engineer", headers=headers
    ).json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(newer.id)


def test_compare_role_matches_case_and_whitespace_insensitively(client, db_session):
    """`role_target` is free text the candidate typed; "SDE" and "sde " are the same target."""
    from tests.feedback_factories import make_session

    headers, email = _login(client)
    user = db_session.query(User).filter(User.email == email).one()
    make_session(db_session, user, role="SDE")

    assert len(client.get("/api/v1/interviews/history?compareRole=sde", headers=headers).json()["data"]) == 1
    assert len(client.get("/api/v1/interviews/history?compareRole=  SDE  ", headers=headers).json()["data"]) == 1


def test_compare_role_with_no_prior_attempt_returns_empty_not_an_error(client, db_session):
    """
    Section 7.3 says it returns null gracefully. A candidate on their first
    attempt at a role has not hit an error.
    """
    headers, _ = _login(client)
    resp = client.get("/api/v1/interviews/history?compareRole=Nobody Has Done This", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_compare_role_ignores_unfinished_sessions(client, db_session):
    from app.models.enums import SessionStatus
    from tests.feedback_factories import make_session

    headers, email = _login(client)
    user = db_session.query(User).filter(User.email == email).one()
    make_session(db_session, user, role="SDE", status=SessionStatus.IN_PROGRESS)

    assert client.get("/api/v1/interviews/history?compareRole=SDE", headers=headers).json()["data"] == []


def test_compare_role_is_scoped_to_the_caller(client, db_session):
    from tests.feedback_factories import make_session

    owner_headers, owner_email = _login(client)
    owner = db_session.query(User).filter(User.email == owner_email).one()
    make_session(db_session, owner, role="SDE")

    other_headers, _ = _login(client)
    assert client.get("/api/v1/interviews/history?compareRole=SDE", headers=other_headers).json()["data"] == []
