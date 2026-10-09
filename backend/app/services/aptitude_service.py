"""
Aptitude practice service (Phase 7).

## Where the answers live

`correct_option_index` never leaves the server before submission. Question
selection, scoring and review all happen here; the API's question payload is
built from `AptitudeQuestionOut`, which has no field for the answer. That is the
only reason a practice score means anything.

## Scoring

`score` is stored as a **percentage, 0-100**. Section 8 gives
`aptitude_attempts.score` as an integer along`total_questions`, and
`dashboard_service` averages that column straight into a 0-100 readiness index
(`select(func.avg(AptitudeAttempt.score))`). A raw correct-count would make that
average incoherent across attempts of different lengths - eight right out of ten
and eight right out of thirty would contribute identically. The percentage keeps
the average meaningful, and `total_questions` preserves the denominator so the
raw count is still recoverable.

Unanswered questions score as incorrect, which is not the same rule the interview
feedback uses for skipped questions (Section 9.8 excludes those). The difference
is deliberate: a skipped interview question is a candidate declining to answer a
question an interviewer chose, while an unanswered multiple-choice question in a
timed test is the test measuring exactly what it set out to measure. The answer
row still records blank and wrong distinctly.
"""
import asyncio
import logging
import random
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.content import aptitude_tests
from app.core.responses import ApiError
from app.core.timeutils import utcnow
from app.models.aptitude import AptitudeAttempt, AptitudeAttemptAnswer, AptitudeQuestion
from app.models.enums import AptitudeTopic, Difficulty
from app.models.user import User
from app.schemas.aptitude import StartAttemptRequest, SubmitAttemptRequest
from app.services import aptitude_generator

# A practice attempt cannot be shorter than this and still say anything, and the
# schema bounds the upper end.

logger = logging.getLogger("mockmateai.aptitude")

# How long a candidate may be kept waiting for fresh questions before the
# curated bank takes over. Chosen against measured behaviour rather than taste:
# generation ran 9-17s on the free tier, so this keeps the common case and
# refuses the tail.
GENERATION_DEADLINE_SECONDS = 12.0

MIN_QUESTIONS = 5


def select_questions(
    db: Session,
    *,
    topics: list[AptitudeTopic],
    difficulties: list[Difficulty],
    count: int,
) -> list[AptitudeQuestion]:
    """
    A random sample matching the requested filters.

    Sampled in Python after fetching the filtered ids rather than with a
    database-side `ORDER BY random()`, because the two dialects spell that
    differently (`random()` vs `rand()`) and the test suite runs on SQLite while
    production runs on Postgres. The candidate pool is a few dozen rows, so the
    cost of doing it here is nil.
    """
    statement = select(AptitudeQuestion).where(AptitudeQuestion.is_generated.is_(False))
    if topics:
        statement = statement.where(AptitudeQuestion.topic.in_(topics))
    if difficulties:
        statement = statement.where(AptitudeQuestion.difficulty.in_(difficulties))

    pool = list(db.scalars(statement))
    if len(pool) < MIN_QUESTIONS:
        raise ApiError(
            status_code=409,
            code="not_enough_questions",
            message=(
                "There aren't enough questions matching those filters yet. "
                "Try adding a topic or a difficulty."
            ),
        )

    return random.sample(pool, min(count, len(pool)))


def persist_generated(
    db: Session,
    generated: list[aptitude_generator.GeneratedQuestion],
) -> list[AptitudeQuestion]:
    """
    Write verified generated questions as real rows.

    They have to be rows: an attempt's answers foreign-key to a question id, and
    the review screen reads the text back from the same table. Flagged
    `is_generated` so the curated pool never samples them -- see
    `select_questions` -- which keeps a generated question to the one attempt it
    was written for.
    """
    rows = [
        AptitudeQuestion(
            topic=item.topic,
            difficulty=item.difficulty,
            question_text=item.question_text,
            options=item.options,
            correct_option_index=item.correct_option_index,
            is_generated=True,
        )
        for item in generated
    ]
    for row in rows:
        db.add(row)
    db.flush()
    return rows


