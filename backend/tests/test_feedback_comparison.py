"""
Before & After comparison tests (Section 4.11A).

The rules being protected here are the honesty ones: no comparison against a
different role without flagging it, no delta against a category nothing
measured, and no calling a two-point wobble "improvement".
"""
from datetime import timedelta

import pytest

from app.core.timeutils import utcnow
from app.models.enums import FeedbackGenerationStatus
from app.models.feedback import FeedbackReport
from app.services.feedback import comparison as comparison_service
from tests.feedback_factories import make_session, make_user


def _backdate(db, session, days: int):
    """Give a session a distinct point in time so 'previous' is unambiguous."""
    moment = utcnow() - timedelta(days=days)
    session.created_at = moment
    session.started_at = moment
    session.ended_at = moment + timedelta(minutes=15)
    db.commit()
    return session


def _attach_report(db, session, *, overall, content=None, communication=None, status=FeedbackGenerationStatus.READY):
    report = FeedbackReport(
        session_id=session.id,
        overall_readiness_score=overall,
        content_score=content,
        communication_score=communication,
        summary_text="Summary.",
        generation_status=status,
        generated_at=utcnow(),
        generated_by="deterministic",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_no_comparison_on_a_first_interview(db_session):
    user = make_user(db_session)
    current = _backdate(db_session, make_session(db_session, user), days=0)
    report = _attach_report(db_session, current, overall=61.0)

    assert comparison_service.get_comparison(db_session, user.id, current, report) is None


def test_improvement_is_reported_with_the_delta(db_session):
    user = make_user(db_session)
    previous = _backdate(db_session, make_session(db_session, user), days=7)
    _attach_report(db_session, previous, overall=52.0, content=50.0, communication=55.0)
    current = _backdate(db_session, make_session(db_session, user), days=0)
    current_report = _attach_report(db_session, current, overall=68.0, content=70.0, communication=65.0)

    result = comparison_service.get_comparison(db_session, user.id, current, current_report)

    assert result is not None
    assert result.previous_session_id == str(previous.id)
    assert result.same_role is True
    overall = next(d for d in result.deltas if d.category == "overall")
    assert overall.delta == pytest.approx(16.0)
    assert overall.direction == "improved"
    assert "up 16 points" in result.headline


def test_a_small_movement_is_not_dressed_up_as_progress(db_session):
    user = make_user(db_session)
    previous = _backdate(db_session, make_session(db_session, user), days=3)
    _attach_report(db_session, previous, overall=60.0)
    current = _backdate(db_session, make_session(db_session, user), days=0)
    current_report = _attach_report(db_session, current, overall=62.0)

    result = comparison_service.get_comparison(db_session, user.id, current, current_report)
    overall = next(d for d in result.deltas if d.category == "overall")

    assert overall.delta == pytest.approx(2.0)
    assert overall.direction == "unchanged"
    assert "held steady" in result.headline


def test_a_decline_is_stated_plainly(db_session):
    user = make_user(db_session)
    previous = _backdate(db_session, make_session(db_session, user), days=5)
    _attach_report(db_session, previous, overall=74.0)
    current = _backdate(db_session, make_session(db_session, user), days=0)
    current_report = _attach_report(db_session, current, overall=55.0)

    result = comparison_service.get_comparison(db_session, user.id, current, current_report)
    overall = next(d for d in result.deltas if d.category == "overall")

    assert overall.direction == "declined"
    assert "down 19 points" in result.headline


def test_unmeasured_categories_are_not_comparable_rather_than_unchanged(db_session):
    user = make_user(db_session)
    previous = _backdate(db_session, make_session(db_session, user), days=2)
    _attach_report(db_session, previous, overall=60.0, content=60.0)
    current = _backdate(db_session, make_session(db_session, user), days=0)
    current_report = _attach_report(db_session, current, overall=64.0, content=64.0)

    result = comparison_service.get_comparison(db_session, user.id, current, current_report)
    confidence = next(d for d in result.deltas if d.category == "confidence")

    assert confidence.delta is None
    assert confidence.direction == "not_comparable"


def test_same_role_is_preferred_over_a_more_recent_different_role(db_session):
    user = make_user(db_session)
    same_role = _backdate(db_session, make_session(db_session, user, role="Backend Engineer"), days=9)
    _attach_report(db_session, same_role, overall=50.0)
    other_role = _backdate(db_session, make_session(db_session, user, role="Product Manager"), days=2)
    _attach_report(db_session, other_role, overall=90.0)
    current = _backdate(db_session, make_session(db_session, user, role="Backend Engineer"), days=0)
    current_report = _attach_report(db_session, current, overall=60.0)

    result = comparison_service.get_comparison(db_session, user.id, current, current_report)

    assert result.previous_session_id == str(same_role.id)
    assert result.same_role is True


def test_a_different_role_comparison_is_flagged_as_rough(db_session):
    user = make_user(db_session)
    other_role = _backdate(db_session, make_session(db_session, user, role="Product Manager"), days=4)
    _attach_report(db_session, other_role, overall=70.0)
    current = _backdate(db_session, make_session(db_session, user, role="Backend Engineer"), days=0)
    current_report = _attach_report(db_session, current, overall=80.0)

    result = comparison_service.get_comparison(db_session, user.id, current, current_report)

    assert result.same_role is False
    assert "different role" in result.headline


def test_unfinished_reports_are_never_compared_against(db_session):
    user = make_user(db_session)
    previous = _backdate(db_session, make_session(db_session, user), days=6)
    _attach_report(db_session, previous, overall=None, status=FeedbackGenerationStatus.PROCESSING)
    current = _backdate(db_session, make_session(db_session, user), days=0)
    current_report = _attach_report(db_session, current, overall=65.0)

    assert comparison_service.get_comparison(db_session, user.id, current, current_report) is None


def test_another_users_sessions_are_never_compared_against(db_session):
    mine = make_user(db_session, email="mine@example.com")
    theirs = make_user(db_session, email="theirs@example.com")
    their_session = _backdate(db_session, make_session(db_session, theirs), days=3)
    _attach_report(db_session, their_session, overall=95.0)
    current = _backdate(db_session, make_session(db_session, mine), days=0)
    current_report = _attach_report(db_session, current, overall=40.0)

    assert comparison_service.get_comparison(db_session, mine.id, current, current_report) is None


def test_comparison_appears_in_the_report_payload(client, db_session):
    """End-to-end: Section 4.11A's block is part of the report response."""
    from app.models.user import User
    from tests.feedback_factories import make_scored_session

    client.post(
        "/api/v1/auth/signup",
        json={"name": "Ada", "email": "compare@example.com", "password": "Str0ng!Pass"},
    )
    login = client.post("/api/v1/auth/login", json={"email": "compare@example.com", "password": "Str0ng!Pass"})
    token = login.json()["data"]["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}
    user = db_session.query(User).filter(User.email == "compare@example.com").one()

    first = _backdate(db_session, make_scored_session(db_session, user), days=4)
    client.post(f"/api/v1/feedback/{first.id}/generate", headers=headers)
    second = _backdate(db_session, make_scored_session(db_session, user), days=0)
    client.post(f"/api/v1/feedback/{second.id}/generate", headers=headers)

    resp = client.get(f"/api/v1/feedback/{second.id}", headers=headers)
    comparison = resp.json()["data"]["comparison"]

    assert comparison is not None
    assert comparison["previousSessionId"] == str(first.id)
    assert comparison["sameRole"] is True
    assert comparison["headline"]
    # Delta identifiers line up with `categoryScores[].category`, plus "overall".
    categories = {delta["category"] for delta in comparison["deltas"]}
    assert categories == {"overall", "content", "communication", "confidence", "body_language"}

