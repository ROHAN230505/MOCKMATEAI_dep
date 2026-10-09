"""
Transcript-derived communication signals (Section 9.7's text-only subset).

Section 9.7 lists four prosody signals and is specific about where each comes
from: "speaking pace (words per minute), filler word frequency (**via
transcript pattern matching** — 'um,' 'like,' 'you know'), pitch variance
(monotone vs. expressive), pause patterns."

Only some of those are text-derivable, and this module computes exactly those:

| Signal          | Source                        | Available in Phase 4 |
|-----------------|-------------------------------|----------------------|
| Filler words    | transcript pattern matching   | yes                  |
| Answer length   | transcript                    | yes                  |
| Structure       | transcript (STAR markers)     | yes                  |
| Speaking pace   | needs answer start/end times  | only when timed      |
| Pitch variance  | needs the audio signal        | no — Phase 5         |
| Pause patterns  | needs the audio signal        | no — Phase 5         |

So the communication score Phase 4 produces is real but partial, and it says
so rather than presenting itself as the finished measure. Phase 5's Voice
Prosody Service adds pitch/pause and writes `prosody_signals`; the scoring
layer already prefers that table when a row exists (see scoring.py), so Phase
5 enriches this without rewriting it.

Pace is computed only when the client actually sent `answer_started_at` /
`answer_ended_at` — those columns are nullable and the current browser client
doesn't populate them, so pace is treated as absent rather than guessed at
from word counts.
"""
import re
from dataclasses import dataclass

from app.models.enums import InterviewMode

# Section 9.7's own examples, plus the other high-frequency English fillers.
# Matched as whole words so "like" fires but "unlike" doesn't, and "I'm" isn't
# split apart by the boundary.
FILLER_PATTERNS = (
    r"\bum+\b",
    r"\buh+\b",
    r"\ber+\b",
    r"\bah+\b",
    r"\blike\b",
    r"\byou know\b",
    r"\bi mean\b",
    r"\bbasically\b",
    r"\bactually\b",
    r"\bsort of\b",
    r"\bkind of\b",
    r"\bkinda\b",
    r"\bsorta\b",
    r"\bstuff like that\b",
    r"\bor whatever\b",
    r"\bi guess\b",
)

# Section 9.4's completeness rubric for behavioral answers: "situation, action,
# result". These are the spoken markers of that structure.
STRUCTURE_PATTERNS = (
    r"\bthe situation was\b",
    r"\bthe problem was\b",
    r"\bthe challenge was\b",
    r"\bmy role was\b",
    r"\bi was responsible\b",
    r"\bwhat i did\b",
    r"\bso i\b",
    r"\bfirst,?\b",
    r"\bthen,?\b",
    r"\bas a result\b",
    r"\bthe result was\b",
    r"\bthe outcome\b",
    r"\bin the end\b",
    r"\bwhich meant\b",
    r"\bthis led to\b",
    r"\bwe ended up\b",
)

# Filler rate thresholds (fillers per 100 words). Calibrated so a normal
# spoken answer isn't penalised — a couple of "like"s in 100 words is how
# people actually talk, not a communication defect.
FILLER_RATE_CLEAN = 2.0
FILLER_RATE_NOTICEABLE = 5.0
FILLER_RATE_HEAVY = 9.0

# A substantive spoken answer to an interview question. Below the floor reads
# as under-elaboration rather than concision.
WORDS_UNDER_ELABORATED = 25
WORDS_WELL_DEVELOPED = 60


@dataclass
class TranscriptSignals:
    """Aggregate communication signals across every scored answer in a session."""

    total_words: int = 0
    answer_count: int = 0
    filler_count: int = 0
    structure_marker_count: int = 0
    under_elaborated_answers: int = 0
    well_developed_answers: int = 0
    quantified_answers: int = 0  # answers citing a concrete number
    speaking_pace_wpm: float | None = None  # only when timings were supplied

    @property
    def filler_rate_per_100_words(self) -> float:
        if self.total_words == 0:
            return 0.0
        return (self.filler_count / self.total_words) * 100

    @property
    def average_answer_words(self) -> float:
        if self.answer_count == 0:
            return 0.0
        return self.total_words / self.answer_count

    @property
    def structure_markers_per_answer(self) -> float:
        if self.answer_count == 0:
            return 0.0
        return self.structure_marker_count / self.answer_count


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("’", "'"))