async def build_question_set(
    db: Session,
    *,
    topics,
    difficulties,
    count: int,
) -> list[AptitudeQuestion]:
    """
    Fresh questions where possible, curated ones to make up the difference.

    The order matters: generation is attempted first so a working provider
    gives a genuinely different test each time, and the bank tops up whatever
    verification rejected. A candidate therefore always gets a full-length test,
    and every question in it has had its answer key checked -- by execution for
    the curated ones, by independent re-solve for the generated ones.

    Generation failing entirely is not an error. It is the untouched original
    behaviour, and the only visible difference is that the questions are ones
    the candidate may have seen before.
    """
    generated_rows: list[AptitudeQuestion] = []
    try:
        # A hard deadline, and the thing that makes this usable rather than
        # merely clever.
        #
        # Generation plus verification is several provider calls, and on a
        # free tier that measured 9-17 seconds -- long enough that a candidate
        # assumes the page has hung. There is no useful progress to show them
        # either, because the questions cannot be revealed one at a time
        # without revealing which ones failed verification.
        #
        # So the wait is bounded instead. Past the deadline the curated bank
        # serves the whole test immediately, which is exactly the behaviour
        # this feature replaced -- the fallback is not a degraded mode, it is
        # the original product.
        generated = await asyncio.wait_for(
            aptitude_generator.generate_verified(
                topics=list(topics or []),
                difficulties=list(difficulties or []),
                count=count,
            ),
            timeout=GENERATION_DEADLINE_SECONDS,
        )
        if generated:
            generated_rows = persist_generated(db, generated)
    except asyncio.TimeoutError:
        logger.info(
            "Aptitude generation exceeded %ss; serving the curated bank.",
            GENERATION_DEADLINE_SECONDS,
        )
    except Exception:  # noqa: BLE001 - a test must never fail to start over this
        # Deliberately broad. Anything unexpected in the generation path is a
        # reason to serve the curated bank, never a reason to refuse the
        # candidate a test.
        logger.exception("Aptitude generation raised; serving the curated bank instead.")

    shortfall = count - len(generated_rows)
    if shortfall <= 0:
        return generated_rows[:count]

    curated = select_questions(db, topics=topics, difficulties=difficulties, count=shortfall)
    combined = generated_rows + curated
    random.shuffle(combined)
    return combined


async def start_attempt(
    db: Session, user: User, body: StartAttemptRequest
) -> tuple[AptitudeAttempt, list[AptitudeQuestion]]:
    questions = await build_question_set(
        db,
        topics=body.topics,
        difficulties=body.difficulties,
        count=body.question_count,
    )

    attempt = AptitudeAttempt(
        user_id=user.id,
        # Null by design: practice mode. See `StartAttemptRequest`.
        test_id=None,
        started_at=utcnow(),
        total_questions=len(questions),
    )
    db.add(attempt)
    db.flush()

    # The chosen set is persisted immediately, one blank answer row per question.
    # Without this the attempt would have no record of *which* questions it asked,
    # so a submission could name any question at all and a reload would hand the
    # candidate a fresh random set while the attempt stayed open.
    for question in questions:
        db.add(AptitudeAttemptAnswer(attempt_id=attempt.id, question_id=question.id))

    db.commit()
    db.refresh(attempt)
    return attempt, questions


def start_test_attempt(
    db: Session, user: User, test_id: UUID
) -> tuple[AptitudeAttempt, list[AptitudeQuestion], dict]:
    """
    Start a timed mock test (Sections 4.13, 11.1).

    The same attempt row as practice mode, with `test_id` set -- which is exactly
    what Section 8 means by "null = practice mode". The distinction is one column,
    so history, scoring and the dashboard need no branch.

    Returns the test definition alongside, because the client needs its duration
    to run the countdown and its name to label the results.
    """
    test = aptitude_tests.get_test(test_id)
    if test is None:
        raise ApiError(status_code=404, code="test_not_found", message="That test doesn't exist.")

    questions = select_questions(
        db,
        topics=test["topics"],
        difficulties=test["difficulties"],
        count=test["question_count"],
    )

    attempt = AptitudeAttempt(
        user_id=user.id,
        test_id=test_id,
        started_at=utcnow(),
        total_questions=len(questions),
    )
    db.add(attempt)
    db.flush()
    for question in questions:
        db.add(AptitudeAttemptAnswer(attempt_id=attempt.id, question_id=question.id))
    db.commit()
    db.refresh(attempt)
    return attempt, questions, test


