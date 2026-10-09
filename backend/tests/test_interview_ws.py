"""
Integration tests for the live interview WebSocket protocol (Section 7.3).

Covers the full loop end-to-end: engine-generated question delivery, answer
submission, follow-up insertion, barge-in logging, skip handling, and each of
the three ways a session ends.

Tests read the stream with `_recv_until` rather than asserting an exact event
sequence. The protocol is additive by design (Phase 3 added
`turn_state_changed` and `followup_triggered` without renaming anything), so
pinning the precise interleaving would make every future additive event a
test failure while proving nothing extra about the behavior under test.
"""
import pytest
from starlette.websockets import WebSocketDisconnect


def _signup_and_login(client, email="candidate@example.com"):
    client.post("/api/v1/auth/signup", json={"name": "Ada Candidate", "email": email, "password": "Str0ng!Pass"})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "Str0ng!Pass"})
    return resp.json()["data"]["accessToken"]


def _start_session(client, token, **overrides):
    body = {"role": "SDE", "type": "behavioral", "durationMinutes": 15, "mode": "voice", "consentGiven": True}
    body.update(overrides)
    resp = client.post(
        "/api/v1/interviews/start", json=body, headers={"Authorization": f"Bearer {token}"}
    )
    return resp.json()["data"]["sessionId"]


def _ws_url(session_id, token):
    return f"/api/v1/interviews/{session_id}/live?token={token}"


def _recv_until(ws, *wanted_types, max_events=25):
    """
    Reads events until one of `wanted_types` arrives, returning it.
    Collected intermediate events are attached as `._skipped` so a test can
    still assert on them when they're the point (see the EVALUATING test).
    """
    skipped = []
    for _ in range(max_events):
        event = ws.receive_json()
        if event.get("type") in wanted_types:
            event["_skipped"] = skipped
            return event
        skipped.append(event)
    raise AssertionError(f"None of {wanted_types} arrived within {max_events} events. Saw: {skipped}")


def _answer(ws, question_id, text="A thoughtful answer.", *, skipped=False):
    ws.send_json(
        {
            "type": "submit_answer",
            "questionId": question_id,
            "transcriptText": None if skipped else text,
            "isSkipped": skipped,
            "asrConfidenceAvg": None if skipped else 0.9,
            "answerStartedAt": None,
            "answerEndedAt": None,
        }
    )


# A deliberately strong answer: concrete tech, STAR structure, and a number.
# The mock adapter's rubric scores this in the "follow-up disallowed" band
# (Section 10.3), so the interview advances one planned question per answer
# and the flow is deterministic.
STRONG_ANSWER = (
    "The situation was that our Django and Postgres reporting job took 40 seconds. "
    "So I added a Redis cache and a composite index, and as a result latency dropped "
    "to 3 seconds across 12000 records."
)


