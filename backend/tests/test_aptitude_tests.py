"""
Timed mock tests (Sections 4.13, 4.14, 11.1).

The distinction that matters: a mock test is the same attempt row as practice
with `test_id` set, so scoring, history and the dashboard need no branch. What
differs is a clock — and the clock is the server's, derived from `started_at`,
not a number the client counts down from.
"""
import uuid
from datetime import timedelta

from app.content import aptitude_tests
from app.content.aptitude_bank import build_rows
from app.core.timeutils import utcnow
from app.models.aptitude import AptitudeAttempt, AptitudeQuestion

PASSWORD = "Str0ng!Pass"


def _login(client, email=None):
    email = email or f"mt-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/v1/auth/signup", json={"name": "Ada", "email": email, "password": PASSWORD})
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["data"]["accessToken"]
    return {"Authorization": "Bearer " + token}


def _seed(db):
    for row in build_rows():
        db.add(
            AptitudeQuestion(
                topic=row["topic"], difficulty=row["difficulty"],
                question_text=row["question_text"], options=row["options"],
                correct_option_index=row["correct_option_index"],
                company_pattern_tag=row["company_pattern_tag"],
            )
        )
    db.commit()


def test_tests_are_listed_with_what_a_candidate_needs_to_decide(client, db_session):
    """Section 4.13: duration and question count shown before starting."""
    headers = _login(client)
    tests = client.get("/api/v1/aptitude/tests", headers=headers).json()["data"]
    assert len(tests) == len(aptitude_tests.TESTS)
    for test in tests:
        assert test["durationMinutes"] > 0
        assert test["questionCount"] > 0
        assert test["description"]
        assert test["topics"]


def test_no_test_claims_to_match_a_real_company(client, db_session):
    """
    Section 4.6 forbids implying verified knowledge of an employer's process, and
    nobody here has data on how any real company builds its test. Sets are
    described by what they contain instead.
    """
    headers = _login(client)
    body = client.get("/api/v1/aptitude/tests", headers=headers).text.lower()
    for company in ("google", "amazon", "microsoft", "tcs", "infosys", "wipro"):
        assert company not in body


def test_starting_a_test_sets_test_id_and_returns_a_server_clock(client, db_session):
    _seed(db_session)
    headers = _login(client)
    test = aptitude_tests.TESTS[0]

    data = client.post(f"/api/v1/aptitude/tests/{test['id']}/start", headers=headers).json()["data"]
    assert data["testId"] == str(test["id"])
    assert data["testName"] == test["name"]
    assert data["durationMinutes"] == test["duration_minutes"]
    # Counted down from the server's own start time, not handed over as a duration.
    assert 0 < data["timeRemainingSeconds"] <= test["duration_minutes"] * 60
    assert len(data["questions"]) == test["question_count"]

    row = db_session.query(AptitudeAttempt).filter(
        AptitudeAttempt.id == uuid.UUID(data["attemptId"])
    ).one()
    assert row.test_id == test["id"]


def test_a_practice_attempt_still_has_no_test_id(client, db_session):
    """Section 8's "null = practice mode" — the one column that distinguishes them."""
    _seed(db_session)
    headers = _login(client)
    data = client.post("/api/v1/aptitude/attempts", json={"questionCount": 10}, headers=headers).json()["data"]
    row = db_session.query(AptitudeAttempt).filter(
        AptitudeAttempt.id == uuid.UUID(data["attemptId"])
    ).one()
    assert row.test_id is None