def time_remaining_seconds(attempt: AptitudeAttempt) -> int | None:
    """
    Seconds left on a timed attempt, or None for untimed practice.

    Computed from `started_at` on the server rather than trusted from the client.
    A countdown running in a tab is a display; the deadline is a fact about when
    the attempt began, and a candidate who reloads the page or edits a timer in
    devtools gets the same answer.
    """
    if attempt.test_id is None or attempt.started_at is None:
        return None
    test = aptitude_tests.get_test(attempt.test_id)
    if test is None:
        return None
    elapsed = (utcnow() - attempt.started_at).total_seconds()
    return max(0, int(test["duration_minutes"] * 60 - elapsed))


def get_attempt_for_user(db: Session, user: User, attempt_id: UUID) -> AptitudeAttempt:
    attempt = db.scalars(
        select(AptitudeAttempt)
        .options(selectinload(AptitudeAttempt.answers))
        .where(AptitudeAttempt.id == attempt_id)
    ).first()
    # 404 rather than 403 on a mismatched owner, matching Section 12.2's handling
    # everywhere else: never confirm to a non-owner that the resource exists.
    if attempt is None or attempt.user_id != user.id:
        raise ApiError(status_code=404, code="attempt_not_found", message="Aptitude attempt not found.")
    return attempt


def submit_attempt(
    db: Session, user: User, attempt_id: UUID, body: SubmitAttemptRequest
) -> AptitudeAttempt:
    """
    Grade a submitted attempt and persist the outcome.

    Only answers naming a question the attempt actually asked are recorded; a
    submission mentioning anything else is ignored rather than rejected, so a
    stale tab cannot fail a candidate's whole submission over one bad id.
    """
    attempt = get_attempt_for_user(db, user, attempt_id)

    if attempt.submitted_at is not None:
        raise ApiError(
            status_code=409,
            code="attempt_already_submitted",
            message="This attempt has already been submitted.",
        )

    rows = {row.question_id: row for row in attempt.answers}
    questions = {
        question.id: question
        for question in db.scalars(
            select(AptitudeQuestion).where(AptitudeQuestion.id.in_(rows.keys()))
        )
    }

    for submitted in body.answers:
        row = rows.get(submitted.question_id)
        question = questions.get(submitted.question_id)
        if row is None or question is None:
            continue

        selected = submitted.selected_option_index
        # An index past the end of the option list is treated as no answer, not
        # as a wrong one: it means the client and the stored question disagree
        # about the options, and guessing which was meant would be worse.
        if selected is not None and not (0 <= selected < len(question.options)):
            selected = None

        row.selected_option_index = selected
        row.is_correct = selected is not None and selected == question.correct_option_index
        row.time_spent_seconds = submitted.time_spent_seconds

    # Anything never submitted stays blank and counts as incorrect.
    for row in rows.values():
        if row.is_correct is None:
            row.is_correct = False

    correct = sum(1 for row in rows.values() if row.is_correct)
    total = len(rows) or 1
    attempt.score = round(correct / total * 100)
    attempt.total_questions = len(rows)
    attempt.submitted_at = utcnow()

    db.commit()
    db.refresh(attempt)
    return attempt


