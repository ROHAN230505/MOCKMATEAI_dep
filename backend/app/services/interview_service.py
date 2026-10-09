"""
Interview session business logic.

Phase 2 established the session lifecycle over a fixed pre-planned question
list. Phase 3 layers the LLM engine on top: the planned questions from
app/content/question_bank.py are now a *topic backbone* rather than the
literal script, and the engine (app/services/llm_engine.py) decides what is
actually said, whether to probe with a follow-up, and how each answer scores.

`question_text` semantics on `interview_questions`, worth stating plainly
since it is deliberately overloaded and Phase 2 set the precedent:
- BEFORE a question is asked (`asked_at IS NULL`) it holds the planned topic
  seed from the question bank.
- ONCE asked (`asked_at` set) it holds the actual utterance the candidate
  heard, which Section 4.8A requires ("`question_text` reflects the full
  intended question").
This works precisely because only unasked rows are ever read as seeds, and it
avoids a second column plus a migration for information that is never needed
after the question has been delivered.
"""
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.content.question_bank import select_planned_questions
from app.core.responses import ApiError
from app.schemas.common import strip_unstorable
from app.core.timeutils import utcnow
from app.models.enums import (
    InterviewMode,
    LLMProvider,
    QuestionType,
    SessionStatus,
    TransportMode,
)
from app.models.interview import (
    AnswerEvaluation,
    InterviewAnswer,
    InterviewQuestion,
    InterviewSession,
)
from app.models.user import User
from app.services import llm_engine
from app.services.ai.contracts import TurnDecision
from app.services.llm_engine import EngineContext, EngineTurn

logger = logging.getLogger("mockmateai.interview_service")


def _clean_text(value: str | None) -> str | None:
    """Same control-character strip the REST schemas get, for the raw WS path."""
    return None if value is None else strip_unstorable(value)


def start_session(
    db: Session,
    user: User,
    *,
    role: str,
    interview_type,
    duration_minutes: int,
    mode: InterviewMode,
    consent_given: bool,
    job_description_text: str | None,
    target_company_name: str | None,
) -> InterviewSession:
    if not consent_given:
        raise ApiError(
            status_code=400,
            code="consent_required",
            message="Recording consent is required before starting an interview.",
        )
    # Section 4.6: the role dropdown is optional *when a JD is supplied* (the
    # JD then drives the prompt), but one of the two must be present or there
    # is nothing to tailor the interview to at all.
    role_target = role.strip()
    jd = (job_description_text or "").strip()
    if not role_target and not jd:
        raise ApiError(
            status_code=400,
            code="role_or_job_description_required",
            message="Select a role, or paste a job description to tailor the interview to.",
        )
    if not role_target:
        # `role_target` is NOT NULL and is what the history list and the
        # "vs. Last Attempt" comparison (Section 4.11A) group by, so a
        # JD-only session still needs a human-readable label.
        role_target = "Role from job description"

    session = InterviewSession(
        user_id=user.id,
        role_target=role_target,
        interview_type=interview_type,
        duration_minutes=duration_minutes,
        mode=mode,
        status=SessionStatus.IN_PROGRESS,
        started_at=utcnow(),
        consent_given=True,
        job_description_text=job_description_text,
        target_company_name=target_company_name,
        transport_mode=TransportMode.BROWSER_NATIVE_SPEECH,
    )
    db.add(session)
    db.flush()  # assigns session.id without a full commit yet

    question_texts = select_planned_questions(interview_type, duration_minutes)
    for order, text in enumerate(question_texts):
        db.add(
            InterviewQuestion(
                session_id=session.id,
                sequence_order=order,
                question_text=text,
                question_type=QuestionType.PLANNED,
            )
        )
    db.commit()
    db.refresh(session)
    return session


