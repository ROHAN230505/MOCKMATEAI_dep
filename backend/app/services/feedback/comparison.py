"""
Before & After comparison (Section 4.11A).

Shows the candidate what changed since their last attempt, which is the whole
reason to practise more than once. Three rules keep it honest:

1. **Only compare like with like.** A delta between a Backend Engineer
   interview and a Product Manager interview says nothing about improvement. The
   most recent earlier session for the *same role* is preferred, and when only a
   different role is available the comparison is still returned but flagged
   `same_role = false` so the UI can say so instead of implying progress.

2. **A missing score is not a zero.** If confidence wasn't measured in either
   session, its delta is None — not 0, which would read as "no change" in a
   category that was never observed. Same when only one side has it: there is no
   defensible delta between a number and nothing.

3. **Small movements are noise.** Two sessions with different questions will
   differ by a few points regardless of the candidate. Anything inside
   `NOISE_BAND` is reported as "about the same" rather than dressed up as
   progress, because telling someone they improved when they didn't is exactly
   the flattery Section 1.2 rules out.
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import FeedbackGenerationStatus
from app.models.feedback import FeedbackReport
from app.models.interview import InterviewSession

# Points on the 0-100 scale within which two sessions are treated as equal.
NOISE_BAND = 3.0

# (report column, wire identifier). The identifiers match
# `categoryScores[].category` in the report payload — plus "overall" — so the
# frontend can line a delta up with the score it belongs to without a lookup
# table of its own.
CATEGORY_FIELDS = (
    ("overall_readiness_score", "overall"),
    ("content_score", "content"),
    ("communication_score", "communication"),
    ("confidence_score", "confidence"),
    ("body_language_score", "body_language"),
)


@dataclass
class CategoryDelta:
    category: str
    previous: float | None
    current: float | None
    delta: float | None
    direction: str  # "improved" | "declined" | "unchanged" | "not_comparable"


@dataclass
class Comparison:
    previous_session_id: str
    previous_role_target: str
    previous_completed_at: str | None
    same_role: bool
    deltas: list[CategoryDelta]
    headline: str


def find_previous_report(
    db: Session, user_id, current_session: InterviewSession
) -> tuple[InterviewSession, FeedbackReport] | None:
    """
    The attempt to compare against: the user's most recent earlier session that
    has a finished report.

    Ordered by `started_at` rather than `created_at` so a session that was
    created and abandoned days before it was actually taken doesn't jump the
    queue. Sessions without a READY report are skipped — a half-generated report
    has no scores to compare.
    """

    def _query(same_role: bool):
        statement = (
            select(InterviewSession, FeedbackReport)
            .join(FeedbackReport, FeedbackReport.session_id == InterviewSession.id)
            .where(
                InterviewSession.user_id == user_id,
                InterviewSession.id != current_session.id,
                FeedbackReport.generation_status == FeedbackGenerationStatus.READY,
            )
            .order_by(InterviewSession.started_at.desc().nullslast(), InterviewSession.created_at.desc())
            .limit(1)
        )
        if same_role:
            statement = statement.where(InterviewSession.role_target == current_session.role_target)
        # Only sessions that actually happened before this one.
        reference = current_session.started_at or current_session.created_at
        if reference is not None:
            statement = statement.where(InterviewSession.created_at < reference)
        return db.execute(statement).first()

    return _query(same_role=True) or _query(same_role=False)


def _direction(previous: float | None, current: float | None) -> tuple[float | None, str]:
    if previous is None or current is None:
        return None, "not_comparable"
    delta = round(current - previous, 1)
    if abs(delta) <= NOISE_BAND:
        return delta, "unchanged"
    return delta, "improved" if delta > 0 else "declined"


def _headline(deltas: list[CategoryDelta], same_role: bool) -> str:
    overall = next((d for d in deltas if d.category == "overall"), None)

    if overall is None or overall.direction == "not_comparable":
        base = (
            "There isn't a comparable overall score between these two sessions, so treat the "
            "category numbers below individually rather than as a trend."
        )
    elif overall.direction == "improved":
        base = (
            f"Your overall readiness is up {abs(overall.delta):.0f} points since your last attempt "
            f"({overall.previous:.0f} to {overall.current:.0f})."
        )
    elif overall.direction == "declined":
        base = (
            f"Your overall readiness is down {abs(overall.delta):.0f} points since your last attempt "
            f"({overall.previous:.0f} to {overall.current:.0f}). One session is a small sample — "
            "different questions land differently — so look at which category moved before reading too "
            "much into it."
        )
    else:
        base = (
            f"Your overall readiness held steady at about {overall.current:.0f}. That's a real result, "
            "not a stall: consistency across different question sets is what interview readiness "
            "actually looks like."
        )

    if not same_role:
        base += (
            " Note that your previous session targeted a different role, so this is a rough comparison "
            "rather than a like-for-like one."
        )
    return base


def build_comparison(
    current_report: FeedbackReport,
    previous_session: InterviewSession,
    previous_report: FeedbackReport,
    current_session: InterviewSession,
) -> Comparison:
    deltas: list[CategoryDelta] = []
    for field, category in CATEGORY_FIELDS:
        previous = getattr(previous_report, field)
        current = getattr(current_report, field)
        delta, direction = _direction(previous, current)
        deltas.append(
            CategoryDelta(
                category=category,
                previous=previous,
                current=current,
                delta=delta,
                direction=direction,
            )
        )

    same_role = previous_session.role_target == current_session.role_target
    return Comparison(
        previous_session_id=str(previous_session.id),
        previous_role_target=previous_session.role_target,
        previous_completed_at=(
            previous_session.ended_at.isoformat() if previous_session.ended_at else None
        ),
        same_role=same_role,
        deltas=deltas,
        headline=_headline(deltas, same_role),
    )


def get_comparison(db: Session, user_id, current_session: InterviewSession, current_report: FeedbackReport) -> Comparison | None:
    """None when this is the user's first completed interview — there is nothing to compare against yet."""
    previous = find_previous_report(db, user_id, current_session)
    if previous is None:
        return None
    previous_session, previous_report = previous
    return build_comparison(current_report, previous_session, previous_report, current_session)
