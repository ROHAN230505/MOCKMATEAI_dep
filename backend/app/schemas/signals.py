"""
Multimodal signal schemas (Section 9.7, Phase 5).

Only the two genuinely audio-derived measures are accepted from the client.
Speaking pace and filler-word count are *not* in the request body even though
`prosody_signals` stores them, because the backend already derives both from the
transcript and the answer timings it holds (see
`services/feedback/transcript_signals.py`). Accepting them over the wire would
create a second source of truth for a number the server can compute itself, and
would let a client inflate its own score.
"""
from pydantic import Field

from app.schemas.common import CamelModel


class ProsodySignalIn(CamelModel):
    """
    What the browser's audio analyser measured over the session.

    Both fields are optional: a session where the microphone was muted for the
    whole interview genuinely has no pitch or pause data, and that must stay
    absent rather than arriving as a zero.
    """

    # 0-100. Spread of fundamental frequency across voiced frames, normalised —
    # low is monotone, high is expressive (Section 9.7).
    pitch_variance_score: float | None = Field(default=None, ge=0, le=100)
    # Mean length of a silent run between utterances, in milliseconds.
    avg_pause_duration_ms: float | None = Field(default=None, ge=0, le=60_000)
    # How much voiced audio the measurement is based on. The server rejects
    # samples too short to mean anything rather than storing a number derived
    # from two seconds of speech.
    voiced_seconds: float = Field(ge=0, le=36_000)


class ProsodySignalOut(CamelModel):
    session_id: str
    avg_pace_wpm: float | None = None
    filler_word_count: int | None = None
    pitch_variance_score: float | None = None
    avg_pause_duration_ms: float | None = None



class ExpressionSignalIn(CamelModel):
    """
    What the browser's face analyser measured over the session (Phase 5B).

    Every field here is client-derived, with no server-side equivalent to check
    it against — unlike prosody, where the server independently computes half the
    row from the transcript. That makes this the widest trust boundary in the
    product, so the bounds below are not decoration: they are the only thing
    between a crafted request and a perfect body-language score.

    All three signals are optional. A session where the camera was covered, the
    model never loaded, or the candidate sat outside frame genuinely has no
    expression data, and that must arrive as absent rather than as zero.
    """

    # Share of judgeable time spent looking at the interviewer (Section 9.7).
    eye_contact_percentage: float | None = Field(default=None, ge=0, le=100)
    # 0-100, from smile *events* per minute rather than time spent smiling.
    smile_frequency_score: float | None = Field(default=None, ge=0, le=100)
    # Sustained posture deviations. Capped well below anything meaningful: past a
    # couple of dozen the count says nothing the first few did not.
    posture_flag_count: int | None = Field(default=None, ge=0, le=100)
    # Coverage. How much video was analysed, and how much of it held a face —
    # the two figures that decide whether the three above are a measurement.
    analysed_seconds: float = Field(ge=0, le=36_000)
    face_detected_seconds: float = Field(ge=0, le=36_000)


class ExpressionSignalOut(CamelModel):
    session_id: str
    eye_contact_percentage: float | None = None
    smile_frequency_score: float | None = None
    posture_flag_count: int | None = None
