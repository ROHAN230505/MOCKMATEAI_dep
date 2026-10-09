"""Interview session REST + WebSocket endpoints (Section 7.3)."""
import logging
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_current_user_ws
from app.core.rate_limit import STANDARD_RATE_LIMIT, limiter
from app.core.responses import ApiError, success
from app.core.timeutils import utcnow
from app.database import get_db
from app.models.enums import QuestionType, SessionStatus, TransportMode
from app.models.user import User
from app.redis_client import get_redis
from app.services.ai.contracts import TurnDecision
from app.services.ai.gateway import get_gateway
from app.schemas.common import strip_unstorable
from app.schemas.signals import ExpressionSignalIn, ProsodySignalIn
from app.schemas.interview import (
    LiveEventsIn,
    InterviewHistoryItem,
    InterviewSessionDetail,
    StartInterviewRequest,
    StartInterviewResponse,
)
from app.services import (
    ai_quota,
    expression_service,
    interview_service,
    interview_ws_registry,
    prosody_service,
)
from app.services.feedback import generator as feedback_generator
from app.services.live_channel import BufferChannel, ClientChannel, WebSocketChannel
from app.services.live_state import LiveState, MemoryLiveState, RedisLiveState

router = APIRouter(prefix="/interviews", tags=["interviews"])
logger = logging.getLogger("mockmateai.interview_ws")


@router.post("/start")
@limiter.limit(STANDARD_RATE_LIMIT)
def start_interview(
    request: Request,
    body: StartInterviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    redis_client=Depends(get_redis),
):
    # Section 12.1A's AI-cost-sensitive tier: a per-user daily budget of
    # interview minutes, on top of (not instead of) the per-IP request limit
    # already applied by the decorator above.
    ai_quota.consume_interview_minutes(redis_client, str(user.id), body.duration_minutes)

    session = interview_service.start_session(
        db,
        user,
        role=body.role,
        interview_type=body.type,
        duration_minutes=body.duration_minutes,
        mode=body.mode,
        consent_given=body.consent_given,
        job_description_text=body.job_description_text,
        target_company_name=body.target_company_name,
    )
    return success(
        StartInterviewResponse(
            session_id=session.id,
            # Relative path — the frontend combines this with its own API
            # host to build the ws:// or wss:// URL, so a reverse proxy or
            # different deployment host never needs backend config changes.
            ws_url=f"/api/v1/interviews/{session.id}/live",
            transport_mode=session.transport_mode,
        ).model_dump(by_alias=True)
    )


