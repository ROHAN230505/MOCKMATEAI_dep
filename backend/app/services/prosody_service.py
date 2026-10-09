"""
Voice Prosody Service (Section 9.7, Phase 5).

## Where the analysis happens, and why

Section 9.7 asks for speaking pace, filler-word frequency, pitch variance and
pause patterns. The four do not come from the same place, and this service is
built around that split:

| Signal          | Derived from            | Computed by |
|-----------------|-------------------------|-------------|
| Filler words    | transcript              | server      |
| Speaking pace   | transcript + timings    | server      |
| Pitch variance  | the audio waveform      | browser     |
| Pause patterns  | the audio waveform      | browser     |

The last two need the waveform, and Phase 2 established that audio never leaves
the browser — speech recognition runs client-side and nothing is uploaded. Rather
than reverse that decision (and take on the privacy surface of streaming a
candidate's voice to a server), the analysis runs in the browser and only the two
aggregate numbers are submitted. No audio, no frames, just two floats.

The first two are computed here, from data the server already holds. That keeps a
single source of truth: the filler count in `prosody_signals` and the one in the
feedback report are the same number by construction, not by agreement.

## Trust

The two client-supplied values are treated exactly as Section 12.8 treats model
output: clamped, never trusted. A crafted request could otherwise post a perfect
pitch-variance score and inflate its own confidence rating. The Pydantic schema
bounds the ranges, and `submit_prosody` additionally refuses samples with too
little voiced audio to be meaningful — a number from three seconds of speech is
noise wearing a measurement's clothes.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import InterviewMode
from app.models.interview import InterviewSession
from app.models.signals import ProsodySignal
from app.schemas.signals import ProsodySignalIn
from app.services.feedback.scoring import load_turns
from app.services.feedback.transcript_signals import extract_signals

logger = logging.getLogger("mockmateai.prosody")


# Below this much voiced audio the pitch and pause figures are not measurements,
# they are artefacts of a tiny sample. Roughly one substantive spoken answer.
MIN_VOICED_SECONDS = 12.0


def _transcript_derived(db: Session, session_id) -> tuple[float | None, int | None]:
    """
    Speaking pace and filler count, from the transcript the server already has.

    Returns (avg_pace_wpm, filler_word_count). Pace is None unless the client
    supplied real per-answer timings — Phase 4 established that an untimed
    session has no pace, and estimating one from word counts alone would be
    inventing a measurement.
    """
    turns = load_turns(db, session_id)
    signals = extract_signals(
        [
            {
                "text": turn.transcript_text,
                "is_skipped": turn.is_skipped,
                "started_at": turn.answer_started_at,
                "ended_at": turn.answer_ended_at,
            }
            for turn in turns
        ]
    )

    if signals.answer_count == 0:
        return None, None
    return signals.speaking_pace_wpm, signals.filler_count


def accepts_prosody(session: InterviewSession) -> bool:
    """
    Whether this session could have prosody at all.

    A signed interview has no audio track, so every field in `prosody_signals`
    would be describing something that was never recorded. Refusing the write is
    the honest outcome: `confidence` then reports as unmeasured with a reason,
    rather than resting on a row a client fabricated or filled with zeroes.
    """
    return session.mode is not InterviewMode.SIGN


def submit_prosody(db: Session, session: InterviewSession, payload: ProsodySignalIn) -> ProsodySignal:
    """
    Record the session's prosody, upserting on `session_id`.

    Upsert rather than insert because `prosody_signals.session_id` is unique and
    a client may submit more than once — a retry after a dropped request must not
    fail, and a resubmission should replace rather than duplicate.

    Once this row exists, Phase 4's `compute_breakdown` starts scoring the
    confidence category with no change to the scoring code. That handoff is the
    contract `test_phase5_signal_rows_are_picked_up_without_code_changes` was
    written to protect.
    """
    enough_audio = payload.voiced_seconds >= MIN_VOICED_SECONDS

    pitch = payload.pitch_variance_score if enough_audio else None
    pause = payload.avg_pause_duration_ms if enough_audio else None

    if not enough_audio:
        logger.info(
            "Prosody sample too short to measure [session_id=%s voiced=%.1fs min=%.1fs]",
            session.id,
            payload.voiced_seconds,
            MIN_VOICED_SECONDS,
        )

    pace, fillers = _transcript_derived(db, session.id)

    row = db.scalars(select(ProsodySignal).where(ProsodySignal.session_id == session.id)).first()
    if row is None:
        row = ProsodySignal(session_id=session.id)
        db.add(row)

    row.pitch_variance_score = pitch
    row.avg_pause_duration_ms = pause
    row.avg_pace_wpm = pace
    row.filler_word_count = fillers

    db.commit()
    db.refresh(row)
    return row


def refresh_derived(db: Session, session_id) -> ProsodySignal | None:
    """
    Recompute the transcript-derived half against the finished transcript.

    In-session updates arrive over the WebSocket *before* each answer is
    submitted, so while an interview is running the row's pace and filler count
    always trail the transcript by one turn. Called once the session ends, this
    makes them exact: the stored figures then describe the whole session rather
    than all of it but the last answer.

    A no-op when no prosody was recorded — an absent row stays absent rather
    than being conjured into existence with half its columns NULL.
    """
    row = get_prosody(db, session_id)
    if row is None:
        return None

    pace, fillers = _transcript_derived(db, session_id)
    row.avg_pace_wpm = pace
    row.filler_word_count = fillers
    db.commit()
    db.refresh(row)
    return row


def get_prosody(db: Session, session_id) -> ProsodySignal | None:
    return db.scalars(select(ProsodySignal).where(ProsodySignal.session_id == session_id)).first()
