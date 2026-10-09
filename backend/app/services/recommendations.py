"""
"This Week's Focus" recommendations (Section 4.5, feature 38).

## How items are chosen, and why that ordering

Every recommendation is ranked by **how much acting on it would actually move the
candidate's Readiness Index** — the gap to 100 in that module multiplied by the
module's weight in Section 10.2's index formula. Not by which weakness is most
dramatic, and not by a fixed editorial order.

That matters because the two differ. A candidate scoring 40 on aptitude
(weight 0.20) has a 12-point index gap; the same candidate never having analysed
a resume (weight 0.10) is a 10-point gap. Ranked by raw score, the resume looks
fine and the aptitude looks urgent. Ranked by index impact, they are nearly
equally worth doing — and telling the candidate which will actually help most is
the difference between advice and noise.

## Nothing is recommended that was not measured

Each item carries the evidence that produced it, and the module states the
projected gain rather than asserting a benefit. A module the candidate has never
touched is reported as exactly that — a real, grounded fact — rather than dressed
up as a diagnosed weakness. If nothing at all has been measured, the list is
empty and the dashboard shows no panel, which is the honest state for a brand new
account rather than three lines of generic interview advice.
"""
from dataclasses import dataclass

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from app.models.aptitude import AptitudeAttempt, AptitudeAttemptAnswer, AptitudeQuestion
from app.models.dsa import DSAProblem, DSASubmission
from app.models.enums import SubmissionStatus
from app.models.feedback import FeedbackReport
from app.models.interview import InterviewSession
from app.models.resume import ResumeAnalysis
from app.models.user import User

# At most three, per Section 4.5's "2-3 personalized recommendation chips".
MAX_ITEMS = 3
# Below this a module is worth recommending; above it, the candidate is doing
# fine there and saying otherwise would be manufacturing a problem.
GOOD_ENOUGH = 80.0
# A projected index gain smaller than this is not worth a candidate's week.
MIN_WORTHWHILE_GAIN = 2.0

TOPIC_LABELS = {
    "quantitative": "quantitative aptitude",
    "logical_reasoning": "logical reasoning",
    "verbal_ability": "verbal ability",
    "data_interpretation": "data interpretation",
}

CATEGORY_LABELS = {
    "content_score": "the substance of your answers",
    "communication_score": "how clearly you structure answers",
    "confidence_score": "vocal delivery",
    "body_language_score": "body language",
}


@dataclass
class FocusItem:
    id: str
    label: str
    #: The measurement this came from. Shown to the candidate, not just logged.
    reason: str
    #: Where the Start button goes (Section 4.5).
    route: str
    cta: str
    #: Points this could add to the Readiness Index. Used for ordering, and shown.
    projected_gain: float


def _as_float(value) -> float | None:
    """`func.avg` returns Decimal on Postgres and float on SQLite. See dashboard_service."""
    return None if value is None else float(value)


def _weakest_interview_category(db: Session, user: User) -> tuple[str, float] | None:
    """
    The lowest-scoring category across this candidate's reports.

    Averaged over their reports rather than taken from the latest one, so a
    single bad session does not redirect a whole week. Categories that were never
    measured average to NULL and are skipped — a candidate whose camera was off
    is not told their body language is their weakest area.
    """
    columns = (
        FeedbackReport.content_score,
        FeedbackReport.communication_score,
        FeedbackReport.confidence_score,
        FeedbackReport.body_language_score,
    )
    row = db.execute(
        select(*[func.avg(column) for column in columns])
        .join(InterviewSession, InterviewSession.id == FeedbackReport.session_id)
        .where(InterviewSession.user_id == user.id)
    ).first()
    if row is None:
        return None

    scored = [
        (column.key, _as_float(value))
        for column, value in zip(columns, row)
        if _as_float(value) is not None
    ]
    if not scored:
        return None
    return min(scored, key=lambda pair: pair[1])


def _weakest_aptitude_topic(db: Session, user: User) -> tuple[str, float] | None:
    """Per-topic accuracy, from the answers themselves rather than the attempt score."""
    rows = db.execute(
        select(
            AptitudeQuestion.topic,
            func.count(),
            # Cast because SQLite stores booleans as integers and Postgres does not
            # sum them directly.
            func.sum(func.cast(AptitudeAttemptAnswer.is_correct, Integer)),
        )
        .join(AptitudeAttemptAnswer, AptitudeAttemptAnswer.question_id == AptitudeQuestion.id)
        .join(AptitudeAttempt, AptitudeAttempt.id == AptitudeAttemptAnswer.attempt_id)
        .where(AptitudeAttempt.user_id == user.id, AptitudeAttempt.submitted_at.is_not(None))
        .group_by(AptitudeQuestion.topic)
    ).all()

    # Fewer than four answered questions in a topic is not a measurement of that
    # topic, it is a coincidence.
    scored = [
        (topic.value, (correct or 0) / total * 100)
        for topic, total, correct in rows
        if total >= 4
    ]
    if not scored:
        return None
    return min(scored, key=lambda pair: pair[1])