def get_session_for_user(db: Session, user: User, session_id) -> InterviewSession:
    session = db.execute(
        select(InterviewSession)
        .options(selectinload(InterviewSession.questions).selectinload(InterviewQuestion.answer))
        .where(InterviewSession.id == session_id)
    ).scalar_one_or_none()

    # 404, not 403, on a mismatched owner — Section 12.2 IDOR guidance:
    # never confirm to a non-owner that the resource exists at all.
    if session is None or session.user_id != user.id:
        raise ApiError(status_code=404, code="session_not_found", message="Interview session not found.")
    return session


def list_history(db: Session, user: User, *, limit: int = 20, offset: int = 0) -> list[InterviewSession]:
    return list(
        db.execute(
            select(InterviewSession)
            .where(InterviewSession.user_id == user.id)
            # `started_at` alone is not a total order. The clock this runs on has
            # coarse resolution (~15ms on Windows), so two sessions can share a
            # timestamp exactly -- and without a tiebreaker the database is free to
            # return tied rows in a different order on each call, which would let a
            # paged history repeat one session and drop another across pages.
            .order_by(InterviewSession.started_at.desc(), InterviewSession.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )


def end_session(db: Session, user: User, session_id) -> InterviewSession:
    session = get_session_for_user(db, user, session_id)
    if session.status == SessionStatus.IN_PROGRESS:
        session.status = SessionStatus.COMPLETED
        session.ended_at = utcnow()
        db.commit()
        db.refresh(session)
    return session


def get_ordered_questions(session: InterviewSession) -> list[InterviewQuestion]:
    return sorted(session.questions, key=lambda q: q.sequence_order)


def get_next_unanswered_question(session: InterviewSession) -> InterviewQuestion | None:
    for question in get_ordered_questions(session):
        if question.answer is None:
            return question
    return None


def mark_question_asked(db: Session, question: InterviewQuestion, *, interrupted_at_char_offset: int | None = None) -> None:
    question.asked_at = utcnow()
    question.interrupted_at_char_offset = interrupted_at_char_offset
    db.commit()


def record_barge_in(db: Session, question: InterviewQuestion, *, char_offset: int | None) -> None:
    """
    Records where TTS playback actually stopped (Section 4.8A's
    `interrupted_at_char_offset`) WITHOUT touching `asked_at`.

    Separate from `mark_question_asked` because in Phase 3 `asked_at` carries
    the "this question has been delivered" meaning that drives question
    sequencing — re-stamping it on every barge-in would blur that.
    """
    question.interrupted_at_char_offset = char_offset
    db.commit()


def record_answer(
    db: Session,
    question: InterviewQuestion,
    *,
    transcript_text: str | None,
    is_skipped: bool,
    asr_confidence_avg: float | None,
    answer_started_at: float | None,
    answer_ended_at: float | None,
    #: Section 8's `code_panel_snapshot` -- what was on the shared code panel at
    #: the moment this answer was given, or None if nothing was shared.
    code_panel_snapshot: str | None = None,
) -> InterviewAnswer:
    """
    Idempotent per question: a reconnect/retry that resubmits the same
    question's answer overwrites rather than duplicating (interview_answers
    has a unique constraint on question_id, Section 8).

    The transcript is stripped of unstorable control characters first. This is
    the one text path into the database that does *not* go through a
    `CamelModel` — the WebSocket handler reads `transcriptText` straight off a
    raw JSON frame — so the base-model validator that protects every REST body
    (see `schemas/common.py`) does not cover it, and a NUL byte here would raise
    the same unhandled `psycopg.DataError` that a pasted job description did.

    Assigns through the `question.answer` relationship (not a bare
    `InterviewAnswer(question_id=...)`) so the in-memory object graph stays
    consistent for the WebSocket handler, which holds the same `session`
    (and its `questions`) for the whole connection's lifetime — a raw FK
    assignment wouldn't update the already-loaded `question.answer`
    backref, and `get_next_unanswered_question` would keep seeing it as
    unanswered.
    """
    transcript_text = _clean_text(transcript_text)

    if question.answer is not None:
        answer = question.answer
        answer.transcript_text = transcript_text
        answer.is_skipped = is_skipped
        answer.asr_confidence_avg = asr_confidence_avg
        answer.answer_started_at = answer_started_at
        answer.answer_ended_at = answer_ended_at
        answer.code_panel_snapshot = code_panel_snapshot
    else:
        answer = InterviewAnswer(
            transcript_text=transcript_text,
            is_skipped=is_skipped,
            asr_confidence_avg=asr_confidence_avg,
            answer_started_at=answer_started_at,
            answer_ended_at=answer_ended_at,
            code_panel_snapshot=code_panel_snapshot,
        )
        question.answer = answer
        db.add(answer)

    db.commit()
    db.refresh(answer)
    return answer


# ---------------------------------------------------------------------------
# Phase 3 — LLM engine integration (Sections 9.3, 9.3A, 10.3)
# ---------------------------------------------------------------------------


def root_question_of(session: InterviewSession, question: InterviewQuestion) -> InterviewQuestion:
    """
    The originally-planned question a follow-up chain hangs off.

    Follow-ups store `parent_question_id` pointing at the ROOT planned
    question rather than at their immediate predecessor. Section 8 describes
    the column as a self-ref for follow-ups without mandating either shape,
    and root-pointing is what Section 10.3's cap actually needs — "no more
    than 2 consecutive follow-ups on the same original question" is a count
    per original question, which a flat star answers in one pass. Chain order
    is not lost: `sequence_order` still records it.
    """
    if question.question_type != QuestionType.FOLLOWUP or question.parent_question_id is None:
        return question
    by_id = {q.id: q for q in session.questions}
    return by_id.get(question.parent_question_id, question)


def count_consecutive_followups(session: InterviewSession, question: InterviewQuestion) -> int:
    """How many follow-ups already hang off this question's root (Section 10.3's cap input)."""
    root = root_question_of(session, question)
    return sum(
        1
        for q in session.questions
        if q.question_type == QuestionType.FOLLOWUP and q.parent_question_id == root.id
    )


def _planned_questions(session: InterviewSession) -> list[InterviewQuestion]:
    return [q for q in get_ordered_questions(session) if q.question_type == QuestionType.PLANNED]


def next_unasked_planned_question(session: InterviewSession) -> InterviewQuestion | None:
    """
    Next planned row that hasn't been delivered yet. Keyed on `asked_at`
    rather than on whether it has an answer, because Phase 3 asks a question
    and only later receives its answer — an unanswered-but-already-asked row
    is the *current* question, not the next one.
    """
    for question in _planned_questions(session):
        if question.asked_at is None:
            return question
    return None


def build_engine_context(
    session: InterviewSession,
    user: User,
    *,
    current_question: InterviewQuestion | None = None,
    current_answer_text: str | None = None,
) -> EngineContext:
    """Assembles Section 9.3's "CONTEXT PROVIDED EACH TURN" from persisted state."""
    ordered = get_ordered_questions(session)

    # Prior turns, excluding the one being evaluated right now (that arrives
    # via current_question/current_answer_text so the engine can fence it and
    # attach interruption context).
    history: list[tuple[str, str | None, bool]] = []
    for question in ordered:
        if current_question is not None and question.id == current_question.id:
            continue
        if question.asked_at is None:
            continue
        answer = question.answer
        history.append(
            (
                question.question_text,
                answer.transcript_text if answer else None,
                bool(answer.is_skipped) if answer else False,
            )
        )

    unasked = [q for q in _planned_questions(session) if q.asked_at is None]
    next_planned = unasked[0] if unasked else None

    return EngineContext(
        session_id=str(session.id),
        role_target=session.role_target,
        interview_type=session.interview_type.value,
        duration_minutes=session.duration_minutes,
        experience_level=user.experience_level.value if user.experience_level else None,
        job_description_text=session.job_description_text,
        target_company_name=session.target_company_name,
        # The full planned list is what makes the system prompt stable; only
        # already-delivered rows have had their text replaced by an utterance,
        # so seeds are read exclusively from unasked rows.
        planned_topics=[q.question_text for q in unasked],
        next_planned_topic=next_planned.question_text if next_planned else None,
        remaining_topic_count=len(unasked),
        history=history,
        current_question_text=current_question.question_text if current_question else None,
        current_answer_text=current_answer_text,
        interrupted_at_char_offset=(
            current_question.interrupted_at_char_offset if current_question else None
        ),
        code_panel_snapshot=(
            current_question.answer.code_panel_snapshot
            if current_question is not None and current_question.answer is not None
            else None
        ),
        consecutive_followups=(
            count_consecutive_followups(session, current_question) if current_question else 0
        ),
        tokens_used=session.total_tokens_used,
        calls_made=session_llm_call_count(session),
    )


def session_llm_call_count(session: InterviewSession) -> int:
    """
    Calls made so far, derived from delivered questions rather than tracked in
    its own column: every engine call produces exactly one asked question, so
    the count is already in the data and can't drift out of sync with it.
    """
    return sum(1 for q in session.questions if q.asked_at is not None)


def _record_usage(db: Session, session: InterviewSession, turn: EngineTurn) -> None:
    """Section 9.3A's per-session cost accounting -> `interview_sessions.total_tokens_used`."""
    session.total_tokens_used = (session.total_tokens_used or 0) + turn.usage.total

    # Section 8's `llm_provider_used`. Only recorded for providers the enum
    # knows about; `mock` and `none` (degraded mode) are real states the
    # column can't express, and inventing an enum value for them would make
    # analytics lie about which vendor served a session.
    try:
        session.llm_provider_used = LLMProvider(turn.provider)
    except ValueError:
        pass

    db.commit()


def _persist_evaluation(db: Session, answer: InterviewAnswer, turn: EngineTurn) -> AnswerEvaluation | None:
    """
    Persists Section 9.3's `internal_evaluation` to `answer_evaluations` so
    the Feedback Generation Service (Phase 4) reuses the same scores the live
    follow-up decision was made on — Section 9.3's "single source of truth for
    'was this answer actually good'".

    Skips are stored with NULL scores and `followup_triggered = False`, never
    zeros, so Section 9.8's skip-aware aggregation can exclude them from
    averages instead of counting them as failures.
    """
    if answer is None:
        return None

    """
    An answer with nothing in it is never scored.

    The model will happily score silence, and does: a session with no
    transcript on any turn came back with 10/10 on one question, 0/10 on
    another and 2/10 on a third. Those numbers describe nothing. They are
    exactly the failure this codebase refuses everywhere else -- a figure
    presented as a measurement that was never taken -- and they are worse than
    useless to a candidate, who cannot tell a genuine 0 from a microphone that
    was not working.

    A skip is different and is handled below: the candidate chose to pass, that
    choice is real, and it is stored with NULL scores rather than zeros.
    Silence is not a choice, so it gets the same NULL treatment and the report
    shows the question as unanswered instead of failed.
    """
    if not (answer.transcript_text or "").strip() and not answer.is_skipped:
        logger.info(
            "No transcript for question %s; recording it as unanswered rather than scoring it.",
            answer.question_id,
        )
        existing_empty = db.execute(
            select(AnswerEvaluation).where(AnswerEvaluation.answer_id == answer.id)
        ).scalar_one_or_none()
        if existing_empty is not None:
            existing_empty.relevance_score = None
            existing_empty.completeness_score = None
            existing_empty.followup_triggered = False
            db.commit()
        return None

    reason = turn.guardrail_reason
    if turn.evaluation and turn.evaluation.reasoning:
        reason = f"{turn.evaluation.reasoning} | Guardrail: {turn.guardrail_reason}"
    if turn.transcript_truncated:
        # Section 9.3A: "note internally that truncation occurred, so the
        # evaluation isn't silently based on a cut-off answer without anyone
        # knowing why."
        reason = f"[transcript truncated for LLM context] {reason}"

    existing = db.execute(
        select(AnswerEvaluation).where(AnswerEvaluation.answer_id == answer.id)
    ).scalar_one_or_none()

    relevance = turn.evaluation.relevance_score if turn.evaluation else None
    completeness = turn.evaluation.completeness_score if turn.evaluation else None
    followup_triggered = turn.decision == TurnDecision.FOLLOWUP

    if existing is not None:
        existing.relevance_score = relevance
        existing.completeness_score = completeness
        existing.followup_triggered = followup_triggered
        existing.followup_reason_text = reason
        evaluation = existing
    else:
        evaluation = AnswerEvaluation(
            relevance_score=relevance,
            completeness_score=completeness,
            followup_triggered=followup_triggered,
            followup_reason_text=reason,
        )
        answer.evaluation = evaluation
        db.add(evaluation)

    db.commit()
    return evaluation


def _next_sequence_order(session: InterviewSession) -> int:
    return max((q.sequence_order for q in session.questions), default=-1) + 1


def _is_transition_only(text: str) -> bool:
    """
    Whether an utterance moves the conversation along without asking anything.

    Deliberately narrow: it matches the short, self-contained filler the model
    produces when it writes a segue and forgets the question -- "Sure, let's
    move on.", "No problem, let's move on." -- and nothing longer. A real
    question that happens to open with "No problem, let's move on. Explain..."
    is left alone, because the length check alone excludes it.

    A question mark is taken as proof there is a question, which is why the
    check runs on the whole utterance rather than on its first sentence.
    """
    stripped = text.strip()
    if "?" in stripped:
        return False
    # Anything this short cannot contain both a segue and a question.
    if len(stripped) > 90:
        return False
    lowered = stripped.lower().rstrip(" .!")
    return any(
        lowered.endswith(tail)
        for tail in ("move on", "moving on", "next question", "carry on", "continue")
    )


def _deliver(
    db: Session,
    session: InterviewSession,
    question: InterviewQuestion,
    turn: EngineTurn,
) -> InterviewQuestion:
    """
    Stamps the engine's actual utterance onto a question row and marks it
    delivered -- repairing it first if the model sent a transition and forgot
    the question.

    Observed in a real session: rows reading exactly "Sure, let's move on." and
    "No problem, let's move on." were stored and shown as questions 5 and 6. A
    candidate cannot answer those, and the report then displays them as
    questions they failed to answer.

    The planned text is the natural repair, because a `next_question` turn
    already has one queued -- the model simply omitted it while writing its
    transition. Where there is nothing queued, the utterance is left alone
    rather than invented: a bare transition at the end of an interview is the
    model winding down, which is fine to say and merely odd to log.
    """
    utterance = (turn.utterance or "").strip()
    if utterance and _is_transition_only(utterance):
        planned = (question.question_text or "").strip()
        if planned and not _is_transition_only(planned):
            logger.info(
                "Engine returned a transition with no question (%r); using the planned text.",
                utterance[:60],
            )
            utterance = f"{utterance} {planned}" if utterance.endswith((".", "!", "?")) else planned
        else:
            logger.warning("Engine returned a transition with no question and none was queued: %r", utterance[:60])

    question.question_text = utterance or turn.utterance
    question.asked_at = utcnow()
    db.commit()
    db.refresh(question)
    return question


async def ask_opening_question(
    db: Session, session: InterviewSession, user: User
) -> tuple[InterviewQuestion, EngineTurn]:
    """
    Generates and delivers question one via the engine.

    Routed through the LLM rather than using the bank text verbatim so JD and
    company targeting (Section 4.6) shape the very first question, not just
    questions two onward.
    """
    question = next_unasked_planned_question(session)
    if question is None:
        raise ApiError(status_code=409, code="no_questions_available", message="This interview has no questions left.")

    context = build_engine_context(session, user)
    turn = await llm_engine.run_turn(context, is_opening=True)
    _deliver(db, session, question, turn)
    _record_usage(db, session, turn)
    return question, turn


async def evaluate_and_advance(
    db: Session,
    session: InterviewSession,
    user: User,
    *,
    question: InterviewQuestion,
    answer: InterviewAnswer,
) -> tuple[InterviewQuestion | None, EngineTurn]:
    """
    The core Phase 3 turn: evaluate the answer just given, persist the
    evaluation, then deliver whatever the engine (post-guardrails) decided to
    say next.

    Returns `(next_question_or_None, turn)`. `None` means no question was
    delivered because the interview has run out of planned topics — the
    caller ends the session.
    """
    context = build_engine_context(
        session,
        user,
        current_question=question,
        current_answer_text=None if answer.is_skipped else answer.transcript_text,
    )

    # Section 10.3's skip exception is decided from persisted state, not
    # re-inferred from the transcript: an explicit Skip button press
    # (Section 4.8) must bypass evaluation even though the transcript may be
    # empty rather than containing pass language.
    if answer.is_skipped:
        turn = await _skip_turn(context)
    else:
        turn = await llm_engine.run_turn(context)
        if turn.decision == TurnDecision.SKIP:
            # The engine detected a spoken pass-phrase (Section 4.8's "the
            # same outcome is triggered by the candidate saying an equivalent
            # phrase out loud"). Reflect that onto the stored answer so the
            # feedback report shows the same distinct Skipped badge a button
            # press produces.
            answer.is_skipped = True
            answer.transcript_text = answer.transcript_text or None
            db.commit()

    _persist_evaluation(db, answer, turn)
    _record_usage(db, session, turn)

    if turn.decision == TurnDecision.FOLLOWUP:
        root = root_question_of(session, question)
        followup = InterviewQuestion(
            session_id=session.id,
            sequence_order=_next_sequence_order(session),
            question_text=turn.utterance,
            question_type=QuestionType.FOLLOWUP,
            parent_question_id=root.id,
            asked_at=utcnow(),
        )
        db.add(followup)
        session.questions.append(followup)
        db.commit()
        db.refresh(followup)
        return followup, turn

    next_question = next_unasked_planned_question(session)
    if next_question is None:
        return None, turn

    _deliver(db, session, next_question, turn)
    return next_question, turn


async def _skip_turn(context: EngineContext) -> EngineTurn:
    """
    Builds the turn for an explicit Skip-button press without spending an LLM
    call. Section 10.3 bypasses every scoring/follow-up guardrail for a skip,
    so there is nothing for the model to decide — paying for a call to be told
    "move on" would be pure cost against Section 9.3A's budget.
    """
    from app.services.ai.contracts import TokenUsage

    if context.next_planned_topic:
        utterance = f"No problem, let's move on. {context.next_planned_topic}"
    else:
        utterance = "No problem. That's everything I wanted to cover — thanks for your time today."

    return EngineTurn(
        decision=TurnDecision.SKIP,
        utterance=utterance,
        evaluation=None,
        guardrail_reason="Candidate used the Skip control; skip bypasses all follow-up guardrails.",
        guardrail_overridden=False,
        usage=TokenUsage(),
        provider="none",
        model="none",
    )


def most_recent_completed_for_role(db: Session, user: User, role: str) -> list[InterviewSession]:
    """
    The single most recent completed session for a role (Section 7.3's `compareRole`).

    Returned as a list rather than a scalar so the history endpoint's response
    shape does not change based on its query parameters — a client parsing an
    array should not have to branch on whether it asked for a comparison.

    Matched case-insensitively on a trimmed role: "SDE" and "sde " are the same
    target to a candidate, and Section 4.11A compares "the same `role_target`",
    which is free text the candidate typed.
    """
    needle = (role or "").strip().lower()
    if not needle:
        return []

    return list(
        db.scalars(
            select(InterviewSession)
            .where(
                InterviewSession.user_id == user.id,
                InterviewSession.status == SessionStatus.COMPLETED,
                func.lower(func.trim(InterviewSession.role_target)) == needle,
            )
            # Same total-order argument as `list_history`: with LIMIT 1 over a tie,
            # an untiebroken sort makes "the previous session" arbitrary.
            .order_by(InterviewSession.started_at.desc(), InterviewSession.id.desc())
            .limit(1)
        )
    )
