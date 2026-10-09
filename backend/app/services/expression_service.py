"""
Expression Signal Service (Section 9.7, Phase 5B).

## Where the analysis happens, and why

Eye contact, smile frequency and posture all need the video frame, and the frame
never leaves the browser — the same decision Phase 2 made for audio, applied to
something even more sensitive. MediaPipe's Face Landmarker runs client-side
against the candidate's own camera preview, and what arrives here is three
aggregate scores plus two coverage figures. No frames, no landmarks, no
biometric template, nothing from which a face could be reconstructed.

## Trust

This is the widest trust boundary in the product, and worth being explicit about.
Prosody has a check on it: the server independently derives half that row from
the transcript, so a client lying about pitch cannot also lie about filler words.
Expression has no such anchor — there is no server-side view of the video, so
every number in this table originates outside the server and is only as
trustworthy as the client that sent it.

Three things follow, and all three are deliberate:

1. The Pydantic schema bounds every field. A crafted request cannot post 100000%
   eye contact, and `scoring.py` clamps again when it reads the row.
2. The coverage figures are submitted *alongside* the scores and checked here.
   A client claiming 95% eye contact over four seconds of video is not making a
   measurement, and is refused.
3. Body language carries the smallest weight of Section 10.2's four categories
   (0.15), so even a client that lies successfully moves the overall readiness
   score less than lying about anything else would.

## Absence is not zero

`MIN_ANALYSED_SECONDS` and `MIN_FACE_COVERAGE` mirror the client-side gates in
`lib/expressionMetrics.ts` rather than trusting the client to have applied them.
When they fail, the three scores are stored as NULL and `scoring.py` reports body
language as unmeasured — which is what a covered camera, a lens pointed at the
ceiling, or a model that never loaded actually means.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interview import InterviewSession
from app.models.signals import ExpressionSignal
from app.schemas.signals import ExpressionSignalIn

logger = logging.getLogger("mockmateai.expression")


# Under half a minute of analysed video there is a sample, not a measurement.
MIN_ANALYSED_SECONDS = 30.0

# Below this share of analysed time containing a face, "no face" has stopped
# being evidence about the candidate and become evidence about the room — a dark
# office, a covered lens, a laptop lid half closed. Those are indistinguishable
# from someone sitting outside frame, so nothing is reported.
MIN_FACE_COVERAGE = 0.25


def _is_measurable(payload: ExpressionSignalIn) -> tuple[bool, str | None]:
    """Whether the submitted coverage supports reporting the scores at all."""
    if payload.analysed_seconds < MIN_ANALYSED_SECONDS:
        return False, f"only {payload.analysed_seconds:.1f}s of video analysed"
    if payload.face_detected_seconds > payload.analysed_seconds:
        # Impossible, so the client is confused or hostile; either way the
        # coverage figures cannot be used to validate anything.
        return False, "face-detected time exceeds analysed time"
    coverage = payload.face_detected_seconds / payload.analysed_seconds
    if coverage < MIN_FACE_COVERAGE:
        return False, f"a face was visible in only {coverage * 100:.0f}% of the video"
    return True, None


def submit_expression(
    db: Session, session: InterviewSession, payload: ExpressionSignalIn
) -> ExpressionSignal:
    """
    Record the session's expression signals, upserting on `session_id`.

    Upsert for the same reason prosody upserts: the client sends a running
    aggregate on every turn, so a resubmission must replace rather than duplicate,
    and a retry after a dropped frame must not fail.
    """
    measurable, why_not = _is_measurable(payload)

    if not measurable:
        logger.info(
            "Expression signals not measurable [session_id=%s reason=%s]", session.id, why_not
        )

    row = db.scalars(
        select(ExpressionSignal).where(ExpressionSignal.session_id == session.id)
    ).first()
    if row is None:
        row = ExpressionSignal(session_id=session.id)
        db.add(row)

    # Written as a set, not merged: a later aggregate supersedes an earlier one,
    # and a session that stops being measurable (the camera was covered halfway
    # through, dragging coverage under the floor) must lose its earlier scores
    # rather than keep stale ones that no longer describe the session.
    row.eye_contact_percentage = payload.eye_contact_percentage if measurable else None
    row.smile_frequency_score = payload.smile_frequency_score if measurable else None
    row.posture_flag_count = payload.posture_flag_count if measurable else None

    db.commit()
    db.refresh(row)
    return row


def get_expression(db: Session, session_id) -> ExpressionSignal | None:
    return db.scalars(
        select(ExpressionSignal).where(ExpressionSignal.session_id == session_id)
    ).first()