def build_focus(db: Session, user: User, weights: dict[str, float]) -> list[FocusItem]:
    """
    Two or three things worth doing this week, ordered by index impact.

    `weights` is Section 10.2's index formula, read from the config table by the
    caller so the ordering follows the same numbers the score itself uses — if the
    weights are retuned, the recommendations reprioritise with them rather than
    drifting out of agreement with the index they are meant to raise.
    """
    candidates: list[FocusItem] = []

    def gain(current: float, weight_key: str) -> float:
        return round(max(0.0, 100.0 - current) * weights.get(weight_key, 0.0), 1)

    # --- Mock interviews (0.45 of the index) --------------------------------
    interview_avg = _as_float(
        db.execute(
            select(func.avg(FeedbackReport.overall_readiness_score))
            .join(InterviewSession, InterviewSession.id == FeedbackReport.session_id)
            .where(InterviewSession.user_id == user.id)
        ).scalar_one()
    )

    if interview_avg is None:
        candidates.append(
            FocusItem(
                id="first-interview",
                label="Take your first mock interview",
                reason="Interviews carry the largest share of your Readiness Index, and you haven't done one yet.",
                route="/interview/setup",
                cta="Start",
                projected_gain=gain(0.0, "mock_interview_avg"),
            )
        )
    elif interview_avg < GOOD_ENOUGH:
        weakest = _weakest_interview_category(db, user)
        if weakest is not None:
            column, score = weakest
            candidates.append(
                FocusItem(
                    id=f"interview-{column}",
                    label=f"Work on {CATEGORY_LABELS.get(column, column)}",
                    reason=f"It's your lowest interview category, averaging {score:.0f} out of 100.",
                    route="/interview/setup",
                    cta="Practise",
                    projected_gain=gain(interview_avg, "mock_interview_avg"),
                )
            )

    # --- Aptitude (0.20) -----------------------------------------------------
    aptitude_avg = _as_float(
        db.execute(
            select(func.avg(AptitudeAttempt.score)).where(AptitudeAttempt.user_id == user.id)
        ).scalar_one()
    )

    if aptitude_avg is None:
        candidates.append(
            FocusItem(
                id="first-aptitude",
                label="Try an aptitude test",
                reason="You haven't attempted one, so this part of your index is still empty.",
                route="/aptitude",
                cta="Start",
                projected_gain=gain(0.0, "aptitude_avg"),
            )
        )
    else:
        topic = _weakest_aptitude_topic(db, user)
        if topic is not None and topic[1] < GOOD_ENOUGH:
            name, accuracy = topic
            candidates.append(
                FocusItem(
                    id=f"aptitude-{name}",
                    label=f"Practise {TOPIC_LABELS.get(name, name)}",
                    reason=f"You're getting {accuracy:.0f}% right in this topic — your weakest.",
                    route="/aptitude",
                    cta="Practise",
                    projected_gain=gain(aptitude_avg, "aptitude_avg"),
                )
            )
        elif aptitude_avg < GOOD_ENOUGH:
            candidates.append(
                FocusItem(
                    id="aptitude-general",
                    label="Keep practising aptitude",
                    reason=f"Your attempts average {aptitude_avg:.0f}%.",
                    route="/aptitude",
                    cta="Practise",
                    projected_gain=gain(aptitude_avg, "aptitude_avg"),
                )
            )

    # --- DSA (0.25) ----------------------------------------------------------
    solved = db.execute(
        select(func.count(func.distinct(DSASubmission.problem_id))).where(
            DSASubmission.user_id == user.id, DSASubmission.status == SubmissionStatus.PASSED
        )
    ).scalar_one()
    total_problems = db.execute(select(func.count()).select_from(DSAProblem)).scalar_one()
    dsa_pct = (solved / total_problems * 100) if total_problems else 0.0

    if total_problems > 0 and dsa_pct < GOOD_ENOUGH:
        remaining = total_problems - solved
        candidates.append(
            FocusItem(
                id="dsa-progress",
                label="Solve one more DSA problem" if remaining == 1 else "Work through more DSA problems",
                reason=(
                    "You haven't solved any yet."
                    if solved == 0
                    else f"You've solved {solved} of {total_problems}."
                ),
                route="/dsa",
                cta="Continue",
                projected_gain=gain(dsa_pct, "dsa_progress_pct"),
            )
        )

    # --- Resume (0.10) -------------------------------------------------------
    latest_resume = db.execute(
        select(ResumeAnalysis)
        .where(ResumeAnalysis.user_id == user.id)
        .order_by(ResumeAnalysis.analyzed_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if latest_resume is None:
        candidates.append(
            FocusItem(
                id="first-resume",
                label="Analyse your resume",
                reason="It takes a minute and it's the last empty part of your index.",
                route="/resume",
                cta="Start",
                projected_gain=gain(0.0, "resume_ats_score"),
            )
        )
    elif latest_resume.ats_score is not None and latest_resume.ats_score < GOOD_ENOUGH:
        candidates.append(
            FocusItem(
                id="resume-score",
                label="Tighten up your resume",
                reason=f"Your last analysis scored {latest_resume.ats_score} for ATS readiness.",
                route="/resume",
                cta="Re-analyse",
                projected_gain=gain(float(latest_resume.ats_score), "resume_ats_score"),
            )
        )

    # Ranked by what would actually move the index, and trimmed of anything too
    # small to be worth a candidate's week.
    worthwhile = [item for item in candidates if item.projected_gain >= MIN_WORTHWHILE_GAIN]
    worthwhile.sort(key=lambda item: item.projected_gain, reverse=True)
    return worthwhile[:MAX_ITEMS]
