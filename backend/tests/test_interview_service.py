import pytest

from app.content.question_bank import (
    BEHAVIORAL_QUESTIONS,
    OPENER,
    TECHNICAL_QUESTIONS,
    question_count_for_duration,
    select_planned_questions,
)
from app.core.responses import ApiError
from app.core.security import hash_password
from app.models.enums import InterviewMode, InterviewType, SessionStatus
from app.models.user import User
from app.services import interview_service


def _make_user(db_session) -> User:
    user = User(name="Ada Candidate", email="candidate@example.com", password_hash=hash_password("Str0ng!Pass"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.mark.parametrize("duration,expected", [(15, 3), (30, 6), (45, 9)])
def test_question_count_for_duration(duration, expected):
    assert question_count_for_duration(duration) == expected


def test_select_planned_questions_opener_always_first():
    questions = select_planned_questions(InterviewType.MIXED, 30)
    assert questions[0] == OPENER
    assert len(questions) == 6
    assert len(set(questions)) == len(questions)  # no duplicates


def test_select_planned_questions_respects_type_pool():
    technical = select_planned_questions(InterviewType.TECHNICAL, 30)[1:]
    assert all(q in TECHNICAL_QUESTIONS for q in technical)

    behavioral = select_planned_questions(InterviewType.BEHAVIORAL, 30)[1:]
    assert all(q in BEHAVIORAL_QUESTIONS for q in behavioral)


def test_start_session_creates_correct_question_count(db_session):
    user = _make_user(db_session)
    session = interview_service.start_session(
        db_session,
        user,
        role="SDE",
        interview_type=InterviewType.MIXED,
        duration_minutes=15,
        mode=InterviewMode.VOICE,
        consent_given=True,
        job_description_text=None,
        target_company_name=None,
    )
    assert session.status == SessionStatus.IN_PROGRESS
    assert session.started_at is not None
    assert len(session.questions) == 3


def test_start_session_requires_consent(db_session):
    user = _make_user(db_session)
    with pytest.raises(ApiError) as exc_info:
        interview_service.start_session(
            db_session,
            user,
            role="SDE",
            interview_type=InterviewType.MIXED,
            duration_minutes=15,
            mode=InterviewMode.VOICE,
            consent_given=False,
            job_description_text=None,
            target_company_name=None,
        )
    assert exc_info.value.code == "consent_required"


def test_start_session_accepts_sign_mode(db_session):
    """Phase 6: signed sessions persist with `mode = sign` and are otherwise ordinary."""
    user = _make_user(db_session)
    session = interview_service.start_session(
        db_session,
        user,
        role="SDE",
        interview_type=InterviewType.MIXED,
        duration_minutes=15,
        mode=InterviewMode.SIGN,
        consent_given=True,
        job_description_text=None,
        target_company_name=None,
    )
    assert session.mode is InterviewMode.SIGN
    assert session.status is SessionStatus.IN_PROGRESS
    assert len(session.questions) > 0


def test_get_session_for_user_enforces_ownership(db_session):
    owner = _make_user(db_session)
    other = User(name="Other Candidate", email="other@example.com", password_hash=hash_password("Str0ng!Pass"))
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    session = interview_service.start_session(
        db_session,
        owner,
        role="SDE",
        interview_type=InterviewType.BEHAVIORAL,
        duration_minutes=15,
        mode=InterviewMode.VOICE,
        consent_given=True,
        job_description_text=None,
        target_company_name=None,
    )

    with pytest.raises(ApiError) as exc_info:
        interview_service.get_session_for_user(db_session, other, session.id)
    assert exc_info.value.status_code == 404


def test_record_answer_updates_in_memory_relationship(db_session):
    user = _make_user(db_session)
    session = interview_service.start_session(
        db_session,
        user,
        role="SDE",
        interview_type=InterviewType.BEHAVIORAL,
        duration_minutes=15,
        mode=InterviewMode.VOICE,
        consent_given=True,
        job_description_text=None,
        target_company_name=None,
    )
    first_question = interview_service.get_next_unanswered_question(session)
    assert first_question is not None

    interview_service.record_answer(
        db_session,
        first_question,
        transcript_text="My answer.",
        is_skipped=False,
        asr_confidence_avg=0.92,
        answer_started_at=0.0,
        answer_ended_at=5.0,
    )

    assert first_question.answer is not None
    assert first_question.answer.transcript_text == "My answer."
    next_question = interview_service.get_next_unanswered_question(session)
    assert next_question is not None
    assert next_question.id != first_question.id


def test_end_session_marks_completed(db_session):
    user = _make_user(db_session)
    session = interview_service.start_session(
        db_session,
        user,
        role="SDE",
        interview_type=InterviewType.BEHAVIORAL,
        duration_minutes=15,
        mode=InterviewMode.VOICE,
        consent_given=True,
        job_description_text=None,
        target_company_name=None,
    )
    ended = interview_service.end_session(db_session, user, session.id)
    assert ended.status == SessionStatus.COMPLETED
    assert ended.ended_at is not None


def test_end_session_is_idempotent(db_session):
    user = _make_user(db_session)
    session = interview_service.start_session(
        db_session,
        user,
        role="SDE",
        interview_type=InterviewType.BEHAVIORAL,
        duration_minutes=15,
        mode=InterviewMode.VOICE,
        consent_given=True,
        job_description_text=None,
        target_company_name=None,
    )
    first = interview_service.end_session(db_session, user, session.id)
    second = interview_service.end_session(db_session, user, session.id)
    assert first.ended_at == second.ended_at