def _count_patterns(text: str, patterns: tuple[str, ...]) -> int:
    return sum(len(re.findall(pattern, text)) for pattern in patterns)


def extract_signals(answers: list[dict]) -> TranscriptSignals:
    """
    `answers` items: {"text": str|None, "is_skipped": bool,
                      "started_at": float|None, "ended_at": float|None}

    Skipped answers contribute nothing — Section 9.8's skip-aware aggregation
    applies to communication signals for the same reason it applies to scores:
    a pass isn't evidence of poor communication.
    """
    signals = TranscriptSignals()
    timed_words = 0
    timed_seconds = 0.0

    for answer in answers:
        if answer.get("is_skipped"):
            continue
        text = (answer.get("text") or "").strip()
        if not text:
            continue

        normalized = _normalize(text)
        words = len(normalized.split())
        if words == 0:
            continue

        signals.answer_count += 1
        signals.total_words += words
        signals.filler_count += _count_patterns(normalized, FILLER_PATTERNS)
        signals.structure_marker_count += _count_patterns(normalized, STRUCTURE_PATTERNS)

        if words < WORDS_UNDER_ELABORATED:
            signals.under_elaborated_answers += 1
        elif words >= WORDS_WELL_DEVELOPED:
            signals.well_developed_answers += 1

        if re.search(r"\d", normalized):
            signals.quantified_answers += 1

        started, ended = answer.get("started_at"), answer.get("ended_at")
        if started is not None and ended is not None and ended > started:
            timed_words += words
            timed_seconds += ended - started

    if timed_seconds > 0:
        signals.speaking_pace_wpm = (timed_words / timed_seconds) * 60

    return signals


COMMUNICATION_BASELINE = 65.0


@dataclass(frozen=True)
class CommunicationComponent:
    """
    One term of the communication score, and the range it can contribute.

    `needs_audible_speech` marks the terms that only mean something about a
    candidate who actually spoke. Both of them measure *how* words came out
    rather than what the words were, which is exactly why they do not survive a
    change of modality.
    """

    name: str
    lowest: float
    highest: float
    needs_audible_speech: bool

    @property
    def swing(self) -> float:
        return self.highest - self.lowest


# The five terms, with the ranges the code below actually produces. Written out
# rather than inferred so the renormalisation has something to renormalise
# against — if a band changes, its entry here has to change with it.
COMMUNICATION_COMPONENTS: tuple[CommunicationComponent, ...] = (
    CommunicationComponent("filler_words", -18.0, 12.0, needs_audible_speech=True),
    CommunicationComponent("elaboration", -20.0, 10.0, needs_audible_speech=False),
    CommunicationComponent("structure", -8.0, 12.0, needs_audible_speech=False),
    CommunicationComponent("concreteness", 0.0, 8.0, needs_audible_speech=False),
    CommunicationComponent("pace", -8.0, 5.0, needs_audible_speech=True),
)


