"""
DSA practice service (Phase 7).

## Grading happens in the browser

The chosen design is in-browser execution via Pyodide: no server-side code
execution, so an untrusted submission never runs on our infrastructure. That
removes the entire sandboxing surface a server-side runner would need, and it
matches how every other candidate-media pipeline in this product already works.

It costs one thing, and it is stated rather than hidden: the hidden test cases
must reach the client to be run against, so a candidate who opens devtools can
read them. `schemas/dsa.py` records that trade and the UI says it out loud.

## What the server still decides

The client reports how many cases passed; the server decides the `status`. That
distinction matters — `passed`/`partial`/`failed` is derived here from the counts
against the problem's real case total, so a client cannot post
`status = passed` directly. It is not a security boundary (a client that runs its
own grading can lie about the counts too) and it is not presented as one; it is
simply the one place the enum is assigned, so the rule is in a single place and
the dashboard's "problems solved" count means one consistent thing.
"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.responses import ApiError
from app.models.dsa import DSAProblem, DSASubmission
from app.models.enums import Difficulty, DSATopic, SubmissionStatus
from app.models.user import User
from app.schemas.dsa import SubmitSolutionRequest
from app.services import dsa_generator

logger = logging.getLogger("mockmateai.dsa")


def list_problems(db: Session, user: User) -> list[dict]:
    """
    Every curated problem, with this candidate's progress folded in.

    Generated problems are excluded. They are written on demand for one
    candidate and reached directly from the response that created them, so
    listing them would pile every user's generated problems into everyone
    else's browse list and grow without bound.
    """
    problems = list(
        db.scalars(
            select(DSAProblem)
            .where(DSAProblem.is_generated.is_(False))
            .order_by(DSAProblem.title)
        )
    )

    submissions = list(
        db.scalars(select(DSASubmission).where(DSASubmission.user_id == user.id))
    )
    solved = {s.problem_id for s in submissions if s.status == SubmissionStatus.PASSED}
    attempted = {s.problem_id for s in submissions}

    return [
        {
            "id": problem.id,
            "title": problem.title,
            "topic": problem.topic,
            "difficulty": problem.difficulty,
            "solved": problem.id in solved,
            "attempted": problem.id in attempted,
        }
        for problem in problems
    ]


def get_problem(db: Session, problem_id: UUID) -> DSAProblem:
    problem = db.scalars(select(DSAProblem).where(DSAProblem.id == problem_id)).first()
    if problem is None:
        raise ApiError(status_code=404, code="problem_not_found", message="Problem not found.")
    return problem


def function_name(problem: DSAProblem) -> str:
    """
    The entry point the runner calls.

    Stored inside `starter_code` alongside the per-language templates rather than
    parsed back out of the source, so the runner never has to guess which `def`
    in a candidate's file is the one under test.
    """
    starter = problem.starter_code or {}
    name = starter.get("functionName")
    if not name:
        raise ApiError(
            status_code=500,
            code="problem_misconfigured",
            message="This problem is missing its entry point and cannot be run.",
        )
    return name


def sample_cases(problem: DSAProblem) -> list[dict]:
    return list((problem.test_cases or {}).get("sample", []))


def hidden_cases(problem: DSAProblem) -> list[dict]:
    return list((problem.test_cases or {}).get("hidden", []))


def is_solved(db: Session, user: User, problem_id: UUID) -> bool:
    return db.scalars(
        select(DSASubmission.id).where(
            DSASubmission.user_id == user.id,
            DSASubmission.problem_id == problem_id,
            DSASubmission.status == SubmissionStatus.PASSED,
        )
    ).first() is not None


def _derive_status(passed: int, total: int) -> SubmissionStatus:
    """
    The one place the enum is assigned.

    `total` is the problem's real case count, not the client's claim about it, so
    a submission reporting "3 of 3 passed" against a problem with nine cases is
    partial rather than passed.
    """
    if total <= 0:
        return SubmissionStatus.FAILED
    if passed >= total:
        return SubmissionStatus.PASSED
    if passed <= 0:
        return SubmissionStatus.FAILED
    return SubmissionStatus.PARTIAL


def record_submission(
    db: Session, user: User, problem: DSAProblem, body: SubmitSolutionRequest
) -> DSASubmission:
    expected_total = len(sample_cases(problem)) + len(hidden_cases(problem))
    passed = min(body.passed_case_count, expected_total)

    if body.total_case_count != expected_total:
        # Not rejected: the client may be running a cached copy of the problem
        # after the bank was extended. Logged and graded against the real total,
        # which can only ever move the outcome toward `partial`.
        logger.info(
            "Submission case count disagrees with the stored problem "
            "[problem_id=%s client_total=%s stored_total=%s]",
            problem.id,
            body.total_case_count,
            expected_total,
        )

    submission = DSASubmission(
        user_id=user.id,
        problem_id=problem.id,
        code=body.code,
        language=body.language,
        status=_derive_status(passed, expected_total),
        runtime_ms=body.runtime_ms,
        hints_used_count=body.hints_used_count,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


def list_submissions(db: Session, user: User, problem_id: UUID, *, limit: int = 20) -> list[DSASubmission]:
    return list(
        db.scalars(
            select(DSASubmission)
            .where(DSASubmission.user_id == user.id, DSASubmission.problem_id == problem_id)
            .order_by(DSASubmission.submitted_at.desc())
            .limit(limit)
        )
    )


async def generate_problem(
    db: Session,
    *,
    topic: DSATopic,
    difficulty: Difficulty,
) -> DSAProblem | None:
    """
    Create and persist one freshly generated problem, or None.

    None means the generator did not produce something that passed
    verification, and the caller should say so plainly rather than retrying
    silently -- a second attempt costs another ten seconds and is no more
    likely to succeed for a topic the model struggles to specify cleanly.

    Persisted like any other problem so submissions can reference it, but
    flagged `is_generated`, which keeps it out of the curated listing.
    """
    generated = await dsa_generator.generate_verified(topic=topic, difficulty=difficulty)
    if generated is None:
        return None

    problem = DSAProblem(
        title=generated.title,
        topic=generated.topic,
        difficulty=generated.difficulty,
        statement_text=generated.statement_text,
        constraints_text=generated.constraints_text or None,
        # `functionName` alongside the template, because that is where
        # `function_name()` looks -- there is no column for it. Omitting it
        # produced a problem that generated and verified cleanly and then 500'd
        # the moment anyone opened it.
        starter_code={
            "python": generated.starter_code,
            "functionName": generated.function_name,
        },
        test_cases={"sample": generated.sample, "hidden": generated.hidden},
        is_generated=True,
    )
    db.add(problem)
    db.flush()
    logger.info("Generated DSA problem persisted [title=%s topic=%s]", problem.title, topic.value)
    return problem
