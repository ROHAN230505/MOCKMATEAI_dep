"""
"This Week's Focus" recommendations (Section 4.5, feature 38).

This was `weekly_focus=[]` — hardcoded — until now, and the dashboard rendered
the panel conditionally so the gap was invisible. These tests exist mostly to
stop it becoming invisible again, and to pin the two properties that make the
advice worth reading: it is ordered by real index impact, and nothing is
suggested that was not measured.
"""
from app.models.user import User
from app.services import recommendations
from app.services.feedback.scoring import load_index_weights

PASSWORD = "Str0ng!Pass"


def _signup_and_login(client, email="focus@example.com"):
    client.post("/api/v1/auth/signup", json={"name": "Ada", "email": email, "password": PASSWORD})
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["data"]["accessToken"]


def _headers(token):
    return {"Authorization": "Bearer " + token}


def _user(db, email="focus@example.com"):
    return db.query(User).filter(User.email == email).one()


def test_a_brand_new_account_is_pointed_at_the_biggest_gaps_first(client, db_session):
    """
    Nothing has been measured, so every module is an empty slot. They must be
    ordered by index weight — interviews (0.45) before DSA (0.25) before
    aptitude (0.20) before resume (0.10) — not by any editorial preference.
    """
    _signup_and_login(client)
    items = recommendations.build_focus(db_session, _user(db_session), load_index_weights(db_session))

    assert len(items) == recommendations.MAX_ITEMS
    assert [item.id for item in items][0] == "first-interview"
    gains = [item.projected_gain for item in items]
    assert gains == sorted(gains, reverse=True), gains


def test_every_item_carries_the_evidence_behind_it(client, db_session):
    _signup_and_login(client)
    for item in recommendations.build_focus(db_session, _user(db_session), load_index_weights(db_session)):
        assert item.reason.strip(), item.id
        assert item.route.startswith("/"), item.id
        assert item.cta.strip()
        assert item.projected_gain > 0


def test_routes_point_at_modules_that_exist(client, db_session):
    _signup_and_login(client)
    routes = {i.route for i in recommendations.build_focus(db_session, _user(db_session), load_index_weights(db_session))}
    assert routes <= {"/interview/setup", "/aptitude", "/dsa", "/resume"}


def test_the_dashboard_surfaces_them(client, db_session):
    token = _signup_and_login(client)
    focus = client.get("/api/v1/dashboard/summary", headers=_headers(token)).json()["data"]["weeklyFocus"]
    assert len(focus) > 0
    first = focus[0]
    assert set(first) == {"id", "label", "reason", "route", "cta", "projectedGain"}
    assert first["route"] == "/interview/setup"


def test_a_module_already_done_well_is_not_recommended(client, db_session):
    """
    The rule that keeps this from being noise: a candidate doing fine somewhere
    must not be told to work on it just to fill three slots.
    """
    from app.models.resume import ResumeAnalysis
    from app.core.timeutils import utcnow

    _signup_and_login(client)
    user = _user(db_session)
    db_session.add(
        ResumeAnalysis(
            user_id=user.id, file_storage_url="not-stored:test", ats_score=95, analyzed_at=utcnow()
        )
    )
    db_session.commit()

    ids = {i.id for i in recommendations.build_focus(db_session, user, load_index_weights(db_session))}
    assert "first-resume" not in ids
    assert "resume-score" not in ids


def test_ordering_follows_the_configured_weights_not_a_hardcoded_list(client, db_session):
    """
    If the index weights are retuned, the advice must reprioritise with them —
    otherwise the dashboard would be recommending one thing while scoring another.
    """
    _signup_and_login(client)
    user = _user(db_session)

    normal = recommendations.build_focus(db_session, user, load_index_weights(db_session))
    assert normal[0].id == "first-interview"

    # Resume suddenly dominates the index.
    flipped = recommendations.build_focus(
        db_session,
        user,
        {"mock_interview_avg": 0.05, "aptitude_avg": 0.05, "dsa_progress_pct": 0.05, "resume_ats_score": 0.85},
    )
    assert flipped[0].id == "first-resume"


def test_nothing_worth_less_than_a_couple_of_points_is_suggested(client, db_session):
    _signup_and_login(client)
    user = _user(db_session)
    tiny = recommendations.build_focus(
        db_session,
        user,
        {"mock_interview_avg": 0.001, "aptitude_avg": 0.001, "dsa_progress_pct": 0.001, "resume_ats_score": 0.001},
    )
    assert tiny == []


