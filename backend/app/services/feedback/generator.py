"""
Feedback Generation Service (Section 6.1, Section 9.8).

Section 9.8's pipeline, in order:

1. Read the session's questions, answers and `answer_evaluations`.
2. Compute the deterministic scores (`scoring.py`) — skip-aware, weights from
   the config table.
3. Build a grounded prompt from those facts (`prompts.py`).
4. Ask a provider for the qualitative half, via the gateway so it inherits
   Section 6.7's failover and Section 9.3A's cost accounting.
5. Persist scores + narrative to `feedback_reports` / `feedback_details`.

The division of labour in step 4/5 is the point: "LLM handles qualitative
content, deterministic code handles the score." The model never sees a score it
can change, so the narrative and the number cannot disagree — and if no model
is available at all, `narrative.py` writes from the same facts and the report
still ships, labelled as rule-based (Section 21.2's degraded-mode requirement).

Idempotency: `feedback_reports.session_id` is unique, so generation upserts.
Regenerating replaces the details rather than appending, which keeps a
re-run from doubling every strength.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.timeutils import utcnow
from app.models.enums import FeedbackGenerationStatus, SessionStatus
from app.models.feedback import FeedbackDetail, FeedbackReport
from app.models.interview import InterviewSession
from app.services.ai.contracts import LLMRequest
from app.services.ai.errors import LLMProviderError
from app.services.ai.gateway import get_gateway
from app.services.feedback import narrative as narrative_writer
from app.services.feedback import prompts
from app.services.feedback.prompts import GeneratedNarrative
from app.services.feedback.scoring import ScoreBreakdown, TurnRecord, compute_breakdown, load_turns

logger = logging.getLogger("mockmateai.feedback")

DETERMINISTIC_AUTHOR = "deterministic"


def build_facts(session: InterviewSession, turns: list[TurnRecord], breakdown: ScoreBreakdown) -> dict:
    """
    Everything the prompt is allowed to know, and nothing else.

    Assembled here rather than inside `prompts.py` so the prompt module stays a
    pure formatter with no database or ORM knowledge — which is what makes the
    prompt testable against fixed facts and keeps Section 15's evaluation set
    from needing a database.
    """
    signals = breakdown.signals
    return {
        "session": {
            "role_target": session.role_target,
            "interview_type": session.interview_type.value,
            "duration_minutes": session.duration_minutes,
            "target_company_name": session.target_company_name,
            "question_count": len(turns),
            "answered_count": breakdown.answered_count,
            "skipped_count": breakdown.skipped_count,
        },
        "scores": {
            "overall_readiness_score": breakdown.overall_readiness_score,
            "content_score": breakdown.content_score,
            "communication_score": breakdown.communication_score,
            "confidence_score": breakdown.confidence_score,
            "body_language_score": breakdown.body_language_score,
        },
        "signals": (
            {
                "total_words": signals.total_words,
                "answer_count": signals.answer_count,
                "filler_count": signals.filler_count,
                "average_answer_words": round(signals.average_answer_words, 1),
                "quantified_answers": signals.quantified_answers,
                "under_elaborated_answers": signals.under_elaborated_answers,
                "well_developed_answers": signals.well_developed_answers,
                "speaking_pace_wpm": (
                    round(signals.speaking_pace_wpm, 1) if signals.speaking_pace_wpm is not None else None
                ),
            }
            if signals is not None
            else None
        ),
        "turns": [
            {
                "number": index + 1,
                "question_text": turn.question_text,
                "is_followup": turn.is_followup,
                "answer_text": turn.transcript_text,
                "is_skipped": turn.is_skipped,
                "relevance_score": turn.relevance_score,
                "completeness_score": turn.completeness_score,
            }
            for index, turn in enumerate(turns)
        ],
    }


async def _request_narrative(
    session: InterviewSession, facts: dict, breakdown: ScoreBreakdown
) -> tuple[GeneratedNarrative, str, int]:
    """
    Step 4: ask a provider for the qualitative half.

    Returns (narrative, author, tokens_used). Raises `LLMProviderError` when no
    provider could serve it, which the caller turns into the deterministic path
    rather than a failed report.
    """
    settings = get_settings()
    system_prompt = prompts.build_system_prompt(breakdown.measured_categories, breakdown.unmeasured_categories)
    request = LLMRequest(
        system_prompt=system_prompt,
        conversation=[{"role": "user", "content": prompts.build_context_message(facts)}],
        max_output_tokens=settings.llm_max_output_tokens,
        json_schema=prompts.FEEDBACK_REPORT_SCHEMA,
        schema_name="feedback_report",
    )

    gateway = get_gateway()
    response = await gateway.complete_json(request, session_id=str(session.id))

    try:
        result = GeneratedNarrative.model_validate(response.payload)
    except Exception as exc:
        # Same clamp-don't-trust posture as Section 12.8's turn validation: a
        # provider that returns the wrong shape is a provider failure, not
        # something to persist half of.
        raise LLMProviderError(
            f"Feedback provider returned a payload that failed validation: {exc}", provider=response.provider
        ) from exc

    # Section 12.8's other half, applied to the report: drop items in
    # categories nothing measured, even if the prompt told the model not to
    # write them. Prompt-level defense is never sufficient on its own — an item
    # about eye contact in a session with no video is a fabrication regardless
    # of how it got there.
    allowed = set(breakdown.measured_categories)
    kept = [item for item in result.items if item.category.value in allowed]
    dropped = len(result.items) - len(kept)
    if dropped:
        logger.warning(
            "Dropped %s feedback item(s) in unmeasured categories [session_id=%s provider=%s]",
            dropped,
            session.id,
            response.provider,
        )
    result = GeneratedNarrative(summary_text=result.summary_text, items=kept)

    return result, response.provider, response.usage.total


def _persist(
    db: Session,
    report: FeedbackReport,
    breakdown: ScoreBreakdown,
    result: GeneratedNarrative,
    author: str,
    error: str | None,
) -> FeedbackReport:
    """Step 5. Details are replaced wholesale so a regenerate doesn't duplicate items."""
    report.overall_readiness_score = breakdown.overall_readiness_score
    report.content_score = breakdown.content_score
    report.communication_score = breakdown.communication_score
    report.confidence_score = breakdown.confidence_score
    report.body_language_score = breakdown.body_language_score
    report.summary_text = result.summary_text
    report.generated_by = author
    report.generation_error = error
    report.generation_status = FeedbackGenerationStatus.READY
    report.generated_at = utcnow()

    for existing in list(report.details):
        db.delete(existing)
    report.details = []
    db.flush()

    for item in result.items:
        db.add(
            FeedbackDetail(
                report_id=report.id,
                category=item.category,
                type=item.type,
                text=item.text,
                evidence_reference=item.evidence_reference(),
            )
        )

    db.commit()
    db.refresh(report)
    return report


