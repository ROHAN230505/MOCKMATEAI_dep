"""
DSA practice endpoints (Phase 7).

The hidden test cases sit behind their own route rather than travelling with the
problem. That does not make them secret — grading runs in the candidate's browser
so they have to arrive there eventually, and `schemas/dsa.py` says so out loud —
but it keeps them off the problem-browsing path, so merely reading a problem does
not hand over its cases.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import GENERATE_PROBLEM_RATE_LIMIT, STANDARD_RATE_LIMIT, limiter
from app.core.responses import ApiError, success
from app.database import get_db
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.dsa import (
    GenerateProblemRequest,
    DSAProblemListItem,
    DSAProblemOut,
    DSASubmissionOut,
    HiddenTestCasesOut,
    HintOut,
    HintRequest,
    SubmitSolutionRequest,
)
from app.services import ai_quota, dsa_hints, dsa_service

router = APIRouter(prefix="/dsa", tags=["dsa"])


@router.get("/problems")
@limiter.limit(STANDARD_RATE_LIMIT)
def list_problems(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return success(
        [
            DSAProblemListItem(**item).model_dump(by_alias=True, mode="json")
            for item in dsa_service.list_problems(db, user)
        ]
    )


@router.get("/problems/{problem_id}")
@limiter.limit(STANDARD_RATE_LIMIT)
def read_problem(
    request: Request,
    problem_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    problem = dsa_service.get_problem(db, problem_id)
    return success(
        DSAProblemOut(
            id=problem.id,
            title=problem.title,
            topic=problem.topic,
            difficulty=problem.difficulty,
            statement_text=problem.statement_text,
            constraints_text=problem.constraints_text,
            starter_code=problem.starter_code or {},
            function_name=dsa_service.function_name(problem),
            sample_test_cases=dsa_service.sample_cases(problem),
            # The count, not the cases. Enough for the UI to say "and 4 hidden
            # tests" without being the thing that delivers them.
            hidden_test_case_count=len(dsa_service.hidden_cases(problem)),
            solved=dsa_service.is_solved(db, user, problem.id),
        ).model_dump(by_alias=True, mode="json")
    )


@router.post("/problems/{problem_id}/test-cases")
@limiter.limit(STANDARD_RATE_LIMIT)
def read_hidden_test_cases(
    request: Request,
    problem_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    The hidden cases, for the in-browser runner.

    A POST rather than a GET because it is the act of starting a graded run, not
    a cacheable read — and because a GET would end up in browser history and
    server logs as a URL that looks like problem content.
    """
    problem = dsa_service.get_problem(db, problem_id)
    return success(
        HiddenTestCasesOut(hidden_test_cases=dsa_service.hidden_cases(problem)).model_dump(
            by_alias=True, mode="json"
        )
    )


@router.post("/problems/{problem_id}/submit")
@limiter.limit(STANDARD_RATE_LIMIT)
def submit_solution(
    request: Request,
    problem_id: UUID,
    body: SubmitSolutionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    problem = dsa_service.get_problem(db, problem_id)
    submission = dsa_service.record_submission(db, user, problem, body)
    return success(
        DSASubmissionOut(
            id=submission.id,
            problem_id=submission.problem_id,
            language=submission.language,
            status=submission.status,
            runtime_ms=submission.runtime_ms,
            hints_used_count=submission.hints_used_count,
            submitted_at=submission.submitted_at,
        ).model_dump(by_alias=True, mode="json")
    )


@router.get("/problems/{problem_id}/submissions")
@limiter.limit(STANDARD_RATE_LIMIT)
def list_submissions(
    request: Request,
    problem_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    submissions = dsa_service.list_submissions(db, user, problem_id, limit=limit)
    return success(
        [
            DSASubmissionOut(
                id=s.id,
                problem_id=s.problem_id,
                language=s.language,
                status=s.status,
                runtime_ms=s.runtime_ms,
                hints_used_count=s.hints_used_count,
                submitted_at=s.submitted_at,
            ).model_dump(by_alias=True, mode="json")
            for s in submissions
        ]
    )


@router.post("/problems/{problem_id}/hint")
@limiter.limit(STANDARD_RATE_LIMIT)
async def request_hint(
    request: Request,
    problem_id: UUID,
    body: HintRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis),
):
    """
    One escalating nudge. Metered, because it is a real provider call.

    Charged against the same per-user AI budget an interview turn draws on
    (Section 12.1A), so a candidate cannot spend the account's daily allowance on
    hints and then find they cannot start an interview.
    """
    problem = dsa_service.get_problem(db, problem_id)

    if body.hint_index >= dsa_hints.MAX_HINTS:
        raise ApiError(
            status_code=409,
            code="no_more_hints",
            message="There are no further hints for this problem.",
        )

    ai_quota.consume_hint(redis_client, str(user.id))
    hint, generated_by = await dsa_hints.generate_hint(problem, body.code, body.hint_index)
    return success(
        HintOut(
            hint=hint,
            generated_by=generated_by,
            hints_used_count=body.hint_index + 1,
        ).model_dump(by_alias=True, mode="json")
    )


@router.post("/problems/generate")
@limiter.limit(GENERATE_PROBLEM_RATE_LIMIT)
async def generate_problem(
    request: Request,
    body: GenerateProblemRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Write a brand-new problem on demand, verified before it is returned.

    Rate-limited harder than the standard tier because each call is two
    provider round trips and takes several seconds -- this is the one DSA
    endpoint where a tight loop costs real money and real latency.

    A 503 rather than a retry when generation or verification fails: a second
    attempt costs another ten seconds and is no more likely to succeed for a
    topic the model cannot specify cleanly, and the candidate has a full
    curated bank sitting one click away.
    """
    problem = await dsa_service.generate_problem(db, topic=body.topic, difficulty=body.difficulty)
    if problem is None:
        raise ApiError(
            status_code=503,
            code="generation_unavailable",
            message=(
                "Couldn't write a fresh problem just now — its answers didn't check out, so it "
                "wasn't used. Try again, or pick one from the list."
            ),
        )
    db.commit()
    # Same shape as GET /problems/{id}: the client opens it exactly as it would
    # any curated problem, and nothing downstream needs to know the difference.
    return success(
        DSAProblemOut(
            id=problem.id,
            title=problem.title,
            topic=problem.topic,
            difficulty=problem.difficulty,
            statement_text=problem.statement_text,
            constraints_text=problem.constraints_text,
            starter_code=problem.starter_code or {},
            function_name=dsa_service.function_name(problem),
            sample_test_cases=dsa_service.sample_cases(problem),
            hidden_test_case_count=len(dsa_service.hidden_cases(problem)),
            solved=False,
        ).model_dump(by_alias=True, mode="json")
    )