def _component_deltas(signals: TranscriptSignals) -> dict[str, float]:
    """Each term's contribution for this session, before any renormalisation."""
    deltas: dict[str, float] = {}

    # --- Filler words (Section 9.7) ---
    rate = signals.filler_rate_per_100_words
    if rate <= FILLER_RATE_CLEAN:
        deltas["filler_words"] = 12.0
    elif rate <= FILLER_RATE_NOTICEABLE:
        deltas["filler_words"] = 4.0
    elif rate <= FILLER_RATE_HEAVY:
        deltas["filler_words"] = -8.0
    else:
        deltas["filler_words"] = -18.0

    # --- Elaboration ---
    under_rate = signals.under_elaborated_answers / signals.answer_count
    developed_rate = signals.well_developed_answers / signals.answer_count
    deltas["elaboration"] = developed_rate * 10.0 - under_rate * 20.0

    # --- Structure (Section 9.4's situation/action/result) ---
    markers = signals.structure_markers_per_answer
    if markers >= 2.0:
        deltas["structure"] = 12.0
    elif markers >= 1.0:
        deltas["structure"] = 6.0
    elif markers < 0.4:
        deltas["structure"] = -8.0
    else:
        deltas["structure"] = 0.0

    # --- Concreteness: quantified answers read as specific, not vague ---
    deltas["concreteness"] = (signals.quantified_answers / signals.answer_count) * 8.0

    # --- Pace, only when the client supplied real timings ---
    # ~110-160 wpm is a comfortable spoken range; well outside it reads as
    # rushing or dragging.
    deltas["pace"] = 0.0
    if signals.speaking_pace_wpm is not None:
        pace = signals.speaking_pace_wpm
        if 110 <= pace <= 160:
            deltas["pace"] = 5.0
        elif pace < 80 or pace > 200:
            deltas["pace"] = -8.0

    return deltas


def applicable_components(modality: InterviewMode) -> tuple[CommunicationComponent, ...]:
    """
    Which terms mean anything in this modality.

    A signed interview drops filler words and pace. Not as a concession — as a
    correction. An English filler regex finds nothing in a signed answer, so the
    old formula handed every signing candidate a +12 bonus for "clean speech"
    they were never assessed on; and words-per-minute is not a signing rate, so
    the 110-160 band was comparing a candidate against a unit that does not
    apply to them. Scoring either one was worse than not scoring it.
    """
    if modality is InterviewMode.SIGN:
        return tuple(c for c in COMMUNICATION_COMPONENTS if not c.needs_audible_speech)
    return COMMUNICATION_COMPONENTS


def renormalisation_factor(modality: InterviewMode) -> float:
    """
    How much the surviving terms are scaled up to cover the dropped ones' range.

    Same mechanism Section 10.2 uses for whole categories, one level down. Simply
    dropping two terms would compress the score's range — a flawless signed
    session would top out around 95 while a flawless spoken one reaches 100, and
    a poor one would floor at 37 against 11 — so the two scores would not mean
    the same thing. Scaling the remaining terms by the ratio of the ranges keeps
    "out of 100" meaning the same thing in both modalities.

    Note this keys on *modality*, never on whether a given signal happened to be
    captured. A spoken session with no answer timings still carries pace as a
    zero rather than renormalising it away — renormalising on availability would
    silently restate the communication score of every report already generated,
    which is a much larger decision than this one.
    """
    applicable = applicable_components(modality)
    applicable_swing = sum(c.swing for c in applicable)
    if applicable_swing <= 0:
        return 1.0
    return sum(c.swing for c in COMMUNICATION_COMPONENTS) / applicable_swing


def communication_score(
    signals: TranscriptSignals, *, modality: InterviewMode = InterviewMode.VOICE
) -> float | None:
    """
    A 0-100 communication score from text-derivable signals only.

    Returns None when there is nothing to measure — no scored answers means no
    score, rather than a default that would look like a real measurement.

    Starts from a neutral baseline and moves on evidence in both directions, so
    a candidate who speaks cleanly and structures answers well can exceed the
    baseline rather than merely avoiding penalties.

    `modality` decides which terms apply. For `VOICE` all five apply and the
    renormalisation factor is exactly 1.0, so this is arithmetically the same
    formula it has always been — a test pins that, because a phase that quietly
    moved every existing candidate's communication score would be a worse
    outcome than one that refused to support signing at all.
    """
    if signals.answer_count == 0 or signals.total_words == 0:
        return None

    deltas = _component_deltas(signals)
    applicable = applicable_components(modality)
    scale = renormalisation_factor(modality)

    score = COMMUNICATION_BASELINE + sum(deltas[c.name] for c in applicable) * scale
    return max(0.0, min(100.0, round(score, 1)))
