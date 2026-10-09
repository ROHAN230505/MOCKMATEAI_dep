"""
Aptitude practice endpoints (Phase 7).

Four routes: what content exists, start an attempt, submit it, read the result.
Plus history. The split matters for one reason — the question payload returned by
`start` has no answer in it, and the answers only become reachable through
`result`, which requires the attempt to have been submitted and to belong to the
caller. See `services/aptitude_service.py`.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import STANDARD_RATE_LIMIT, limiter
from app.core.responses import success
from app.database import get_db
from app.models.user import User
from app.content import aptitude_tests
from app.schemas.aptitude import (
    AptitudeQuestionOut,
    AttemptHistoryItem,
    AttemptOut,
    AttemptResultOut,
    MockTestOut,
    StartAttemptRequest,
    SubmitAttemptRequest,
    TimedAttemptOut,
)
from app.services import aptitude_service

router = APIRouter(prefix="/aptitude", tags=["aptitude"])


@router.get("/catalog")
@limiter.limit(STANDARD_RATE_LIMIT)
def catalog(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    What content exists, per topic and per topic-and-difficulty pair.

    The setup screen needs the pairs, not just the topics, to avoid offering a
    filter combination that cannot produce a test: there are eight verbal
    questions but only three easy ones, so "verbal + easy" would 409 after the
    candidate pressed start. Better to grey the combination out.
    """
    return success(aptitude_service.catalog_counts(db))


@router.post("/attempts")
@limiter.limit(STANDARD_RATE_LIMIT)
async def start_attempt(
    request: Request,
    body: StartAttemptRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    attempt, questions = await aptitude_service.start_attempt(db, user, body)
    return success(
        AttemptOut(
            attempt_id=attempt.id,
            total_questions=attempt.total_questions or len(questions),
            questions=[
                AptitudeQuestionOut(
                    id=question.id,
                    topic=question.topic,
                    difficulty=question.difficulty,
                    question_text=question.question_text,
                    options=list(question.options),
                )
                for question in questions
            ],
        ).model_dump(by_alias=True, mode="json")
    )


@router.post("/attempts/{attempt_id}/submit")
@limiter.limit(STANDARD_RATE_LIMIT)
def submit_attempt(
    request: Request,
    attempt_id: UUID,
    body: SubmitAttemptRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    attempt = aptitude_service.submit_attempt(db, user, attempt_id, body)
    result = aptitude_service.build_result(db, attempt)
    return success(AttemptResultOut(**result).model_dump(by_alias=True, mode="json"))


@router.get("/attempts/{attempt_id}")
@limiter.limit(STANDARD_RATE_LIMIT)
def read_attempt_result(
    request: Request,
    attempt_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    attempt = aptitude_service.get_attempt_for_user(db, user, attempt_id)
    result = aptitude_service.build_result(db, attempt)
    return success(AttemptResultOut(**result).model_dump(by_alias=True, mode="json"))


@router.get("/attempts")
@limiter.limit(STANDARD_RATE_LIMIT)
def attempt_history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    attempts = aptitude_service.list_attempts(db, user, limit=limit)
    return success(
        [
            AttemptHistoryItem(
                attempt_id=attempt.id,
                score=attempt.score,
                total_questions=attempt.total_questions,
                started_at=attempt.started_at,
                submitted_at=attempt.submitted_at,
            ).model_dump(by_alias=True, mode="json")
            for attempt in attempts
        ]
    )


@router.get("/tests")
@limiter.limit(STANDARD_RATE_LIMIT)
def list_tests(
    request: Request,
    user: User = Depends(get_current_user),
):
    """
    Section 4.13's "Full Mock Tests" list, with duration and question count shown
    before the candidate commits to starting one.
    """
    return success(
        [
            MockTestOut(
                id=test["id"],
                name=test["name"],
                description=test["description"],
                question_count=test["question_count"],
                duration_minutes=test["duration_minutes"],
                topics=test["topics"],
            ).model_dump(by_alias=True, mode="json")
            for test in aptitude_tests.TESTS
        ]
    )


@router.post("/tests/{test_id}/start")
@limiter.limit(STANDARD_RATE_LIMIT)
def start_test(
    request: Request,
    test_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    attempt, questions, test = aptitude_service.start_test_attempt(db, user, test_id)
    return success(
        TimedAttemptOut(
            attempt_id=attempt.id,
            total_questions=attempt.total_questions or len(questions),
            test_id=test["id"],
            test_name=test["name"],
            duration_minutes=test["duration_minutes"],
            time_remaining_seconds=aptitude_service.time_remaining_seconds(attempt) or 0,
            questions=[
                AptitudeQuestionOut(
                    id=question.id,
                    topic=question.topic,
                    difficulty=question.difficulty,
                    question_text=question.question_text,
                    options=list(question.options),
                )
                for question in questions
            ],
        ).model_dump(by_alias=True, mode="json")
    )


@router.get("/attempts/{attempt_id}/time")
@limiter.limit(STANDARD_RATE_LIMIT)
def attempt_time_remaining(
    request: Request,
    attempt_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    The server's view of the clock.

    Exists so a reload does not hand the candidate a fresh full-length timer, and
    so the countdown on screen can be re-anchored to `started_at` rather than
    drifting with a backgrounded tab.
    """
    attempt = aptitude_service.get_attempt_for_user(db, user, attempt_id)
    return success(
        {
            "timeRemainingSeconds": aptitude_service.time_remaining_seconds(attempt),
            "submitted": attempt.submitted_at is not None,
        }
    )
