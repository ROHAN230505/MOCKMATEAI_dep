"""
Feedback report endpoints (Section 7.4, Section 4.11).

Ownership is checked on every route through
`interview_service.get_session_for_user`, which is Section 12.2's object-level
authorization: a session ID in the URL is not permission to read it. That's the
whole security surface here — a feedback report is the most personal artifact in
the product, containing a verbatim transcript of someone's interview.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.rate_limit import STANDARD_RATE_LIMIT, limiter
from app.core.responses import ApiError, success
from app.database import get_db
from app.models.enums import FeedbackCategory, FeedbackGenerationStatus, FeedbackItemType
from app.models.feedback import FeedbackReport
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.feedback import (
    CategoryDeltaOut,
    CategoryScoreOut,
    ComparisonOut,
    FeedbackItemOut,
    FeedbackReportOut,
    FeedbackStatusOut,
    TranscriptSignalsOut,
    TranscriptTurnOut,
)
from app.services import ai_quota, interview_service
from app.services.feedback import comparison as comparison_service
from app.services.feedback import exports, generator
from app.services.feedback.prompts import CATEGORY_LABELS
from app.services.feedback.scoring import compute_breakdown, load_turns, readiness_label

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _require_report(db: Session, user: User, session_id: UUID):
    """
    Resolve (session, report), 404-ing when generation has never been started.

    A distinct 404 code from "session not found" matters to the client: one means
    "you're looking at the wrong session", the other means "ask for the report to
    be generated".
    """
    session = interview_service.get_session_for_user(db, user, session_id)
    report = generator.get_report(db, session.id)
    if report is None:
        raise ApiError(
            status_code=404,
            code="feedback_not_generated",
            message="No feedback report exists for this interview yet.",
        )
    return session, report


def _category_scores(report: FeedbackReport, measured: list[str], weights: dict[str, float]) -> list[CategoryScoreOut]:
    values = {
        FeedbackCategory.CONTENT: report.content_score,
        FeedbackCategory.COMMUNICATION: report.communication_score,
        FeedbackCategory.CONFIDENCE: report.confidence_score,
        FeedbackCategory.BODY_LANGUAGE: report.body_language_score,
    }
    return [
        CategoryScoreOut(
            category=category,
            score=score,
            weight=weights.get(category.value),
            measured=category.value in measured,
            label=CATEGORY_LABELS[category],
        )
        for category, score in values.items()
    ]


def _build_report_out(db: Session, user: User, session, report: FeedbackReport) -> FeedbackReportOut:
    turns = load_turns(db, session.id)

    # Recomputing the breakdown here is deliberate and cheap: it supplies the
    # measured/unmeasured split, the effective weights and the transcript
    # signals for display. The persisted scores in `report` remain the source of
    # truth for the numbers themselves — they are what the narrative was written
    # against, so showing a freshly recomputed score next to that narrative
    # could contradict it if the weights were retuned in between.
    breakdown = compute_breakdown(db, session.id, turns)

    strengths = [
        FeedbackItemOut(
            category=detail.category,
            type=detail.type,
            text=detail.text,
            evidence_reference=detail.evidence_reference,
        )
        for detail in report.details
        if detail.type == FeedbackItemType.STRENGTH
    ]
    improvements = [
        FeedbackItemOut(
            category=detail.category,
            type=detail.type,
            text=detail.text,
            evidence_reference=detail.evidence_reference,
        )
        for detail in report.details
        if detail.type == FeedbackItemType.IMPROVEMENT
    ]

    signals = breakdown.signals
    signals_out = (
        TranscriptSignalsOut(
            answer_count=signals.answer_count,
            total_words=signals.total_words,
            filler_count=signals.filler_count,
            filler_rate_per_100_words=round(signals.filler_rate_per_100_words, 1),
            average_answer_words=round(signals.average_answer_words, 1),
            quantified_answers=signals.quantified_answers,
            under_elaborated_answers=signals.under_elaborated_answers,
            well_developed_answers=signals.well_developed_answers,
            speaking_pace_wpm=(
                round(signals.speaking_pace_wpm, 1) if signals.speaking_pace_wpm is not None else None
            ),
        )
        if signals is not None and signals.answer_count > 0
        else None
    )

    comparison_out = None
    if report.generation_status == FeedbackGenerationStatus.READY:
        found = comparison_service.get_comparison(db, user.id, session, report)
        if found is not None:
            comparison_out = ComparisonOut(
                previous_session_id=UUID(found.previous_session_id),
                previous_role_target=found.previous_role_target,
                previous_completed_at=found.previous_completed_at,
                same_role=found.same_role,
                headline=found.headline,
                deltas=[
                    CategoryDeltaOut(
                        category=delta.category,
                        previous=delta.previous,
                        current=delta.current,
                        delta=delta.delta,
                        direction=delta.direction,
                    )
                    for delta in found.deltas
                ],
            )

    return FeedbackReportOut(
        session_id=session.id,
        status=report.generation_status,
        generated_at=report.generated_at,
        generated_by=report.generated_by,
        role_target=session.role_target,
        interview_type=session.interview_type.value,
        duration_minutes=session.duration_minutes,
        mode=session.mode.value,
        started_at=session.started_at,
        ended_at=session.ended_at,
        target_company_name=session.target_company_name,
        overall_readiness_score=report.overall_readiness_score,
        readiness_label=readiness_label(report.overall_readiness_score),
        category_scores=_category_scores(report, breakdown.measured_categories, breakdown.effective_weights),
        measured_categories=breakdown.measured_categories,
        unmeasured_categories=breakdown.unmeasured_categories,
        summary_text=report.summary_text,
        strengths=strengths,
        improvements=improvements,
        answered_count=breakdown.answered_count,
        skipped_count=breakdown.skipped_count,
        question_count=len(turns),
        turns=[
            TranscriptTurnOut(
                number=index + 1,
                question_id=UUID(turn.question_id),
                question_text=turn.question_text,
                is_followup=turn.is_followup,
                answer_text=turn.transcript_text,
                is_skipped=turn.is_skipped,
                relevance_score=turn.relevance_score,
                completeness_score=turn.completeness_score,
                asr_confidence_avg=turn.asr_confidence_avg,
            )
            for index, turn in enumerate(turns)
        ],
        signals=signals_out,
        comparison=comparison_out,
        disclaimer=exports.DISCLAIMER,
    )


@router.get("/{session_id}")
@limiter.limit(STANDARD_RATE_LIMIT)
def get_feedback(
    request: Request,
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session, report = _require_report(db, user, session_id)
    return success(_build_report_out(db, user, session, report).model_dump(by_alias=True, mode="json"))


@router.get("/{session_id}/status")
@limiter.limit(STANDARD_RATE_LIMIT)
def get_feedback_status(
    request: Request,
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    What Section 4.10's processing screen polls.

    Returns PENDING (rather than 404) when no row exists yet but the interview is
    over, so a client that reaches this before the background job has claimed the
    row sees a lifecycle state instead of an error it has to special-case.
    """
    session = interview_service.get_session_for_user(db, user, session_id)
    report = generator.get_report(db, session.id)
    if report is None:
        return success(
            FeedbackStatusOut(
                session_id=session.id, status=FeedbackGenerationStatus.PENDING
            ).model_dump(by_alias=True, mode="json")
        )
    return success(
        FeedbackStatusOut(
            session_id=session.id,
            status=report.generation_status,
            generated_at=report.generated_at,
            # Only surfaced on a real failure. `generation_error` is also set on
            # a READY report when the provider was unavailable and the
            # deterministic writer stood in — that's a success, and reporting it
            # as an error would make the processing screen cry wolf. The
            # fallback is communicated by `generatedBy: "deterministic"` on the
            # report itself instead.
            error=(
                report.generation_error
                if report.generation_status == FeedbackGenerationStatus.FAILED
                else None
            ),
        ).model_dump(by_alias=True, mode="json")
    )


