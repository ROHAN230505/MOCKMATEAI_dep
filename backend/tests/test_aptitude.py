"""
Aptitude module tests (Phase 7).

The one that matters most is `test_the_answer_never_leaves_the_server_before_submission`.
Everything else is scoring arithmetic and ownership; that one is the difference
between a practice test and a quiz with the answers printed on the back.
"""
import pytest

from app.content.aptitude_bank import build_rows
from app.models.aptitude import AptitudeAttemptAnswer, AptitudeQuestion

PASSWORD = "Str0ng!Pass"


def _signup_and_login(client, email="apt@example.com"):
    client.post("/api/v1/auth/signup", json={"name": "Ada", "email": email, "password": PASSWORD})
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["data"]["accessToken"]


def _headers(token):
    return {"Authorization": "Bearer " + token}


@pytest.fixture()
def seeded(db_session):
    """The real bank, inserted directly — the migration is Postgres-side."""
    for row in build_rows():
        db_session.add(
            AptitudeQuestion(
                topic=row["topic"],
                difficulty=row["difficulty"],
                question_text=row["question_text"],
                options=row["options"],
                correct_option_index=row["correct_option_index"],
                company_pattern_tag=row["company_pattern_tag"],
            )
        )
    db_session.commit()
    return db_session


def _start(client, token, **body):
    payload = {"questionCount": 10}
    payload.update(body)
    return client.post("/api/v1/aptitude/attempts", json=payload, headers=_headers(token))