def build_result(db: Session, attempt: AptitudeAttempt) -> dict:
    """
    The reviewable result: per-question outcome plus a per-topic breakdown.

    This is the first and only point at which `correct_option_index` is exposed,
    and it is reachable only for a submitted attempt belonging to the caller.
    """
    if attempt.submitted_at is None:
        raise ApiError(
            status_code=409,
            code="attempt_not_submitted",
            message="This attempt hasn't been submitted yet, so there is no result to show.",
        )

    rows = sorted(attempt.answers, key=lambda row: str(row.question_id))
    questions = {
        question.id: question
        for question in db.scalars(
            select(AptitudeQuestion).where(
                AptitudeQuestion.id.in_([row.question_id for row in rows])
            )
        )
    }

    answers = []
    per_topic: dict[AptitudeTopic, list[bool]] = {}
    for row in rows:
        question = questions.get(row.question_id)
        if question is None:
            # The question was deleted after the attempt. The recorded outcome
            # still stands, but there is nothing to review against, so it is
            # omitted from the review rather than rendered with empty fields.
            continue
        answers.append(
            {
                "question_id": question.id,
                "question_text": question.question_text,
                "topic": question.topic,
                "difficulty": question.difficulty,
                "options": list(question.options),
                "selected_option_index": row.selected_option_index,
                "correct_option_index": question.correct_option_index,
                "is_correct": bool(row.is_correct),
                "time_spent_seconds": row.time_spent_seconds,
            }
        )
        per_topic.setdefault(question.topic, []).append(bool(row.is_correct))

    breakdown = []
    for topic in AptitudeTopic:
        outcomes = per_topic.get(topic)
        if not outcomes:
            # Reported as absent rather than as 0%, which would read as having
            # got every question in the topic wrong.
            breakdown.append({"topic": topic, "correct": 0, "total": 0, "percentage": None})
            continue
        correct = sum(1 for outcome in outcomes if outcome)
        breakdown.append(
            {
                "topic": topic,
                "correct": correct,
                "total": len(outcomes),
                "percentage": round(correct / len(outcomes) * 100, 1),
            }
        )

    # Timed-test facts, derived rather than stored. `submitted_late` is a
    # statement about two timestamps, not a flag anyone had to remember to set.
    test = aptitude_tests.get_test(attempt.test_id) if attempt.test_id else None
    time_taken = None
    submitted_late = False
    if attempt.started_at and attempt.submitted_at:
        time_taken = int((attempt.submitted_at - attempt.started_at).total_seconds())
        if test is not None:
            submitted_late = time_taken > test["duration_minutes"] * 60

    return {
        "attempt_id": attempt.id,
        "test_name": test["name"] if test else None,
        "duration_minutes": test["duration_minutes"] if test else None,
        "time_taken_seconds": time_taken,
        "submitted_late": submitted_late,
        "score": attempt.score or 0,
        "correct_count": sum(1 for answer in answers if answer["is_correct"]),
        "total_questions": attempt.total_questions or len(rows),
        "topic_breakdown": breakdown,
        "answers": answers,
    }


def list_attempts(db: Session, user: User, *, limit: int = 20) -> list[AptitudeAttempt]:
    return list(
        db.scalars(
            select(AptitudeAttempt)
            .where(AptitudeAttempt.user_id == user.id, AptitudeAttempt.submitted_at.is_not(None))
            .order_by(AptitudeAttempt.submitted_at.desc())
            .limit(limit)
        )
    )


def catalog_counts(db: Session) -> dict:
    """
    How many questions exist, broken down three ways.

    Per topic *and* per topic-and-difficulty pair, because per-topic counts alone
    cannot answer the question the setup screen actually has. There are eight
    verbal questions but only three easy ones, so "verbal + easy" cannot fill a
    five-question test — and with only topic counts the UI would offer that
    combination and the candidate would meet a 409 after pressing start.

    Keys in `combinations` are "topic:difficulty" so the payload stays a flat map
    that JSON and the client can both index without a nested lookup.
    """
    per_topic: dict[str, int] = {}
    per_difficulty: dict[str, int] = {}
    combinations: dict[str, int] = {}

    for topic, difficulty, count in db.execute(
        select(AptitudeQuestion.topic, AptitudeQuestion.difficulty, func.count()).group_by(
            AptitudeQuestion.topic, AptitudeQuestion.difficulty
        )
    ):
        per_topic[topic.value] = per_topic.get(topic.value, 0) + count
        per_difficulty[difficulty.value] = per_difficulty.get(difficulty.value, 0) + count
        combinations[f"{topic.value}:{difficulty.value}"] = count

    return {
        "topicCounts": per_topic,
        "difficultyCounts": per_difficulty,
        "combinationCounts": combinations,
        # So the client can apply the same rule the service applies rather than
        # hardcoding a copy of it that could drift.
        "minQuestions": MIN_QUESTIONS,
    }