@router.post("/{session_id}/generate")
@limiter.limit(STANDARD_RATE_LIMIT)
async def generate_feedback(
    request: Request,
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis),
):
    """
    Generate (or regenerate) the report, awaiting the result.

    Synchronous by design: this is the explicit "generate my report" / retry
    action, so the caller wants the report, not a job ID. The automatic path when
    an interview ends is the asynchronous one (`generator.schedule_generation`).

    Metered against the export quota because a regenerate is a real provider
    call — Section 12.1A's cost-control tier, not just abuse prevention.
    """
    session = interview_service.get_session_for_user(db, user, session_id)
    if not generator.is_generation_allowed(session):
        raise ApiError(
            status_code=409,
            code="interview_in_progress",
            message="This interview hasn't finished yet, so there's nothing to report on.",
        )

    ai_quota.consume_export(redis_client, str(user.id))
    report = await generator.generate_report(db, session)
    return success(_build_report_out(db, user, session, report).model_dump(by_alias=True, mode="json"))


@router.get("/{session_id}/pdf")
@limiter.limit(STANDARD_RATE_LIMIT)
def download_feedback_pdf(
    request: Request,
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis),
):
    """Section 7.4's `GET /feedback/:sessionId/pdf`."""
    session, report = _require_report(db, user, session_id)
    if report.generation_status != FeedbackGenerationStatus.READY:
        raise ApiError(
            status_code=409,
            code="feedback_not_ready",
            message="Your report is still being generated. Try the download again in a moment.",
        )

    ai_quota.consume_export(redis_client, str(user.id))
    turns = load_turns(db, session.id)
    pdf_bytes = exports.report_pdf(session, report, turns)
    filename = f"{exports.filename_stem(session)}-feedback.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # A report is personal data; no shared cache should hold a copy.
            "Cache-Control": "private, no-store",
        },
    )