def get_report(db: Session, session_id) -> FeedbackReport | None:
    return db.scalars(select(FeedbackReport).where(FeedbackReport.session_id == session_id)).first()


def claim_report(db: Session, session_id) -> FeedbackReport:
    """
    Create-or-reuse the report row and mark it PROCESSING before any slow work
    starts, so Section 4.10's processing screen has something to poll
    immediately after the interview ends rather than a 404 for several seconds.
    """
    report = get_report(db, session_id)
    if report is None:
        report = FeedbackReport(session_id=session_id, generation_status=FeedbackGenerationStatus.PROCESSING)
        db.add(report)
    else:
        report.generation_status = FeedbackGenerationStatus.PROCESSING
        report.generation_error = None
    db.commit()
    db.refresh(report)
    return report


async def generate_report(db: Session, session: InterviewSession) -> FeedbackReport:
    """
    Run the whole pipeline for one session and return the persisted report.

    Never raises for a provider problem — Section 21.2 requires a defined
    degraded-mode outcome, and a candidate who just finished an interview should
    get their report either way. It does raise if the database itself fails,
    because silently pretending to have saved a report would be worse.
    """
    report = claim_report(db, session.id)

    turns = load_turns(db, session.id)
    breakdown = compute_breakdown(db, session.id, turns)
    facts = build_facts(session, turns, breakdown)

    author = DETERMINISTIC_AUTHOR
    error: str | None = None
    try:
        result, author, tokens_used = await _request_narrative(session, facts, breakdown)
        if tokens_used:
            # Section 9.3A: the report call is a real cost against this
            # session, so it lands in the same counter the interview turns use.
            session.total_tokens_used = (session.total_tokens_used or 0) + tokens_used
            db.add(session)
    except LLMProviderError as exc:
        error = str(exc)
        logger.warning("Feedback narrative fell back to deterministic [session_id=%s]: %s", session.id, exc)
        result = narrative_writer.build_narrative(breakdown, turns)
        author = DETERMINISTIC_AUTHOR

    return _persist(db, report, breakdown, result, author, error)


def mark_failed(db: Session, session_id, reason: str) -> None:
    """
    Record a generation failure that wasn't a provider problem — a bug, or the
    process dying mid-run. Kept separate from the degraded path on purpose: a
    deterministic report is a success, and conflating the two would hide real
    breakage behind a report that looks fine.
    """
    report = get_report(db, session_id)
    if report is None:
        return
    report.generation_status = FeedbackGenerationStatus.FAILED
    report.generation_error = reason[:2000]
    db.commit()


async def run_generation_job(session_id) -> None:
    """
    Fire-and-forget wrapper used when an interview ends.

    Opens its OWN database session: the request (or WebSocket) that ended the
    interview has already returned by the time this runs, and its session is
    closed. Swallows every exception into `mark_failed` so a background task
    can't take the event loop's exception handler with it — but records the
    reason, so a failure surfaces on the status endpoint instead of leaving the
    candidate's processing screen spinning forever.
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        session = db.get(InterviewSession, session_id)
        if session is None:
            logger.warning("Feedback generation skipped: session %s no longer exists", session_id)
            return
        if not is_generation_allowed(session):
            logger.info("Feedback generation skipped: session %s is still in progress", session_id)
            return
        await generate_report(db, session)
    except Exception as exc:  # noqa: BLE001 — background task of last resort
        logger.exception("Feedback generation failed [session_id=%s]", session_id)
        try:
            mark_failed(db, session_id, f"{type(exc).__name__}: {exc}")
        except Exception:
            logger.exception("Could not record the feedback generation failure [session_id=%s]", session_id)
    finally:
        db.close()


# Strong references to in-flight background tasks. Without this the event loop
# holds only a weak reference and a report can be garbage-collected mid-write.
_background_tasks: set = set()


def schedule_generation(session_id) -> None:
    """
    Kick off generation without blocking the caller.

    Section 4.10's processing screen exists precisely because this work takes
    seconds: the interview's final WebSocket frame or REST response must not
    wait on an LLM call. `claim_report` runs synchronously first so the status
    endpoint reports PROCESSING immediately rather than 404 for the first second.
    """
    import asyncio

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        claim_report(db, session_id)
    except Exception:
        logger.exception("Could not claim the feedback report row [session_id=%s]", session_id)
    finally:
        db.close()

    task = asyncio.create_task(run_generation_job(session_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def is_generation_allowed(session: InterviewSession) -> bool:
    """
    A report describes a finished interview. Generating one mid-session would
    score a partial transcript and then be cached against a session that keeps
    going.
    """
    return session.status in (SessionStatus.COMPLETED, SessionStatus.ABANDONED)