@router.post("/{session_id}/end")
@limiter.limit(STANDARD_RATE_LIMIT)
def end_interview(
    request: Request,
    session_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = interview_service.end_session(db, user, session_id)
    prosody_service.refresh_derived(db, session.id)  # same reason as in `_end_and_notify`
    # Section 4.10: the candidate goes straight to a processing screen, so
    # generation starts now and the response doesn't wait on it. Claiming the
    # report row synchronously means the status poll that follows immediately
    # sees `processing` rather than a 404.
    feedback_generator.claim_report(db, session.id)
    background_tasks.add_task(feedback_generator.run_generation_job, session.id)
    return success(_session_detail(session).model_dump(by_alias=True))


@router.get("/history")
@limiter.limit(STANDARD_RATE_LIMIT)
def interview_history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    compare_role: str | None = Query(
        default=None,
        alias="compareRole",
        max_length=255,
        description="Return only the most recent completed session for this role.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Past sessions, newest first.

    With `?compareRole=` it returns at most one item: the most recent *completed*
    session for that role, which is what Section 4.11A's "vs. Last Attempt" tab
    compares against. Section 7.3 specifies it returns null gracefully when there
    is no prior attempt, so an empty list is the correct answer rather than a 404
    — a candidate on their first attempt at a role has not hit an error.

    Aliased to camelCase explicitly. FastAPI would otherwise expose the Python
    name `compare_role`, and a mistyped query parameter silently falls back to
    its default rather than failing — which is exactly how the `hintIndex` bug
    in Phase 7 got in.
    """
    if compare_role is not None:
        sessions = interview_service.most_recent_completed_for_role(db, user, compare_role)
    else:
        sessions = interview_service.list_history(db, user, limit=limit, offset=offset)
    items = [
        InterviewHistoryItem(
            id=s.id,
            role_target=s.role_target,
            interview_type=s.interview_type,
            duration_minutes=s.duration_minutes,
            mode=s.mode,
            status=s.status,
            started_at=s.started_at,
            ended_at=s.ended_at,
        ).model_dump(by_alias=True)
        for s in sessions
    ]
    return success(items)


@router.get("/{session_id}")
@limiter.limit(STANDARD_RATE_LIMIT)
def get_interview(request: Request, session_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = interview_service.get_session_for_user(db, user, session_id)
    return success(_session_detail(session).model_dump(by_alias=True))


def _session_detail(session) -> InterviewSessionDetail:
    from app.schemas.interview import AnswerEvaluationOut, InterviewAnswerOut, InterviewQuestionOut

    questions = [
        InterviewQuestionOut(
            id=q.id,
            sequence_order=q.sequence_order,
            question_text=q.question_text,
            question_type=q.question_type,
            interrupted_at_char_offset=q.interrupted_at_char_offset,
            parent_question_id=q.parent_question_id,
            answer=(
                InterviewAnswerOut(
                    transcript_text=q.answer.transcript_text,
                    is_skipped=q.answer.is_skipped,
                    asr_confidence_avg=q.answer.asr_confidence_avg,
                )
                if q.answer
                else None
            ),
            evaluation=(
                AnswerEvaluationOut(
                    relevance_score=q.answer.evaluation.relevance_score,
                    completeness_score=q.answer.evaluation.completeness_score,
                    followup_triggered=q.answer.evaluation.followup_triggered,
                    followup_reason_text=q.answer.evaluation.followup_reason_text,
                )
                if q.answer is not None and q.answer.evaluation is not None
                else None
            ),
        )
        for q in interview_service.get_ordered_questions(session)
    ]
    return InterviewSessionDetail(
        id=session.id,
        role_target=session.role_target,
        interview_type=session.interview_type,
        duration_minutes=session.duration_minutes,
        mode=session.mode,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        transport_mode=session.transport_mode,
        total_tokens_used=session.total_tokens_used or 0,
        llm_provider_used=session.llm_provider_used.value if session.llm_provider_used else None,
        job_description_text=session.job_description_text,
        target_company_name=session.target_company_name,
        questions=questions,
    )


# ---------------------------------------------------------------------------
# Live WebSocket protocol (Section 7.3: `WS /interviews/:sessionId/live`)
#
# ASR/TTS still run client-side via the browser's Web Speech API, so this
# channel carries only JSON text/control events, never raw audio.
#
# Phase 3 moves EVALUATION server-side: the server now owns Section 10.1's
# `EVALUATING` state, because deciding what to say next is an LLM call it
# makes. The browser continues to own AI_SPEAKING vs LISTENING locally (it
# holds the speech APIs) and reports outcomes back. So the state machine is
# split by who can actually observe each state, and `turn_state_changed`
# (Section 7.3) is what keeps the two halves in sync — the client needs to
# know an evaluation is in flight so it can show a "thinking" cue instead of
# an unexplained silence.
#
# Message envelope both directions: {"type": "<event>", ...payload}.
# Server -> client: question_asked, turn_state_changed, timer_sync,
#   session_paused, session_resumed, session_ended, error.
# Client -> server: submit_answer, barge_in, heartbeat, pause_requested,
#   resume_requested, end_requested.
#
# Every Phase 2 event name and payload field is preserved; `question_asked`
# gains additive fields (`questionType`, `isFollowup`, `plannedRemaining`)
# and `turn_state_changed` is new, so a Phase 2 client keeps working.
# ---------------------------------------------------------------------------
@router.post("/{session_id}/events")
@limiter.limit(STANDARD_RATE_LIMIT)
async def interview_events(
    request: Request,
    session_id: UUID,
    body: LiveEventsIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    redis=Depends(get_redis),
):
    """
    Section 6.6's bottom rung: the live turn loop over plain HTTP.

    Used only when the WebSocket cannot be opened at all — a proxy that refuses
    the upgrade, most often. It is not a second protocol: the request carries the
    same client events the socket carries, `_handle_client_event` runs the same
    rules, and the response returns the same server events in the same order.
    The difference is purely who is holding them.

    Events are sent as a batch because a turn is naturally more than one event
    (a `code_panel_update` and then the `submit_answer` it belongs to), and one
    round trip per turn is what keeps this usable on the kind of network that
    forced the fallback in the first place.
    """
    session = interview_service.get_session_for_user(db, user, session_id)
    if session.status != SessionStatus.IN_PROGRESS:
        raise ApiError(
            status_code=409, code="session_not_active", message="This interview is not in progress."
        )
    # Section 12.1A's single-connection rule, applied to a transport with no
    # connection to count: a session being driven over a live socket must not
    # also be driven over HTTP, or two clients would interleave turns.
    if interview_ws_registry.is_registered(str(session_id)):
        raise ApiError(
            status_code=409,
            code="duplicate_connection",
            message="This interview is already open in another window.",
        )

    # Section 6.6 asks which transport an interview actually ran on. Recorded
    # the first time HTTP carries a turn, so the stored mode is a fact about
    # this session rather than the mode we hoped to use.
    if session.transport_mode != TransportMode.AUDIO_ONLY_HTTP:
        session.transport_mode = TransportMode.AUDIO_ONLY_HTTP
        db.commit()

    channel = BufferChannel()
    # Redis rather than an attribute: consecutive requests are not one
    # connection, so anything scoped to the request would lose the shared panel
    # between the turn it was typed on and the turn it belongs to.
    state = RedisLiveState(redis, session_id)
    total_seconds = session.duration_minutes * 60

    for message in body.events:
        if message.get("type") == "client_ready":
            # The socket's on-connect behaviour, made explicit. Sent once, when
            # the client has given up on the WebSocket and is falling back.
            if not await _open_session(channel, db, session, user, total_seconds=total_seconds):
                break
            continue
        if not await _handle_client_event(
            channel, db, session, user, message, state, total_seconds=total_seconds
        ):
            break

    return success({"events": channel.events, "ended": channel.closed})


@router.websocket("/{session_id}/live")
async def interview_live(
    websocket: WebSocket,
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_ws),
):
    try:
        session = interview_service.get_session_for_user(db, user, session_id)
    except ApiError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="session_not_found")

    if session.status != SessionStatus.IN_PROGRESS:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="session_not_active")

    registry_key = str(session_id)
    if not interview_ws_registry.try_register(registry_key):
        # Section 12.1A: reject a duplicate connection attempt rather than
        # silently allowing two (e.g. the same candidate with two tabs open).
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="duplicate_connection")

    await websocket.accept()
    try:
        await _run_live_session(websocket, db, session, user)
    except WebSocketDisconnect:
        # Network drop / tab closed mid-interview: leave status IN_PROGRESS
        # rather than guessing at intent — Section 5.6's reconnect banner is
        # a frontend concern; the session itself simply isn't ended yet.
        logger.info("Interview WS disconnected mid-session [session_id=%s]", session_id)
    finally:
        interview_ws_registry.unregister(registry_key)
        # Release the gateway's provider pin so a *new* session can fail back
        # to the primary provider (Section 6.7: "only fail back to the primary
        # on the next new session once the primary's health signal recovers").
        get_gateway().release_session(str(session_id))


async def _send_question(channel: ClientChannel, session, question, *, elapsed: float, total_seconds: float) -> None:
    planned_remaining = sum(
        1
        for q in session.questions
        if q.question_type == QuestionType.PLANNED and q.asked_at is None
    )
    await channel.send(
        {
            "type": "question_asked",
            "questionId": str(question.id),
            "sequenceOrder": question.sequence_order,
            "totalQuestions": len(session.questions),
            "questionText": question.question_text,
            # Additive Phase 3 fields — a Phase 2 client ignores them.
            "questionType": question.question_type.value,
            "isFollowup": question.question_type == QuestionType.FOLLOWUP,
            "plannedRemaining": planned_remaining,
        }
    )
    await channel.send({"type": "timer_sync", "elapsedSeconds": elapsed, "totalSeconds": total_seconds})


async def _open_session(
    channel: ClientChannel, db: Session, session, user: User, *, total_seconds: float
) -> bool:
    """
    Delivers the opening question. Returns False when the session ended here.

    Shared by both transports: the WebSocket calls it on connect, and the HTTP
    fallback calls it on `client_ready`, so the interview begins identically
    whichever channel is carrying it.
    """
    # --- Opening question: engine-generated so JD/company targeting applies
    # from question one (Section 4.6 / 9.3). ---
    elapsed = (utcnow() - session.started_at).total_seconds()
    if elapsed >= total_seconds:
        await _end_and_notify(channel, db, session, reason="time_up")
        return False

    await channel.send({"type": "turn_state_changed", "state": "EVALUATING"})
    try:
        question, _turn = await interview_service.ask_opening_question(db, session, user)
    except ApiError as exc:
        await channel.send({"type": "error", "code": exc.code, "message": exc.message})
        await _end_and_notify(channel, db, session, reason="completed")
        return False
    await channel.send({"type": "turn_state_changed", "state": "AI_SPEAKING"})
    await _send_question(channel, session, question, elapsed=elapsed, total_seconds=total_seconds)
    return True


async def _run_live_session(websocket: WebSocket, db: Session, session, user: User) -> None:
    total_seconds = session.duration_minutes * 60
    channel = WebSocketChannel(websocket)
    # Scoped to this connection: over a socket there is nowhere else it needs to
    # live, and nothing else can be looking at it.
    state = MemoryLiveState()

    if not await _open_session(channel, db, session, user, total_seconds=total_seconds):
        return

    while True:
        message = await websocket.receive_json()
        if not await _handle_client_event(
            channel, db, session, user, message, state, total_seconds=total_seconds
        ):
            return


async def _handle_client_event(
    channel: ClientChannel,
    db: Session,
    session,
    user: User,
    message: dict,
    state: LiveState,
    *,
    total_seconds: float,
) -> bool:
    """
    Handles one client event. Returns False when the session is over.

    Transport-agnostic on purpose — this is the whole turn loop, and both the
    WebSocket and the HTTP fallback drive it with the same events in the same
    order, so neither can drift into being a second implementation of the rules.
    """

    def elapsed_seconds() -> float:
        return (utcnow() - session.started_at).total_seconds()

    event_type = message.get("type")

    if event_type == "submit_answer":
        question = _find_question(session, message.get("questionId"))
        if question is None or question.answer is not None:
            await channel.send(
                {"type": "error", "code": "invalid_question", "message": "Unknown or already-answered question."}
            )
            return True

        answer = interview_service.record_answer(
            db,
            question,
            transcript_text=message.get("transcriptText"),
            is_skipped=bool(message.get("isSkipped", False)),
            asr_confidence_avg=message.get("asrConfidenceAvg"),
            answer_started_at=message.get("answerStartedAt"),
            answer_ended_at=message.get("answerEndedAt"),
            # Section 8: the panel content as it stood when this answer was
            # given, so the report can show what was on screen at the time.
                code_panel_snapshot=state.get_panel(),
        )

        # Time check happens BEFORE the LLM call: spending a call (and
        # Section 9.3A budget) to generate a question the candidate will
        # never be asked is pure waste.
        elapsed = elapsed_seconds()
        if elapsed >= total_seconds:
            await _end_and_notify(channel, db, session, reason="time_up")
            return False

        # Section 10.1's EVALUATING state, now server-owned.
        await channel.send({"type": "turn_state_changed", "state": "EVALUATING"})
        next_question, turn = await interview_service.evaluate_and_advance(
            db, session, user, question=question, answer=answer
        )

        if turn.decision == TurnDecision.FOLLOWUP:
            await channel.send(
                {
                    "type": "followup_triggered",
                    "questionId": str(question.id),
                    "reason": turn.guardrail_reason,
                }
            )

        if next_question is None:
            await _end_and_notify(channel, db, session, reason="completed")
            return False

        await channel.send({"type": "turn_state_changed", "state": "AI_SPEAKING"})
        await _send_question(channel, session, next_question, elapsed=elapsed_seconds(), total_seconds=total_seconds
        )

    elif event_type == "barge_in":
        if not interview_ws_registry.allow_event(str(session.id)):
            return True  # Section 12.1A: quietly drop events past the low-cost-spam threshold
        question = _find_question(session, message.get("questionId"))
        if question is not None:
            # Records only the interruption offset. Phase 2 reused
            # mark_question_asked here, which also re-stamped `asked_at`;
            # in Phase 3 `asked_at` is set at delivery time and carries
            # the "already delivered" meaning, so re-stamping it on every
            # barge-in would muddy that.
            interview_service.record_barge_in(
                db, question, char_offset=message.get("charOffset")
            )

    elif event_type == "prosody_update":
        # Section 9.7's audio-derived signals. They are measured in the
        # browser because audio never leaves it (Phase 2's decision), and
        # they arrive as a *running aggregate* on every turn rather than
        # once at the end.
        #
        # That timing is the whole point. The end of an interview is
        # server-decided: `completed` and `time_up` both close this socket
        # from our side and schedule report generation in the same breath
        # (see `_end_and_notify`). A client that waited for `session_ended`
        # before submitting would always lose that race, and every report
        # would score confidence as unmeasured. Re-sending the aggregate
        # each turn means the row is already current whenever the session
        # happens to end, and whoever ended it.
        if not prosody_service.accepts_prosody(session):
            # A signed interview has no audio. A client sending this is
            # confused rather than hostile, so it is dropped quietly.
            return True
        if not interview_ws_registry.allow_event(str(session.id)):
            return True  # Section 12.1A: same low-cost-event budget as barge_in
        try:
            payload = ProsodySignalIn.model_validate(message.get("prosody") or {})
        except ValidationError:
            # Out-of-range or malformed client measurements are dropped --
            # not stored, and not fatal. One bad frame out of the browser's
            # analyser must not take down a live interview.
            logger.warning("Discarded a malformed prosody_update [session_id=%s]", session.id)
            return True
        prosody_service.submit_prosody(db, session, payload)

    elif event_type == "expression_update":
        # Section 9.7's video-derived signals, on the same running-aggregate
        # footing as `prosody_update` above and for the same reason: the
        # server decides when an interview ends and starts scoring
        # immediately, so the row has to already be current.
        #
        # The frame itself never crosses this socket. MediaPipe reduces it to
        # landmarks in the browser, `lib/expressionMetrics.ts` reduces those
        # to three scores, and only the scores arrive here. There is
        # deliberately no message on this protocol that can carry a video
        # frame or a landmark set.
        if not interview_ws_registry.allow_event(str(session.id)):
            return True  # Section 12.1A: same low-cost-event budget as barge_in
        try:
            expression = ExpressionSignalIn.model_validate(message.get("expression") or {})
        except ValidationError:
            logger.warning("Discarded a malformed expression_update [session_id=%s]", session.id)
            return True
        expression_service.submit_expression(db, session, expression)

    elif event_type == "code_panel_update":
        # Section 9.9's `code_panel_update`. Debounced client-side to every
        # 1-2s of inactivity rather than sent per keystroke, so a candidate
        # typing quickly does not flood the control channel that the same
        # socket uses for turn-taking.
        #
        # Held in memory for the connection rather than written per update:
        # Section 8 stores the snapshot on `interview_answers`, meaning what
        # matters is the content at the moment an answer was given, not every
        # intermediate keystroke. Writing each update would be a row-rewrite
        # per second for a field nothing reads until submit.
        if not interview_ws_registry.allow_event(str(session.id)):
            return True  # Section 12.1A: same low-cost-event budget as barge_in
        shared = message.get("shared")
        code = message.get("code")
        # `shared: false` means the candidate turned the toggle off, and the
        # panel's content must stop reaching the engine from that point --
        # cleared rather than merely not updated, so an earlier snapshot
        # cannot linger in a later turn's context.
        state.set_panel(
            strip_unstorable(str(code))[:20_000] if shared and isinstance(code, str) else None
        )

    elif event_type == "heartbeat":
        elapsed = (utcnow() - session.started_at).total_seconds()
        await channel.send({"type": "timer_sync", "elapsedSeconds": elapsed, "totalSeconds": total_seconds})

    elif event_type == "pause_requested":
        await channel.send({"type": "session_paused"})

    elif event_type == "resume_requested":
        await channel.send({"type": "session_resumed"})

    elif event_type == "end_requested":
        await _end_and_notify(channel, db, session, reason="ended_by_candidate")
        return False

    else:
        await channel.send(
            {"type": "error", "code": "unknown_event", "message": f"Unknown event type: {event_type!r}"}
        )

    return True

def _find_question(session, question_id: str | None):
    if question_id is None:
        return None
    return next((q for q in session.questions if str(q.id) == question_id), None)


async def _end_and_notify(channel: ClientChannel, db: Session, session, *, reason: str) -> None:
    session.status = SessionStatus.COMPLETED
    session.ended_at = utcnow()
    db.commit()
    # Bring the prosody row's transcript-derived figures up to the final
    # transcript before anything reads them. In-session updates land ahead of
    # each answer, so without this the stored pace and filler count would be
    # missing the last answer the candidate gave.
    prosody_service.refresh_derived(db, session.id)
    # Feedback generation starts here rather than in the frontend, so a
    # candidate who closes the tab the moment the interview ends still has a
    # report waiting when they come back (Section 4.10).
    feedback_generator.schedule_generation(session.id)
    await channel.send({"type": "session_ended", "reason": reason})
    await channel.close()
