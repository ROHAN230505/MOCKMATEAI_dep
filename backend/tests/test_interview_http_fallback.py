"""
Section 6.6's HTTP fallback transport.

The point of these tests is not that the endpoint responds — it is that the
fallback is the *same* turn loop. A second implementation of the interview rules
that drifts from the first would be worse than no fallback at all, so the
central test here runs one interview over the socket and one over HTTP and
compares the two event streams.
"""
import uuid

from app.models.interview import InterviewAnswer, InterviewQuestion


def _signup_and_login(client, email="fallback@example.com"):
    client.post(
        "/api/v1/auth/signup",
        json={"name": "Ada Candidate", "email": email, "password": "Str0ng!Pass"},
    )
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "Str0ng!Pass"})
    return resp.json()["data"]["accessToken"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _start(client, token, **overrides):
    body = {
        "role": "SDE",
        "type": "behavioral",
        "durationMinutes": 15,
        "mode": "voice",
        "consentGiven": True,
    }
    body.update(overrides)
    resp = client.post("/api/v1/interviews/start", json=body, headers=_headers(token))
    return resp.json()["data"]["sessionId"]


def _post_events(client, token, session_id, events):
    resp = client.post(
        f"/api/v1/interviews/{session_id}/events",
        json={"events": events},
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _types(events):
    return [e["type"] for e in events]


def _answer_event(question_id, text="A real answer."):
    return {
        "type": "submit_answer",
        "questionId": question_id,
        "transcriptText": text,
        "isSkipped": False,
    }

def _read_ws_turn(ws, collected):
    """
    Reads a socket up to the end of one turn.

    Stopping at `question_asked` is not the end of the turn: `_send_question`
    always emits `timer_sync` straight after it, so a reader that breaks on the
    question leaves that event unread and makes the two transports look
    different when they are not.
    """
    for _ in range(10):
        event = ws.receive_json()
        collected.append(event)
        if event["type"] == "session_ended":
            return
        if event["type"] == "question_asked":
            collected.append(ws.receive_json())  # the paired timer_sync
            return
    raise AssertionError("no question or ending arrived")



def test_an_interview_runs_end_to_end_without_a_websocket(client):
    """The whole point: a candidate on a network that blocks WS still interviews."""
    token = _signup_and_login(client)
    session_id = _start(client, token)

    opened = _post_events(client, token, session_id, [{"type": "client_ready"}])
    assert "question_asked" in _types(opened["events"])
    assert opened["ended"] is False
    question = next(e for e in opened["events"] if e["type"] == "question_asked")

    turn = _post_events(client, token, session_id, [_answer_event(question["questionId"])])
    assert {"question_asked", "session_ended"} & set(_types(turn["events"]))

    ended = _post_events(client, token, session_id, [{"type": "end_requested"}])
    assert "session_ended" in _types(ended["events"])
    # `ended` carries here what `close()` carries on a socket.
    assert ended["ended"] is True


def test_both_transports_produce_the_same_event_stream(client):
    """
    One interview over the socket, one over HTTP, same inputs — same events.

    This is the test that would catch the fallback drifting into a second
    implementation of the turn loop, which is the failure that would actually
    hurt: a candidate forced onto HTTP getting a subtly different interview.
    """
    token = _signup_and_login(client)

    ws_session = _start(client, token)
    ws_events = []
    with client.websocket_connect(f"/api/v1/interviews/{ws_session}/live?token={token}") as ws:
        _read_ws_turn(ws, ws_events)
        question_id = next(e for e in ws_events if e["type"] == "question_asked")["questionId"]
        ws.send_json(_answer_event(question_id))
        _read_ws_turn(ws, ws_events)

    http_session = _start(client, token)
    opened = _post_events(client, token, http_session, [{"type": "client_ready"}])
    http_events = list(opened["events"])
    question_id = next(e for e in http_events if e["type"] == "question_asked")["questionId"]
    http_events += _post_events(client, token, http_session, [_answer_event(question_id)])["events"]

    assert _types(http_events) == _types(ws_events)


def test_shared_code_survives_between_requests(client):
    """
    The panel is shared on one request and the answer submitted on a later one.

    Over a socket the snapshot lives on the connection; over HTTP there is no
    connection, so this is the case a request-scoped variable would get wrong —
    silently, by dropping the candidate's code from the turn it belonged to.
    """
    from app.database import SessionLocal

    token = _signup_and_login(client)
    session_id = _start(client, token, type="technical")

    opened = _post_events(client, token, session_id, [{"type": "client_ready"}])
    question = next(e for e in opened["events"] if e["type"] == "question_asked")

    _post_events(
        client,
        token,
        session_id,
        [{"type": "code_panel_update", "shared": True, "code": "def solve(nums):\n    pass"}],
    )
    _post_events(client, token, session_id, [_answer_event(question["questionId"])])

    with SessionLocal() as db:
        answer = (
            db.query(InterviewAnswer)
            .join(InterviewQuestion, InterviewQuestion.id == InterviewAnswer.question_id)
            .filter(InterviewQuestion.session_id == uuid.UUID(session_id))
            .first()
        )
        assert answer is not None
        assert "def solve" in (answer.code_panel_snapshot or "")


def test_http_is_refused_while_a_socket_holds_the_session(client):
    """
    Section 12.1A's one-connection rule, on a transport with no connection.

    Without this the same interview could be driven from a socket and from HTTP
    at once, and the two clients would interleave turns.
    """
    token = _signup_and_login(client)
    session_id = _start(client, token)

    with client.websocket_connect(f"/api/v1/interviews/{session_id}/live?token={token}") as ws:
        ws.receive_json()
        resp = client.post(
            f"/api/v1/interviews/{session_id}/events",
            json={"events": [{"type": "client_ready"}]},
            headers=_headers(token),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "duplicate_connection"


def test_a_finished_interview_refuses_more_events(client):
    token = _signup_and_login(client)
    session_id = _start(client, token)
    _post_events(client, token, session_id, [{"type": "client_ready"}])
    _post_events(client, token, session_id, [{"type": "end_requested"}])

    resp = client.post(
        f"/api/v1/interviews/{session_id}/events",
        json={"events": [{"type": "heartbeat"}]},
        headers=_headers(token),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "session_not_active"


def test_another_users_session_is_not_reachable(client):
    token = _signup_and_login(client)
    session_id = _start(client, token)
    intruder = _signup_and_login(client, email="intruder@example.com")

    resp = client.post(
        f"/api/v1/interviews/{session_id}/events",
        json={"events": [{"type": "client_ready"}]},
        headers=_headers(intruder),
    )
    assert resp.status_code in (403, 404)


def test_an_oversized_batch_is_rejected(client):
    """A turn is a handful of events; hundreds is broken or probing."""
    token = _signup_and_login(client)
    session_id = _start(client, token)
    resp = client.post(
        f"/api/v1/interviews/{session_id}/events",
        json={"events": [{"type": "heartbeat"}] * 64},
        headers=_headers(token),
    )
    assert resp.status_code == 422


def test_an_unknown_event_is_reported_but_not_fatal(client):
    token = _signup_and_login(client)
    session_id = _start(client, token)
    _post_events(client, token, session_id, [{"type": "client_ready"}])
    data = _post_events(client, token, session_id, [{"type": "nonsense"}, {"type": "heartbeat"}])
    assert "error" in _types(data["events"])
    # The batch continues: one bad event must not cost the candidate their turn.
    assert "timer_sync" in _types(data["events"])
    assert data["ended"] is False


def test_the_transport_actually_used_is_recorded(client, db_session):
    """
    Section 6.6 asks which rung a session ran on. A session driven over HTTP must
    not keep reporting the mode it was optimistically assigned at start.
    """
    from app.models.enums import TransportMode
    from app.models.interview import InterviewSession

    token = _signup_and_login(client)
    session_id = _start(client, token)

    started = db_session.get(InterviewSession, uuid.UUID(session_id))
    assert started.transport_mode is TransportMode.BROWSER_NATIVE_SPEECH

    _post_events(client, token, session_id, [{"type": "client_ready"}])

    db_session.expire_all()
    switched = db_session.get(InterviewSession, uuid.UUID(session_id))
    assert switched.transport_mode is TransportMode.AUDIO_ONLY_HTTP
