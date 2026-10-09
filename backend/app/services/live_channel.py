"""
Transport abstraction for the live interview turn loop (Section 6.6).

Section 6.6 specifies a fallback ladder ending in `audio_only_http`. The rungs
above it describe relaying *media* to the server, which this build has no use
for: ASR and TTS run in the browser (the Phase 2 decision), so audio never
crosses the wire and there is nothing for a TURN server to relay. What the
ladder is actually protecting against still applies, though — a network that
refuses WebSockets. Corporate proxies do this routinely, and until now such a
network ended the interview after Section 5.6's thirty seconds of retries.

So the bottom rung is the one that means something here, and it is a text
transport rather than an audio one: the same turn loop, driven over ordinary
HTTP requests.

The loop is request-driven end to end — every server event is produced in
response to a client event or at session open, and nothing is ever pushed
spontaneously — which is why plain request/response is sufficient and no
long-polling or SSE channel is needed.
"""
from typing import Protocol


class ClientChannel(Protocol):
    """Where the turn loop writes events, whatever is carrying them."""

    async def send(self, event: dict) -> None: ...

    async def close(self) -> None: ...


class WebSocketChannel:
    """The primary transport: events go out as they are produced."""

    def __init__(self, websocket) -> None:
        self._websocket = websocket

    async def send(self, event: dict) -> None:
        await self._websocket.send_json(event)

    async def close(self) -> None:
        await self._websocket.close()


class BufferChannel:
    """
    The HTTP fallback: events accumulate and are returned as one response body.

    `closed` carries what `WebSocket.close()` carries on the other transport —
    the session is over and the client should stop sending. It is reported in
    the response rather than by dropping the connection, since there is no
    connection to drop.
    """

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.closed = False

    async def send(self, event: dict) -> None:
        self.events.append(event)

    async def close(self) -> None:
        self.closed = True