def test_an_unknown_test_is_404(client, db_session):
    headers = _login(client)
    resp = client.post(f"/api/v1/aptitude/tests/{uuid.uuid4()}/start", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "test_not_found"


def test_the_clock_is_the_servers_not_the_clients(client, db_session):
    """
    A reload must not hand back a fresh full-length timer. The remaining time is
    recomputed from `started_at` every time it is asked for.
    """
    _seed(db_session)
    headers = _login(client)
    test = aptitude_tests.TESTS[0]
    started = client.post(f"/api/v1/aptitude/tests/{test['id']}/start", headers=headers).json()["data"]

    attempt = db_session.query(AptitudeAttempt).filter(
        AptitudeAttempt.id == uuid.UUID(started["attemptId"])
    ).one()
    # Rewind the start as if most of the test had already elapsed.
    attempt.started_at = utcnow() - timedelta(minutes=test["duration_minutes"] - 1)
    db_session.commit()

    remaining = client.get(
        f"/api/v1/aptitude/attempts/{started['attemptId']}/time", headers=headers
    ).json()["data"]["timeRemainingSeconds"]
    assert 0 < remaining <= 61, remaining


def test_the_clock_floors_at_zero_rather_than_going_negative(client, db_session):
    _seed(db_session)
    headers = _login(client)
    test = aptitude_tests.TESTS[0]
    started = client.post(f"/api/v1/aptitude/tests/{test['id']}/start", headers=headers).json()["data"]

    attempt = db_session.query(AptitudeAttempt).filter(
        AptitudeAttempt.id == uuid.UUID(started["attemptId"])
    ).one()
    attempt.started_at = utcnow() - timedelta(hours=3)
    db_session.commit()

    assert client.get(
        f"/api/v1/aptitude/attempts/{started['attemptId']}/time", headers=headers
    ).json()["data"]["timeRemainingSeconds"] == 0


def test_practice_attempts_report_no_clock_at_all(client, db_session):
    """Section 11.1: practice is untimed. None, not zero — zero means "out of time"."""
    _seed(db_session)
    headers = _login(client)
    started = client.post("/api/v1/aptitude/attempts", json={"questionCount": 10}, headers=headers).json()["data"]
    data = client.get(
        f"/api/v1/aptitude/attempts/{started['attemptId']}/time", headers=headers
    ).json()["data"]
    assert data["timeRemainingSeconds"] is None


def _answer_all(client, headers, started, db, correct=True):
    answers = []
    for q in started["questions"]:
        row = db.query(AptitudeQuestion).filter(AptitudeQuestion.id == uuid.UUID(q["id"])).one()
        index = row.correct_option_index if correct else (row.correct_option_index + 1) % 4
        answers.append({"questionId": q["id"], "selectedOptionIndex": index, "timeSpentSeconds": 10})
    return client.post(
        f"/api/v1/aptitude/attempts/{started['attemptId']}/submit",
        json={"answers": answers},
        headers=headers,
    ).json()["data"]


def test_a_timed_result_reports_the_test_and_the_time_taken(client, db_session):
    _seed(db_session)
    headers = _login(client)
    test = aptitude_tests.TESTS[0]
    started = client.post(f"/api/v1/aptitude/tests/{test['id']}/start", headers=headers).json()["data"]

    result = _answer_all(client, headers, started, db_session)
    assert result["testName"] == test["name"]
    assert result["durationMinutes"] == test["duration_minutes"]
    assert result["timeTakenSeconds"] is not None
    assert result["submittedLate"] is False
    assert result["score"] == 100


def test_a_late_submission_is_recorded_as_late_without_losing_the_work(client, db_session):
    """
    Derived from two timestamps rather than a stored flag, so nothing can be set
    wrong. And accepted rather than rejected: a practice tool that throws away a
    candidate's answers for being ninety seconds over has taught them nothing.
    """
    _seed(db_session)
    headers = _login(client)
    test = aptitude_tests.TESTS[0]
    started = client.post(f"/api/v1/aptitude/tests/{test['id']}/start", headers=headers).json()["data"]

    attempt = db_session.query(AptitudeAttempt).filter(
        AptitudeAttempt.id == uuid.UUID(started["attemptId"])
    ).one()
    attempt.started_at = utcnow() - timedelta(minutes=test["duration_minutes"] + 5)
    db_session.commit()

    result = _answer_all(client, headers, started, db_session)
    assert result["submittedLate"] is True
    # The answers still counted.
    assert result["score"] == 100
    assert result["correctCount"] == test["question_count"]


def test_a_practice_result_carries_no_timing_fields(client, db_session):
    _seed(db_session)
    headers = _login(client)
    started = client.post("/api/v1/aptitude/attempts", json={"questionCount": 10}, headers=headers).json()["data"]
    result = _answer_all(client, headers, started, db_session)
    assert result["testName"] is None
    assert result["durationMinutes"] is None
    assert result["submittedLate"] is False


def test_a_timed_attempt_reaches_the_dashboard_like_any_other(client, db_session):
    """One column's difference — the readiness index must not care which it was."""
    _seed(db_session)
    headers = _login(client)
    test = aptitude_tests.TESTS[0]
    started = client.post(f"/api/v1/aptitude/tests/{test['id']}/start", headers=headers).json()["data"]
    _answer_all(client, headers, started, db_session)

    summary = client.get("/api/v1/dashboard/summary", headers=headers).json()["data"]
    assert summary["aptitudeAvgScore"] == 100.0


def test_mock_tests_require_authentication(client):
    assert client.get("/api/v1/aptitude/tests").status_code == 401
    assert client.post(f"/api/v1/aptitude/tests/{aptitude_tests.TESTS[0]['id']}/start").status_code == 401