def test_catalog_reports_what_is_available(client, seeded):
    token = _signup_and_login(client)
    resp = client.get("/api/v1/aptitude/catalog", headers=_headers(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["topicCounts"]["quantitative"] == 8
    assert set(data["topicCounts"]) == {
        "quantitative", "logical_reasoning", "verbal_ability", "data_interpretation",
    }
    assert sum(data["difficultyCounts"].values()) == 32


def test_catalog_exposes_pair_counts_so_the_ui_can_avoid_an_impossible_filter(client, seeded):
    """
    Per-topic counts alone cannot tell the setup screen that "verbal + easy" has
    only three questions behind it and so cannot fill a five-question test.
    """
    token = _signup_and_login(client)
    data = client.get("/api/v1/aptitude/catalog", headers=_headers(token)).json()["data"]

    assert data["minQuestions"] == 5
    assert data["combinationCounts"]["verbal_ability:easy"] == 3
    assert data["combinationCounts"]["verbal_ability:easy"] < data["minQuestions"]
    # And the whole topic is fine, which is exactly the distinction the pair
    # counts exist to make visible.
    assert data["topicCounts"]["verbal_ability"] == 8


def test_starting_an_attempt_returns_questions_without_answers(client, seeded):
    token = _signup_and_login(client)
    resp = _start(client, token)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["totalQuestions"] == 10
    assert len(data["questions"]) == 10
    for question in data["questions"]:
        assert len(question["options"]) == 4
        assert "correctOptionIndex" not in question
        assert "correct_option_index" not in question


def test_the_answer_never_leaves_the_server_before_submission(client, seeded):
    """
    Checked against the serialised body, not the parsed shape: a field added to
    the schema later, or a stray debug dump, would show up here.
    """
    token = _signup_and_login(client)
    started = _start(client, token)
    assert "correct" not in started.text.lower()

    attempt_id = started.json()["data"]["attemptId"]
    # And it is still unavailable through the result route until submission.
    pending = client.get(f"/api/v1/aptitude/attempts/{attempt_id}", headers=_headers(token))
    assert pending.status_code == 409
    assert pending.json()["error"]["code"] == "attempt_not_submitted"
    assert "correct" not in pending.text.lower() or "correctOptionIndex" not in pending.text


def test_the_chosen_questions_are_persisted_at_start(client, seeded, db_session):
    """
    Without this an attempt would have no record of what it asked, so a
    submission could name any question and a reload would deal a fresh hand.
    """
    token = _signup_and_login(client)
    started = _start(client, token).json()["data"]
    rows = (
        db_session.query(AptitudeAttemptAnswer)
        .filter(AptitudeAttemptAnswer.attempt_id == started["attemptId"])
        .all()
    )
    assert len(rows) == 10
    assert {str(r.question_id) for r in rows} == {q["id"] for q in started["questions"]}
    assert all(r.selected_option_index is None and r.is_correct is None for r in rows)


def test_filters_narrow_the_selection(client, seeded):
    token = _signup_and_login(client)
    resp = _start(client, token, topics=["verbal_ability"], questionCount=5)
    assert resp.status_code == 200
    for question in resp.json()["data"]["questions"]:
        assert question["topic"] == "verbal_ability"


def test_a_filter_with_too_few_questions_is_refused_not_silently_shortened(client, seeded):
    """
    Only three easy verbal questions exist. Returning a three-question "test"
    would quietly change what the percentage score is a percentage *of*.
    """
    token = _signup_and_login(client)
    resp = _start(client, token, topics=["verbal_ability"], difficulties=["easy"], questionCount=5)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "not_enough_questions"


def test_an_impossible_filter_is_refused_rather_than_returning_a_short_test(client, db_session):
    """
    An empty bank cannot produce a five-question test, and silently returning
    two would make the percentage score mean something different.
    """
    token = _signup_and_login(client)
    resp = _start(client, token, topics=["quantitative"])
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "not_enough_questions"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _answer_all(client, token, started, *, correct: bool, db_session):
    """Answer every question in the attempt, either all right or all wrong."""
    answers = []
    for question in started["questions"]:
        row = (
            db_session.query(AptitudeQuestion)
            .filter(AptitudeQuestion.id == question["id"])
            .one()
        )
        index = row.correct_option_index
        if not correct:
            index = (index + 1) % len(row.options)
        answers.append({"questionId": question["id"], "selectedOptionIndex": index,
                        "timeSpentSeconds": 12})
    return client.post(
        f"/api/v1/aptitude/attempts/{started['attemptId']}/submit",
        json={"answers": answers},
        headers=_headers(token),
    )


def test_a_perfect_attempt_scores_100(client, seeded, db_session):
    token = _signup_and_login(client)
    started = _start(client, token).json()["data"]
    resp = _answer_all(client, token, started, correct=True, db_session=db_session)
    assert resp.status_code == 200
    result = resp.json()["data"]
    assert result["score"] == 100
    assert result["correctCount"] == 10
    assert result["totalQuestions"] == 10


def test_an_all_wrong_attempt_scores_zero(client, seeded, db_session):
    token = _signup_and_login(client)
    started = _start(client, token).json()["data"]
    result = _answer_all(client, token, started, correct=False, db_session=db_session).json()["data"]
    assert result["score"] == 0
    assert result["correctCount"] == 0


def test_score_is_a_percentage_not_a_correct_count(client, seeded, db_session):
    """
    The dashboard averages this column straight into a 0-100 readiness index, so
    a raw count would make that average incoherent across attempts of different
    lengths. Five right out of twenty is 25, not 5.
    """
    token = _signup_and_login(client)
    started = _start(client, token, questionCount=20).json()["data"]

    answers = []
    for position, question in enumerate(started["questions"]):
        row = db_session.query(AptitudeQuestion).filter(AptitudeQuestion.id == question["id"]).one()
        index = row.correct_option_index if position < 5 else (row.correct_option_index + 1) % 4
        answers.append({"questionId": question["id"], "selectedOptionIndex": index})

    result = client.post(
        f"/api/v1/aptitude/attempts/{started['attemptId']}/submit",
        json={"answers": answers},
        headers=_headers(token),
    ).json()["data"]

    assert result["correctCount"] == 5
    assert result["totalQuestions"] == 20
    assert result["score"] == 25


def test_unanswered_questions_count_as_incorrect_but_are_recorded_as_blank(client, seeded, db_session):
    """
    Deliberately unlike Section 9.8's treatment of a skipped interview question,
    which is excluded from the average. A blank in a timed multiple-choice test is
    the test measuring what it set out to measure. The row still keeps blank and
    wrong apart.
    """
    token = _signup_and_login(client)
    started = _start(client, token).json()["data"]

    resp = client.post(
        f"/api/v1/aptitude/attempts/{started['attemptId']}/submit",
        json={"answers": []},
        headers=_headers(token),
    )
    result = resp.json()["data"]
    assert result["score"] == 0
    assert result["correctCount"] == 0
    assert all(answer["selectedOptionIndex"] is None for answer in result["answers"])
    assert all(answer["isCorrect"] is False for answer in result["answers"])


def test_an_out_of_range_selection_is_treated_as_blank_not_as_wrong(client, seeded, db_session):
    """
    An index past the end of the options means the client and the stored question
    disagree about what the options are. Guessing which was meant would be worse
    than recording nothing.
    """
    token = _signup_and_login(client)
    started = _start(client, token, questionCount=5).json()["data"]
    answers = [
        {"questionId": q["id"], "selectedOptionIndex": 9} for q in started["questions"]
    ]
    result = client.post(
        f"/api/v1/aptitude/attempts/{started['attemptId']}/submit",
        json={"answers": answers},
        headers=_headers(token),
    ).json()["data"]
    assert all(answer["selectedOptionIndex"] is None for answer in result["answers"])


def test_the_result_shows_the_correct_answer_only_after_submission(client, seeded, db_session):
    token = _signup_and_login(client)
    started = _start(client, token, questionCount=5).json()["data"]
    result = _answer_all(client, token, started, correct=True, db_session=db_session).json()["data"]

    for answer in result["answers"]:
        assert "correctOptionIndex" in answer
        assert answer["correctOptionIndex"] == answer["selectedOptionIndex"]
        assert answer["questionText"]
        assert len(answer["options"]) == 4


def test_topic_breakdown_reports_absent_topics_as_null_not_zero(client, seeded, db_session):
    """
    A topic the attempt never asked about has no percentage. Reporting 0% would
    read as having got every question in it wrong.
    """
    token = _signup_and_login(client)
    started = _start(client, token, topics=["quantitative"], questionCount=5).json()["data"]
    result = _answer_all(client, token, started, correct=True, db_session=db_session).json()["data"]

    by_topic = {row["topic"]: row for row in result["topicBreakdown"]}
    assert by_topic["quantitative"]["percentage"] == 100.0
    assert by_topic["quantitative"]["total"] == 5
    for topic in ("verbal_ability", "logical_reasoning", "data_interpretation"):
        assert by_topic[topic]["percentage"] is None
        assert by_topic[topic]["total"] == 0


# ---------------------------------------------------------------------------
# Ownership, lifecycle and the dashboard handoff
# ---------------------------------------------------------------------------
def test_an_attempt_cannot_be_submitted_twice(client, seeded, db_session):
    token = _signup_and_login(client)
    started = _start(client, token, questionCount=5).json()["data"]
    _answer_all(client, token, started, correct=True, db_session=db_session)

    again = client.post(
        f"/api/v1/aptitude/attempts/{started['attemptId']}/submit",
        json={"answers": []},
        headers=_headers(token),
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "attempt_already_submitted"


def test_another_user_cannot_read_or_submit_someone_elses_attempt(client, seeded, db_session):
    owner = _signup_and_login(client, "owner-apt@example.com")
    started = _start(client, owner, questionCount=5).json()["data"]

    intruder = _signup_and_login(client, "intruder-apt@example.com")
    url = f"/api/v1/aptitude/attempts/{started['attemptId']}"
    assert client.get(url, headers=_headers(intruder)).status_code == 404
    assert client.post(f"{url}/submit", json={"answers": []}, headers=_headers(intruder)).status_code == 404


def test_aptitude_endpoints_require_authentication(client, seeded):
    assert client.get("/api/v1/aptitude/catalog").status_code == 401
    assert client.post("/api/v1/aptitude/attempts", json={"questionCount": 10}).status_code == 401


def test_history_lists_only_submitted_attempts(client, seeded, db_session):
    token = _signup_and_login(client)

    submitted = _start(client, token, questionCount=5).json()["data"]
    _answer_all(client, token, submitted, correct=True, db_session=db_session)
    # A second attempt left open.
    _start(client, token, questionCount=5)

    history = client.get("/api/v1/aptitude/attempts", headers=_headers(token)).json()["data"]
    assert len(history) == 1
    assert history[0]["attemptId"] == submitted["attemptId"]
    assert history[0]["score"] == 100


def test_a_submitted_attempt_reaches_the_dashboard(client, seeded, db_session):
    """
    `dashboard_service` already averaged `AptitudeAttempt.score` before this
    module existed, so Phase 7 lights up an existing tile rather than adding one.
    """
    token = _signup_and_login(client)
    before = client.get("/api/v1/dashboard/summary", headers=_headers(token)).json()["data"]
    assert before["aptitudeAvgScore"] is None

    started = _start(client, token, questionCount=5).json()["data"]
    _answer_all(client, token, started, correct=True, db_session=db_session)

    after = client.get("/api/v1/dashboard/summary", headers=_headers(token)).json()["data"]
    assert after["aptitudeAvgScore"] == 100.0


def test_an_open_attempt_does_not_affect_the_dashboard_average(client, seeded, db_session):
    """
    An unsubmitted attempt has a NULL score, so it must not drag the average
    down as a zero. `func.avg` ignores NULLs, and this pins that it stays true.
    """
    token = _signup_and_login(client)
    started = _start(client, token, questionCount=5).json()["data"]
    _answer_all(client, token, started, correct=True, db_session=db_session)
    _start(client, token, questionCount=5)  # left open

    summary = client.get("/api/v1/dashboard/summary", headers=_headers(token)).json()["data"]
    assert summary["aptitudeAvgScore"] == 100.0


def test_an_attempt_survives_a_question_being_deleted(client, seeded, db_session):
    """
    The recorded outcome still stands, but there is nothing left to review
    against, so the question is omitted from the review rather than rendered with
    empty fields.
    """
    token = _signup_and_login(client)
    started = _start(client, token, questionCount=5).json()["data"]
    _answer_all(client, token, started, correct=True, db_session=db_session)

    doomed = started["questions"][0]["id"]
    db_session.query(AptitudeAttemptAnswer).filter(
        AptitudeAttemptAnswer.question_id == doomed
    ).delete()
    db_session.query(AptitudeQuestion).filter(AptitudeQuestion.id == doomed).delete()
    db_session.commit()

    result = client.get(
        f"/api/v1/aptitude/attempts/{started['attemptId']}", headers=_headers(token)
    ).json()["data"]
    assert len(result["answers"]) == 4
    assert doomed not in [answer["questionId"] for answer in result["answers"]]
    # The stored score is unchanged: it recorded what happened at the time.
    assert result["score"] == 100