def test_full_interview_flow_completes_all_questions(client):
    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        seen_questions = []
        for _ in range(3):
            question = _recv_until(ws, "question_asked", "session_ended")
            if question["type"] == "session_ended":
                break
            seen_questions.append(question["questionId"])
            assert question["questionText"].strip()
            assert question["totalQuestions"] >= 3
            _answer(ws, question["questionId"], STRONG_ANSWER)

        end = _recv_until(ws, "session_ended")
        assert end["reason"] == "completed"
        assert len(set(seen_questions)) == 3

    detail = client.get(f"/api/v1/interviews/{session_id}", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    assert detail["status"] == "completed"
    answered = [q for q in detail["questions"] if q["answer"] is not None]
    assert len(answered) == 3
    assert all(q["answer"]["transcriptText"] == STRONG_ANSWER for q in answered)


def test_evaluating_turn_state_is_emitted_before_each_question(client):
    """Section 10.1's EVALUATING state is now server-owned (Phase 3) and must reach the client."""
    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        first = _recv_until(ws, "question_asked")
        states = [e for e in first["_skipped"] if e.get("type") == "turn_state_changed"]
        assert {"EVALUATING", "AI_SPEAKING"} <= {e["state"] for e in states}

        _answer(ws, first["questionId"], STRONG_ANSWER)
        second = _recv_until(ws, "question_asked", "session_ended")
        if second["type"] == "question_asked":
            evaluating = [
                e for e in second["_skipped"]
                if e.get("type") == "turn_state_changed" and e["state"] == "EVALUATING"
            ]
            assert evaluating, "EVALUATING must be sent while the answer is being evaluated"

        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")


def test_weak_answer_triggers_followup(client):
    """
    Section 10.3's mandatory band: a vague answer scoring below 5 must produce
    a follow-up question rather than advancing to the next planned topic.
    """
    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        first = _recv_until(ws, "question_asked")
        assert first["isFollowup"] is False

        _answer(ws, first["questionId"], "I am a hard worker and a team player.")
        nxt = _recv_until(ws, "question_asked")

        assert nxt["isFollowup"] is True
        assert nxt["questionType"] == "followup"
        followup_events = [e for e in nxt["_skipped"] if e.get("type") == "followup_triggered"]
        assert followup_events, "a followup_triggered event should accompany the probe"
        assert "mandatory" in followup_events[0]["reason"].lower()

        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    detail = client.get(f"/api/v1/interviews/{session_id}", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    followups = [q for q in detail["questions"] if q["questionType"] == "followup"]
    assert len(followups) == 1
    # Section 8: follow-ups hang off the original planned question.
    assert followups[0]["parentQuestionId"] == first["questionId"]


def test_followup_cap_stops_after_two_consecutive(client):
    """Section 10.3: "no more than 2 consecutive follow-ups on the same original question"."""
    token = _signup_and_login(client)
    session_id = _start_session(client, token)
    vague = "I am a hard worker."

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        current = _recv_until(ws, "question_asked")
        root_id = current["questionId"]

        followup_count = 0
        for _ in range(5):
            _answer(ws, current["questionId"], vague)
            current = _recv_until(ws, "question_asked", "session_ended")
            if current["type"] == "session_ended":
                break
            if current["isFollowup"]:
                followup_count += 1
            else:
                break  # cap forced a move to the next planned question

        assert followup_count == 2, f"expected the cap to stop at 2 follow-ups, got {followup_count}"

        if current["type"] != "session_ended":
            ws.send_json({"type": "end_requested"})
            _recv_until(ws, "session_ended")

    detail = client.get(f"/api/v1/interviews/{session_id}", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    chained = [q for q in detail["questions"] if q["parentQuestionId"] == root_id]
    assert len(chained) == 2


def test_spoken_skip_phrase_is_recorded_as_skip(client):
    """
    Section 4.8 / 9.3: a spoken pass-phrase produces the same distinct
    `is_skipped` outcome as the Skip button, not a low-scored weak answer.
    """
    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        first = _recv_until(ws, "question_asked")
        _answer(ws, first["questionId"], "Honestly I don't know, can we skip this one?")
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    detail = client.get(f"/api/v1/interviews/{session_id}", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    skipped = next(q for q in detail["questions"] if q["id"] == first["questionId"])
    assert skipped["answer"]["isSkipped"] is True
    # Section 9.3: a skip must NOT carry scores — never a scored zero.
    assert skipped["evaluation"] is not None
    assert skipped["evaluation"]["relevanceScore"] is None
    assert skipped["evaluation"]["completenessScore"] is None
    assert skipped["evaluation"]["followupTriggered"] is False


def test_skip_is_recorded_distinctly(client):
    """The explicit Skip control (Section 4.8) — no LLM call, no scores."""
    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        first = _recv_until(ws, "question_asked")
        _answer(ws, first["questionId"], skipped=True)
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    detail = client.get(f"/api/v1/interviews/{session_id}", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    skipped_question = next(q for q in detail["questions"] if q["id"] == first["questionId"])
    assert skipped_question["answer"]["isSkipped"] is True
    assert skipped_question["answer"]["transcriptText"] is None


def test_evaluations_are_persisted_for_scored_answers(client):
    """Section 9.3: internal_evaluation lands in answer_evaluations for reuse by Phase 4."""
    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        first = _recv_until(ws, "question_asked")
        _answer(ws, first["questionId"], STRONG_ANSWER)
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    detail = client.get(f"/api/v1/interviews/{session_id}", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    scored = next(q for q in detail["questions"] if q["id"] == first["questionId"])
    evaluation = scored["evaluation"]
    assert evaluation is not None
    assert 0 <= evaluation["relevanceScore"] <= 10
    assert 0 <= evaluation["completenessScore"] <= 10
    assert evaluation["followupReasonText"]


def test_token_usage_is_accounted_on_the_session(client):
    """Section 9.3A: per-session token/cost accounting on interview_sessions.total_tokens_used."""
    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        first = _recv_until(ws, "question_asked")
        _answer(ws, first["questionId"], STRONG_ANSWER)
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    detail = client.get(f"/api/v1/interviews/{session_id}", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    assert detail["totalTokensUsed"] > 0


def test_end_requested_ends_session_early(client):
    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        _recv_until(ws, "question_asked")
        ws.send_json({"type": "end_requested"})
        end = _recv_until(ws, "session_ended")
        assert end["reason"] == "ended_by_candidate"

    detail = client.get(f"/api/v1/interviews/{session_id}", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    assert detail["status"] == "completed"
    assert sum(1 for q in detail["questions"] if q["answer"] is not None) == 0


def test_barge_in_records_char_offset(client):
    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        first = _recv_until(ws, "question_asked")
        ws.send_json({"type": "barge_in", "questionId": first["questionId"], "charOffset": 12})
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    detail = client.get(f"/api/v1/interviews/{session_id}", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    question = next(q for q in detail["questions"] if q["id"] == first["questionId"])
    assert question["interruptedAtCharOffset"] == 12


def test_pause_and_resume_acks(client):
    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        _recv_until(ws, "question_asked")
        ws.send_json({"type": "pause_requested"})
        assert _recv_until(ws, "session_paused")["type"] == "session_paused"
        ws.send_json({"type": "resume_requested"})
        assert _recv_until(ws, "session_resumed")["type"] == "session_resumed"
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")


def test_duplicate_connection_rejected(client):
    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws1:
        _recv_until(ws1, "question_asked")

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(_ws_url(session_id, token)) as ws2:
                ws2.receive_json()


def test_connection_requires_valid_token(client):
    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(_ws_url(session_id, "not-a-real-token")) as ws:
            ws.receive_json()


def test_connection_blocks_other_users_session(client):
    token_a = _signup_and_login(client, email="a@example.com")
    token_b = _signup_and_login(client, email="b@example.com")
    session_id = _start_session(client, token_a)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(_ws_url(session_id, token_b)) as ws:
            ws.receive_json()


# ---------------------------------------------------------------------------
# Phase 5: prosody_update (Section 9.7)
# ---------------------------------------------------------------------------
def test_prosody_update_lands_before_the_session_ends(client, db_session):
    """
    The reason prosody comes over the socket at all: `_end_and_notify` schedules
    report generation in the same breath as it closes the connection, so a row
    written after `session_ended` arrives is too late to be scored. Sent
    in-session, it is already there.
    """
    from app.services.prosody_service import get_prosody

    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        first = _recv_until(ws, "question_asked")
        ws.send_json(
            {
                "type": "prosody_update",
                "prosody": {"pitchVarianceScore": 61.5, "avgPauseDurationMs": 380.0, "voicedSeconds": 40.0},
            }
        )
        _answer(ws, first["questionId"])
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    row = get_prosody(db_session, session_id)
    assert row is not None
    assert row.pitch_variance_score == pytest.approx(61.5)
    assert row.avg_pause_duration_ms == pytest.approx(380.0)
    # Derived server-side from the answer that was just submitted.
    assert row.filler_word_count is not None


def test_prosody_update_is_upserted_across_turns(client, db_session):
    from app.services.prosody_service import get_prosody

    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        question = _recv_until(ws, "question_asked")
        for value in (30.0, 55.0, 72.0):
            ws.send_json(
                {
                    "type": "prosody_update",
                    "prosody": {"pitchVarianceScore": value, "voicedSeconds": 60.0},
                }
            )
        _answer(ws, question["questionId"])
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    row = get_prosody(db_session, session_id)
    assert row.pitch_variance_score == pytest.approx(72.0)


def test_a_malformed_prosody_update_is_dropped_without_killing_the_interview(client, db_session):
    """
    An out-of-range measurement is a client bug, not a reason to end someone's
    interview. It is discarded and the loop carries on.
    """
    from app.services.prosody_service import get_prosody

    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        question = _recv_until(ws, "question_asked")
        ws.send_json({"type": "prosody_update", "prosody": {"pitchVarianceScore": 4000, "voicedSeconds": 60.0}})
        # The socket is still usable: the interview runs to a normal end.
        _answer(ws, question["questionId"])
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        assert _recv_until(ws, "session_ended")["type"] == "session_ended"

    assert get_prosody(db_session, session_id) is None


def test_prosody_update_reaches_the_generated_report(client, db_session):
    """
    End to end: an in-session prosody update turns Section 10.2's confidence
    category from unmeasured into a real score on the report the candidate reads.
    """
    from app.services.feedback.scoring import compute_breakdown

    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        question = _recv_until(ws, "question_asked")
        ws.send_json(
            {
                "type": "prosody_update",
                "prosody": {"pitchVarianceScore": 58.0, "avgPauseDurationMs": 430.0, "voicedSeconds": 55.0},
            }
        )
        _answer(ws, question["questionId"])
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    db_session.expire_all()
    breakdown = compute_breakdown(db_session, session_id)
    assert breakdown.confidence_score is not None
    assert "confidence" in breakdown.measured_categories


def test_the_final_answer_is_included_in_the_stored_transcript_figures(client, db_session):
    """
    Updates arrive ahead of each answer, so mid-interview the row's filler count
    is always one answer behind. `_end_and_notify` refreshes it against the
    finished transcript, which is why the stored number describes the whole
    session and not all of it but the last answer.
    """
    from app.services.prosody_service import get_prosody

    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        question = _recv_until(ws, "question_asked")
        # Sent before any answer exists: at this moment there is nothing to
        # derive, so the transcript half of the row is written as NULL.
        ws.send_json({"type": "prosody_update", "prosody": {"pitchVarianceScore": 50.0, "voicedSeconds": 45.0}})
        _answer(ws, question["questionId"], text="Um, basically I sort of handled it.")
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    row = get_prosody(db_session, session_id)
    assert row.filler_word_count == 3  # um, basically, sort of
    assert row.pitch_variance_score == pytest.approx(50.0)  # the audio half is untouched by the refresh


# ---------------------------------------------------------------------------
# Phase 5B: expression_update (Section 9.7)
# ---------------------------------------------------------------------------
EXPRESSION = {
    "eyeContactPercentage": 74.0,
    "smileFrequencyScore": 52.0,
    "postureFlagCount": 1,
    "analysedSeconds": 480.0,
    "faceDetectedSeconds": 440.0,
}


def test_expression_update_lands_before_the_session_ends(client, db_session):
    from app.services.expression_service import get_expression

    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        question = _recv_until(ws, "question_asked")
        ws.send_json({"type": "expression_update", "expression": EXPRESSION})
        _answer(ws, question["questionId"])
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    row = get_expression(db_session, session_id)
    assert row is not None
    assert row.eye_contact_percentage == pytest.approx(74.0)
    assert row.posture_flag_count == 1


def test_a_malformed_expression_update_is_dropped_without_killing_the_interview(client, db_session):
    from app.services.expression_service import get_expression

    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        question = _recv_until(ws, "question_asked")
        ws.send_json({"type": "expression_update", "expression": {**EXPRESSION, "eyeContactPercentage": 900}})
        _answer(ws, question["questionId"])
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        assert _recv_until(ws, "session_ended")["type"] == "session_ended"

    assert get_expression(db_session, session_id) is None


def test_both_signal_families_reach_the_report_together(client, db_session):
    """
    Phase 5 complete, end to end over the live protocol: all four of Section
    10.2's categories measured, and the weighted formula running at its full
    specified weights with nothing renormalised away.
    """
    from app.services.feedback.scoring import compute_breakdown

    token = _signup_and_login(client)
    session_id = _start_session(client, token)

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        question = _recv_until(ws, "question_asked")
        ws.send_json({
            "type": "prosody_update",
            "prosody": {"pitchVarianceScore": 63.0, "avgPauseDurationMs": 405.0, "voicedSeconds": 220.0},
        })
        ws.send_json({"type": "expression_update", "expression": EXPRESSION})
        _answer(ws, question["questionId"])
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    db_session.expire_all()
    breakdown = compute_breakdown(db_session, session_id)
    assert breakdown.unmeasured_categories == []
    assert breakdown.confidence_score is not None
    assert breakdown.body_language_score is not None
    assert breakdown.overall_readiness_score is not None


# ---------------------------------------------------------------------------
# Section 4.8B / 9.9: the mini code panel
# ---------------------------------------------------------------------------
def test_shared_code_travels_with_the_answer_it_was_on_screen_for(client, db_session):
    """
    Section 8 stores the snapshot on `interview_answers`, not as a running log:
    what matters is what was on screen when the answer was given, so the report
    can show it beside that answer.
    """
    from app.models.interview import InterviewAnswer, InterviewQuestion

    token = _signup_and_login(client)
    session_id = _start_session(client, token, type="technical")

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        question = _recv_until(ws, "question_asked")
        ws.send_json({
            "type": "code_panel_update",
            "shared": True,
            "code": "def solve(nums):\n    for a in nums:\n        for b in nums:\n            pass",
        })
        _answer(ws, question["questionId"])
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    answer = (
        db_session.query(InterviewAnswer)
        .join(InterviewQuestion, InterviewQuestion.id == InterviewAnswer.question_id)
        .filter(InterviewQuestion.session_id == session_id)
        .first()
    )
    assert answer is not None
    assert "def solve" in (answer.code_panel_snapshot or "")


def test_turning_sharing_off_clears_the_snapshot(client, db_session):
    """
    Not merely "stop updating". An earlier snapshot lingering into a later turn
    would mean the interviewer still sees code the candidate has withdrawn.
    """
    from app.models.interview import InterviewAnswer, InterviewQuestion

    token = _signup_and_login(client)
    session_id = _start_session(client, token, type="technical")

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        question = _recv_until(ws, "question_asked")
        ws.send_json({"type": "code_panel_update", "shared": True, "code": "secret_draft = 1"})
        ws.send_json({"type": "code_panel_update", "shared": False, "code": "secret_draft = 1"})
        _answer(ws, question["questionId"])
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        _recv_until(ws, "session_ended")

    answer = (
        db_session.query(InterviewAnswer)
        .join(InterviewQuestion, InterviewQuestion.id == InterviewAnswer.question_id)
        .filter(InterviewQuestion.session_id == session_id)
        .first()
    )
    assert answer.code_panel_snapshot is None


def test_a_malformed_code_panel_update_does_not_end_the_interview(client, db_session):
    token = _signup_and_login(client)
    session_id = _start_session(client, token, type="technical")

    with client.websocket_connect(_ws_url(session_id, token)) as ws:
        question = _recv_until(ws, "question_asked")
        ws.send_json({"type": "code_panel_update"})                      # no fields
        ws.send_json({"type": "code_panel_update", "shared": True, "code": 12345})  # wrong type
        _answer(ws, question["questionId"])
        _recv_until(ws, "question_asked", "session_ended")
        ws.send_json({"type": "end_requested"})
        assert _recv_until(ws, "session_ended")["type"] == "session_ended"


def test_shared_code_reaches_the_engine_as_fenced_data(client, db_session):
    """
    Section 12.8: the panel is candidate-controlled text, so it is fenced as data
    in the prompt exactly like the transcript. The engine has read this field
    since Phase 3 — only the column was never populated.
    """
    from app.services.llm_engine import EngineContext, build_conversation

    conversation = build_conversation(
        EngineContext(
            session_id="test-session",
            role_target="SDE",
            interview_type="technical",
            duration_minutes=15,
            current_question_text="What is the complexity?",
            current_answer_text="Two nested loops.",
            code_panel_snapshot="for a in nums:\n    for b in nums:\n        pass",
        )
    )
    rendered = " ".join(part["content"] for part in conversation)
    assert "<code_panel>" in rendered
    assert "for a in nums" in rendered