def test_the_weakest_interview_category_is_the_one_named(client, db_session):
    """
    Averaged across reports, not taken from the latest, so one bad session does
    not redirect a whole week.
    """
    from tests.feedback_factories import make_scored_session
    from app.models.feedback import FeedbackReport
    from app.core.timeutils import utcnow

    _signup_and_login(client)
    user = _user(db_session)
    session = make_scored_session(db_session, user)
    db_session.add(
        FeedbackReport(
            session_id=session.id,
            overall_readiness_score=55,
            content_score=80,
            communication_score=35,  # the weakest
            confidence_score=70,
            body_language_score=75,
            generated_at=utcnow(),
        )
    )
    db_session.commit()

    items = recommendations.build_focus(db_session, user, load_index_weights(db_session))
    interview = next(i for i in items if i.id.startswith("interview-"))
    assert interview.id == "interview-communication_score"
    assert "structure answers" in interview.label
    assert "35" in interview.reason


def test_an_unmeasured_category_is_never_named_as_the_weakness(client, db_session):
    """
    A candidate whose camera was off has a NULL body-language score. Treating
    NULL as zero would make "body language" everyone's top recommendation.
    """
    from tests.feedback_factories import make_scored_session
    from app.models.feedback import FeedbackReport
    from app.core.timeutils import utcnow

    _signup_and_login(client)
    user = _user(db_session)
    session = make_scored_session(db_session, user)
    db_session.add(
        FeedbackReport(
            session_id=session.id,
            overall_readiness_score=60,
            content_score=75,
            communication_score=65,
            confidence_score=None,
            body_language_score=None,
            generated_at=utcnow(),
        )
    )
    db_session.commit()

    items = recommendations.build_focus(db_session, user, load_index_weights(db_session))
    interview = next(i for i in items if i.id.startswith("interview-"))
    assert interview.id == "interview-communication_score"
    assert "body_language" not in interview.id
    assert "confidence" not in interview.id


def test_the_weakest_aptitude_topic_is_named(client, db_session):
    from app.content.aptitude_bank import build_rows
    from app.models.aptitude import AptitudeAttempt, AptitudeAttemptAnswer, AptitudeQuestion
    from app.core.timeutils import utcnow

    _signup_and_login(client)
    user = _user(db_session)

    questions = []
    for row in build_rows():
        question = AptitudeQuestion(
            topic=row["topic"], difficulty=row["difficulty"], question_text=row["question_text"],
            options=row["options"], correct_option_index=row["correct_option_index"],
        )
        db_session.add(question)
        questions.append((row["topic"].value, question))
    db_session.flush()

    attempt = AptitudeAttempt(user_id=user.id, started_at=utcnow(), submitted_at=utcnow(),
                              score=50, total_questions=16)
    db_session.add(attempt)
    db_session.flush()

    # Verbal answered entirely wrong; quantitative entirely right.
    for topic, question in questions:
        if topic not in {"verbal_ability", "quantitative"}:
            continue
        db_session.add(
            AptitudeAttemptAnswer(
                attempt_id=attempt.id, question_id=question.id,
                selected_option_index=0, is_correct=(topic == "quantitative"),
            )
        )
    db_session.commit()

    items = recommendations.build_focus(db_session, user, load_index_weights(db_session))
    aptitude = next(i for i in items if i.id.startswith("aptitude-"))
    assert aptitude.id == "aptitude-verbal_ability"
    assert "verbal ability" in aptitude.label
    assert "0%" in aptitude.reason


def test_a_topic_with_too_few_answers_is_not_called_a_weakness(client, db_session):
    """Two wrong answers in a topic is a coincidence, not a measurement."""
    from app.models.aptitude import AptitudeAttempt, AptitudeAttemptAnswer, AptitudeQuestion
    from app.models.enums import AptitudeTopic, Difficulty
    from app.core.timeutils import utcnow

    _signup_and_login(client)
    user = _user(db_session)

    attempt = AptitudeAttempt(user_id=user.id, started_at=utcnow(), submitted_at=utcnow(),
                              score=0, total_questions=2)
    db_session.add(attempt)
    db_session.flush()
    for index in range(2):
        question = AptitudeQuestion(
            topic=AptitudeTopic.VERBAL_ABILITY, difficulty=Difficulty.EASY,
            question_text=f"Q{index}", options=["a", "b", "c", "d"], correct_option_index=0,
        )
        db_session.add(question)
        db_session.flush()
        db_session.add(
            AptitudeAttemptAnswer(attempt_id=attempt.id, question_id=question.id,
                                  selected_option_index=1, is_correct=False)
        )
    db_session.commit()

    assert recommendations._weakest_aptitude_topic(db_session, user) is None
