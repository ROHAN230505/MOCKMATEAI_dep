"""
Aggregate analytics for the admin/TnP dashboard (Section 16).

## Aggregate only, and enforced rather than intended

Section 16 says cohort-level views "by default", with individual drill-down "only
if a candidate has explicitly opted in to sharing". No opt-in mechanism exists in
this build -- there is no consent flag on `users` for it and Section 8 defines
none -- so **individual drill-down is not implemented at all**. Building it
without the consent gate would be building the thing Section 12.4 forbids.

Nothing returned here identifies anyone: no ids, no names, no emails, and no free
text a candidate wrote. Only counts and averages.

## Small-cohort suppression

The control Section 16 implies but does not spell out. With four accounts, an
"average readiness score" is not an aggregate -- anyone who knows three of them
can solve for the fourth, and "60% of users score low on STAR structure" is one
person when there are two users.

So every figure is withheld below `MIN_COHORT`, and the response says it is being
withheld and why, rather than returning a number that looks aggregate and is not.

## What is deliberately absent

Section 16 also asks for "sign-language recognition accuracy over time". That
cannot be reported: accuracy needs ground truth, and nothing here knows what a
candidate actually meant to sign. The response says so explicitly instead of
substituting a confidence average, which would look like accuracy while measuring
something else.
"""
from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from app.models.aptitude import AptitudeAttempt, AptitudeAttemptAnswer, AptitudeQuestion
from app.models.dsa import DSAProblem, DSASubmission
from app.models.enums import SubmissionStatus
from app.models.feedback import FeedbackReport
from app.models.interview import InterviewSession
from app.models.resume import ResumeAnalysis
from app.models.user import User

#: Below this many accounts, aggregates are withheld -- see the module docstring.
MIN_COHORT = 5

CATEGORY_LABELS = {
    "content_score": "Content",
    "communication_score": "Communication",
    "confidence_score": "Confidence",
    "body_language_score": "Body language",
}

NOT_MEASURED = [
    {
        "metric": "Sign-language recognition accuracy",
        "reason": (
            "Accuracy needs ground truth, and nothing in this system knows what a candidate meant "
            "to sign. A confidence average would look like accuracy and measure something else."
        ),
    },
    {
        "metric": "Individual candidate drill-down",
        "reason": (
            "Section 16 permits it only for candidates who have explicitly opted into sharing. "
            "No opt-in exists in this build, so it is not implemented."
        ),
    },
]


def _f(value) -> float | None:
    """`func.avg` returns Decimal on Postgres and float on SQLite."""
    return None if value is None else round(float(value), 1)


def build_analytics(db: Session) -> dict:
    total_users = db.execute(select(func.count()).select_from(User)).scalar_one() or 0

    if total_users < MIN_COHORT:
        return {
            "cohort_size": total_users,
            "suppressed": True,
            "suppression_reason": (
                f"Aggregates are withheld below {MIN_COHORT} accounts. With a cohort this small an "
                "average is effectively individual data: anyone who knows the other members can "
                "work back to a single candidate."
            ),
            "engagement": [],
            "category_averages": [],
            "weakest_category_counts": [],
            "aptitude_topic_accuracy": [],
            "dsa_topic_completion": [],
            "not_measured": NOT_MEASURED,
        }

    def distinct_users(model, column) -> int:
        return db.execute(
            select(func.count(func.distinct(column))).select_from(model)
        ).scalar_one() or 0

    engagement = [
        {"module": "Mock interviews", "users": distinct_users(InterviewSession, InterviewSession.user_id)},
        {"module": "Aptitude", "users": distinct_users(AptitudeAttempt, AptitudeAttempt.user_id)},
        {"module": "DSA", "users": distinct_users(DSASubmission, DSASubmission.user_id)},
        {"module": "Resume", "users": distinct_users(ResumeAnalysis, ResumeAnalysis.user_id)},
    ]
    for row in engagement:
        row["percentage"] = round(row["users"] / total_users * 100, 1)

    columns = (
        FeedbackReport.content_score,
        FeedbackReport.communication_score,
        FeedbackReport.confidence_score,
        FeedbackReport.body_language_score,
    )
    averages_row = db.execute(select(*[func.avg(c) for c in columns])).first()
    category_averages = [
        {"category": CATEGORY_LABELS[column.key], "average": _f(value)}
        for column, value in zip(columns, averages_row or [None] * 4)
    ]

    # The curriculum signal Section 16 actually asks for: which category is most
    # often a cohort's weakest. Unmeasured categories are skipped rather than
    # counted as zero, so a batch that never enabled cameras does not read as
    # universally bad at body language.
    weakest_counts: dict[str, int] = {}
    for report in db.execute(select(*columns)).all():
        scored = [(c.key, v) for c, v in zip(columns, report) if v is not None]
        if not scored:
            continue
        weakest = min(scored, key=lambda pair: pair[1])[0]
        weakest_counts[weakest] = weakest_counts.get(weakest, 0) + 1

    total_reports = sum(weakest_counts.values())
    weakest_category_counts = sorted(
        (
            {
                "category": CATEGORY_LABELS[key],
                "count": count,
                "percentage": round(count / total_reports * 100, 1) if total_reports else 0.0,
            }
            for key, count in weakest_counts.items()
        ),
        key=lambda row: row["count"],
        reverse=True,
    )

    aptitude_topic_accuracy = [
        {
            "topic": topic.value,
            "answered": answered,
            "accuracy": round((correct or 0) / answered * 100, 1) if answered else None,
        }
        for topic, answered, correct in db.execute(
            select(
                AptitudeQuestion.topic,
                func.count(),
                func.sum(func.cast(AptitudeAttemptAnswer.is_correct, Integer)),
            )
            .join(AptitudeAttemptAnswer, AptitudeAttemptAnswer.question_id == AptitudeQuestion.id)
            .group_by(AptitudeQuestion.topic)
        ).all()
    ]

    dsa_topic_completion = []
    for topic, problems in db.execute(
        select(DSAProblem.topic, func.count()).group_by(DSAProblem.topic)
    ).all():
        solved = db.execute(
            select(func.count(func.distinct(DSASubmission.problem_id)))
            .join(DSAProblem, DSAProblem.id == DSASubmission.problem_id)
            .where(DSAProblem.topic == topic, DSASubmission.status == SubmissionStatus.PASSED)
        ).scalar_one() or 0
        dsa_topic_completion.append(
            {"topic": topic.value, "problems": problems, "solved_by_anyone": solved}
        )

    return {
        "cohort_size": total_users,
        "suppressed": False,
        "suppression_reason": None,
        "engagement": engagement,
        "category_averages": category_averages,
        "weakest_category_counts": weakest_category_counts,
        "aptitude_topic_accuracy": aptitude_topic_accuracy,
        "dsa_topic_completion": dsa_topic_completion,
        "not_measured": NOT_MEASURED,
    }
