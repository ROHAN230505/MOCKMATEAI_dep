"""
Dashboard summary aggregation (Section 4.5, 7.9, 10.2).

Phase 1 has no interview/aptitude/DSA/resume data yet, so every aggregate
below genuinely queries the (currently empty) tables for this user rather
than returning a hardcoded placeholder — a fresh account honestly sees an
all-zero dashboard, and Phase 4-8 populate the same query paths with real
numbers as those modules are built, with no reshaping needed here.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.aptitude import AptitudeAttempt
from app.models.dsa import DSAProblem, DSASubmission
from app.models.enums import SubmissionStatus
from app.models.feedback import FeedbackReport
from app.models.interview import InterviewSession
from app.models.resume import ResumeAnalysis
from app.models.user import User
from app.schemas.dashboard import DashboardSummary, WeeklyFocusItem
from app.services import recommendations
from app.services.feedback.scoring import load_index_weights, readiness_label


def _as_float(value) -> float | None:
    """
    Normalise an aggregate to a plain float, or None.

    `func.avg()` does not return the same Python type on every dialect: over an
    Integer column Postgres hands back `decimal.Decimal` while SQLite hands back
    `float`. Mixing a Decimal into the weighted arithmetic below raises
    `TypeError: unsupported operand type(s) for *: 'float' and 'decimal.Decimal'`.

    This was latent from Phase 1 until Phase 7 and invisible to the test suite
    twice over: `aptitude_attempts` was empty, so the value was always None and
    the multiplication never ran, and the suite runs on SQLite, which would have
    returned a float even once it did. It surfaced the first time a real attempt
    was scored against real Postgres - the same way the project's other two
    cross-dialect bugs did.
    """
    return None if value is None else float(value)


def get_dashboard_summary(db: Session, user: User) -> DashboardSummary:
    mock_interviews_count = db.execute(
        select(func.count()).select_from(InterviewSession).where(InterviewSession.user_id == user.id)
    ).scalar_one()

    # Both averages go through `_as_float`. The interview one reads a Float
    # column and so happens to be safe today, but relying on that would leave the
    # next person to touch it one column-type change away from the same crash.
    mock_interviews_avg_score = _as_float(
        db.execute(
            select(func.avg(FeedbackReport.overall_readiness_score))
            .join(InterviewSession, InterviewSession.id == FeedbackReport.session_id)
            .where(InterviewSession.user_id == user.id)
        ).scalar_one()
    )

    aptitude_avg_score = _as_float(
        db.execute(
            select(func.avg(AptitudeAttempt.score)).where(AptitudeAttempt.user_id == user.id)
        ).scalar_one()
    )

    dsa_problems_solved = db.execute(
        select(func.count(func.distinct(DSASubmission.problem_id))).where(
            DSASubmission.user_id == user.id, DSASubmission.status == SubmissionStatus.PASSED
        )
    ).scalar_one()
    dsa_problems_total = db.execute(select(func.count()).select_from(DSAProblem)).scalar_one()

    last_resume = db.execute(
        select(ResumeAnalysis)
        .where(ResumeAnalysis.user_id == user.id)
        .order_by(ResumeAnalysis.analyzed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    resume_last_ats_score = last_resume.ats_score if last_resume else None

    dsa_progress_pct = (dsa_problems_solved / dsa_problems_total * 100) if dsa_problems_total else 0.0

    # Section 10.2: weights come from the `scoring_weights` config table so
    # they can be retuned without a redeploy. Missing modules count as zero
    # here — unlike the per-interview formula, a module the candidate hasn't
    # attempted is a genuine readiness gap, not a measurement we can't take.
    weights = load_index_weights(db)
    readiness_index = (
        weights["mock_interview_avg"] * (mock_interviews_avg_score or 0)
        + weights["aptitude_avg"] * (aptitude_avg_score or 0)
        + weights["dsa_progress_pct"] * dsa_progress_pct
        + weights["resume_ats_score"] * (resume_last_ats_score or 0)
    )

    return DashboardSummary(
        readiness_index=round(readiness_index, 1),
        readiness_label=readiness_label(readiness_index),
        mock_interviews_count=mock_interviews_count,
        mock_interviews_avg_score=round(mock_interviews_avg_score, 1) if mock_interviews_avg_score else None,
        aptitude_avg_score=round(aptitude_avg_score, 1) if aptitude_avg_score else None,
        dsa_problems_solved=dsa_problems_solved,
        dsa_problems_total=dsa_problems_total,
        resume_last_ats_score=resume_last_ats_score,
        # Personalized recommendation chips (Section 4.5) need real signal
        # from completed sessions to be honest, non-generic advice (Section
        # 1.2) — nothing to recommend yet for a brand-new account.
        # Section 4.5's "This Week's Focus", ordered by what would actually move
        # the index. Passed the same weights the index itself uses, so advice and
        # score can never drift apart.
        weekly_focus=[
            WeeklyFocusItem(
                id=item.id,
                label=item.label,
                reason=item.reason,
                route=item.route,
                cta=item.cta,
                projected_gain=item.projected_gain,
            )
            for item in recommendations.build_focus(db, user, weights)
        ],
    )
