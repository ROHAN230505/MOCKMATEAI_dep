"""
Shared builders for Phase 4 feedback tests.

Rows are inserted directly rather than driven through the interview WebSocket:
the scoring and report code under test cares only about what ended up in the
tables, and going through a live interview to set up a fixture would make these
tests fail for reasons that have nothing to do with feedback.
"""
import uuid

from app.core.timeutils import utcnow
from app.models.enums import InterviewMode, InterviewType, QuestionType, SessionStatus
from app.models.interview import AnswerEvaluation, InterviewAnswer, InterviewQuestion, InterviewSession
from app.models.user import User

STRONG_ANSWER = (
    "The situation was that our checkout API was timing out under load. My role was to find the "
    "bottleneck, so I profiled the endpoint and found we were making 40 sequential database calls "
    "per request. What I did was batch them into a single query and add a Redis cache for the "
    "product catalogue. As a result p95 latency dropped from 2100 milliseconds to 180, and the "
    "timeout alerts stopped entirely."
)

WEAK_ANSWER = "Um, I guess I would, like, probably just try some stuff and see."


def make_user(db, email="candidate@example.com", name="Ada Candidate") -> User:
    user = User(id=uuid.uuid4(), name=name, email=email, password_hash="x")
    db.add(user)
    db.commit()
    return user


def make_session(
    db,
    user,
    role="Backend Engineer",
    status=SessionStatus.COMPLETED,
    company=None,
) -> InterviewSession:
    session = InterviewSession(
        id=uuid.uuid4(),
        user_id=user.id,
        role_target=role,
        interview_type=InterviewType.MIXED,
        duration_minutes=15,
        mode=InterviewMode.VOICE,
        status=status,
        started_at=utcnow(),
        ended_at=utcnow() if status != SessionStatus.IN_PROGRESS else None,
        consent_given=True,
        target_company_name=company,
    )
    db.add(session)
    db.commit()
    return session


def add_turn(
    db,
    session,
    order: int,
    question: str,
    answer: str | None,
    *,
    relevance: int | None = None,
    completeness: int | None = None,
    skipped: bool = False,
    started_at: float | None = None,
    ended_at: float | None = None,
    parent_question_id=None,
    asked: bool = True,
):
    """
    `asked=False` writes a planned question the interviewer never reached.

    Worth having, because every question this factory made was implicitly
    asked, and that is exactly why a reporting bug survived: the planned rows
    are written up front and the interviewer routinely does not get to all of
    them, so unasked questions were appearing in transcripts as unanswered.
    No fixture could produce one, so no test could catch it.
    """
    q = InterviewQuestion(
        id=uuid.uuid4(),
        session_id=session.id,
        sequence_order=order,
        question_text=question,
        question_type=QuestionType.FOLLOWUP if parent_question_id else QuestionType.PLANNED,
        parent_question_id=parent_question_id,
        asked_at=utcnow() if asked else None,
    )
    db.add(q)
    db.flush()
    if answer is not None or skipped:
        a = InterviewAnswer(
            id=uuid.uuid4(),
            question_id=q.id,
            transcript_text=answer,
            is_skipped=skipped,
            answer_started_at=started_at,
            answer_ended_at=ended_at,
        )
        db.add(a)
        db.flush()
        if relevance is not None or completeness is not None:
            db.add(
                AnswerEvaluation(
                    id=uuid.uuid4(),
                    answer_id=a.id,
                    relevance_score=relevance,
                    completeness_score=completeness,
                )
            )
    db.commit()
    return q


def make_scored_session(db, user, role="Backend Engineer", company=None) -> InterviewSession:
    """A finished session with one strong answer, one weak answer and one skip."""
    session = make_session(db, user, role=role, company=company)
    add_turn(db, session, 1, "Tell me about a performance problem you fixed.", STRONG_ANSWER, relevance=9, completeness=9)
    add_turn(db, session, 2, "How would you debug a flaky test?", WEAK_ANSWER, relevance=3, completeness=2)
    add_turn(db, session, 3, "Explain database indexing.", None, skipped=True)
    return session
