"""
Deterministic narrative writer — the degraded-mode half of Section 9.8.

Section 21.2 requires that "every external AI dependency needs a defined
degraded-mode behavior, not a silent crash". A report is generated after the
interview is already over, so unlike a live turn there is no candidate waiting
on a socket — but there is still a promise on screen that a report is coming,
and returning nothing would break it.

This module keeps that promise without a provider. It is the default path in
two situations:

1. Only the deterministic mock provider is configured (the out-of-the-box
   setup, and CI — Section 15: "don't hit real paid AI APIs in CI").
2. Every configured provider failed the report call.

What it produces is real, not filler: every item below is derived from a score
or a signal that was actually measured, and every item quotes the candidate's
own words. What it cannot do is *read* the answers — it can say an answer was
short, unquantified, or scored low, but not what was technically wrong with it.
So the report labels itself: `generated_by` is recorded as
"deterministic" rather than a provider name, and the summary says outright that
the qualitative analysis is rule-based. A candidate reading it knows exactly
what they're looking at, which is the point of Section 1.2's honesty rule.
"""
from app.models.enums import FeedbackCategory, FeedbackItemType
from app.services.feedback.prompts import GeneratedNarrative, NarrativeItem
from app.services.feedback.scoring import ScoreBreakdown, TurnRecord
from app.services.feedback.transcript_signals import (
    FILLER_RATE_NOTICEABLE,
    WORDS_UNDER_ELABORATED,
)

# A turn scoring at or above this (0-100) is worth citing as a strength; at or
# below the lower bound, as an improvement. The band between them is ordinary —
# neither a highlight nor a problem, and padding the report with it would bury
# the items that matter.
STRONG_TURN_SCORE = 70.0
WEAK_TURN_SCORE = 50.0

QUOTE_MAX_WORDS = 18
MAX_TURN_ITEMS_PER_TYPE = 2


def _quote(text: str | None) -> str | None:
    """A short verbatim excerpt — never a paraphrase, so the citation stays checkable."""
    if not text:
        return None
    words = text.strip().split()
    if not words:
        return None
    if len(words) <= QUOTE_MAX_WORDS:
        return " ".join(words)
    return " ".join(words[:QUOTE_MAX_WORDS]) + "…"


def _band(score: float | None) -> str:
    if score is None:
        return "not measured"
    if score >= 75:
        return "strong"
    if score >= 60:
        return "solid"
    if score >= 45:
        return "mixed"
    return "weak"


def _content_items(turns: list[TurnRecord]) -> list[NarrativeItem]:
    items: list[NarrativeItem] = []
    scored = [
        (index + 1, turn)
        for index, turn in enumerate(turns)
        if not turn.is_skipped and turn.turn_score_0_100 is not None and (turn.transcript_text or "").strip()
    ]
    if not scored:
        return items

    best = sorted(scored, key=lambda pair: pair[1].turn_score_0_100, reverse=True)
    worst = sorted(scored, key=lambda pair: pair[1].turn_score_0_100)

    for number, turn in best[:MAX_TURN_ITEMS_PER_TYPE]:
        if turn.turn_score_0_100 < STRONG_TURN_SCORE:
            break
        items.append(
            NarrativeItem(
                category=FeedbackCategory.CONTENT,
                type=FeedbackItemType.STRENGTH,
                text=(
                    "This answer landed. It stayed on the question that was asked and covered enough of "
                    "the expected ground that an interviewer would move on satisfied. Keep answering at "
                    "this level of substance."
                ),
                evidence_question_number=number,
                evidence_quote=_quote(turn.transcript_text),
            )
        )

    for number, turn in worst[:MAX_TURN_ITEMS_PER_TYPE]:
        if turn.turn_score_0_100 > WEAK_TURN_SCORE:
            break
        words = len((turn.transcript_text or "").split())
        if words < WORDS_UNDER_ELABORATED:
            text = (
                "This answer was too short to show what you know. Rebuild it as three beats: the "
                "situation you were in, the specific thing you did, and how it turned out. Aim for "
                "around a minute of speech rather than a single sentence."
            )
        else:
            text = (
                "This answer drifted from what was asked, or left out the parts an interviewer was "
                "listening for. Before answering, name the question back to yourself in one line, then "
                "answer that line directly and finish with the outcome."
            )
        items.append(
            NarrativeItem(
                category=FeedbackCategory.CONTENT,
                type=FeedbackItemType.IMPROVEMENT,
                text=text,
                evidence_question_number=number,
                evidence_quote=_quote(turn.transcript_text),
            )
        )

    return items


def _communication_items(breakdown: ScoreBreakdown, turns: list[TurnRecord]) -> list[NarrativeItem]:
    items: list[NarrativeItem] = []
    signals = breakdown.signals
    if signals is None or signals.answer_count == 0:
        return items

    def first_quote() -> tuple[int | None, str | None]:
        for index, turn in enumerate(turns):
            if not turn.is_skipped and (turn.transcript_text or "").strip():
                return index + 1, _quote(turn.transcript_text)
        return None, None

    number, quote = first_quote()
    filler_rate = signals.filler_rate_per_100_words

    if filler_rate > FILLER_RATE_NOTICEABLE:
        items.append(
            NarrativeItem(
                category=FeedbackCategory.COMMUNICATION,
                type=FeedbackItemType.IMPROVEMENT,
                text=(
                    f"You used {signals.filler_count} filler words across {signals.total_words} words of "
                    f"answers — roughly {filler_rate:.1f} per hundred words. Fillers cluster where you're "
                    "thinking, so buy that time deliberately instead: pause for a beat, then start the "
                    "sentence. A silent pause reads as composure; 'um, like, you know' reads as "
                    "uncertainty."
                ),
                evidence_question_number=number,
                evidence_quote=quote,
            )
        )
    else:
        items.append(
            NarrativeItem(
                category=FeedbackCategory.COMMUNICATION,
                type=FeedbackItemType.STRENGTH,
                text=(
                    f"Your delivery was clean — only {signals.filler_count} filler words across "
                    f"{signals.total_words} words. That's noticeably tidier than most candidates manage "
                    "under pressure and it makes you easy to follow."
                ),
                evidence_question_number=number,
                evidence_quote=quote,
            )
        )

    if signals.under_elaborated_answers > 0:
        items.append(
            NarrativeItem(
                category=FeedbackCategory.COMMUNICATION,
                type=FeedbackItemType.IMPROVEMENT,
                text=(
                    f"{signals.under_elaborated_answers} of your {signals.answer_count} answers ran under "
                    f"{WORDS_UNDER_ELABORATED} words. Short answers hand the work back to the "
                    "interviewer. Finish each one with a concrete detail — a number, a tool, a result — "
                    "so they don't have to ask for it."
                ),
                evidence_question_number=number,
                evidence_quote=quote,
            )
        )
    elif signals.well_developed_answers >= max(1, signals.answer_count // 2):
        items.append(
            NarrativeItem(
                category=FeedbackCategory.COMMUNICATION,
                type=FeedbackItemType.STRENGTH,
                text=(
                    "You gave your answers room to breathe — most ran long enough to actually make a "
                    f"case, averaging about {signals.average_answer_words:.0f} words. That's the right "
                    "length for a spoken interview answer."
                ),
                evidence_question_number=number,
                evidence_quote=quote,
            )
        )

    if signals.quantified_answers == 0:
        items.append(
            NarrativeItem(
                category=FeedbackCategory.COMMUNICATION,
                type=FeedbackItemType.IMPROVEMENT,
                text=(
                    "None of your answers cited a concrete number. Quantities are what make an "
                    "accomplishment legible to someone who wasn't there — how many users, how much "
                    "faster, how many hours saved, how big the team. Pick two stories before your next "
                    "interview and attach real figures to them."
                ),
                evidence_question_number=number,
                evidence_quote=quote,
            )
        )

    if signals.structure_markers_per_answer < 0.4:
        items.append(
            NarrativeItem(
                category=FeedbackCategory.COMMUNICATION,
                type=FeedbackItemType.IMPROVEMENT,
                text=(
                    "Your answers ran together without much visible structure. Signpost them out loud: "
                    "'the situation was…', 'what I did was…', 'the result was…'. It costs nothing and it "
                    "makes an interviewer's job easy, which they remember."
                ),
                evidence_question_number=number,
                evidence_quote=quote,
            )
        )
    elif signals.structure_markers_per_answer >= 1.0:
        items.append(
            NarrativeItem(
                category=FeedbackCategory.COMMUNICATION,
                type=FeedbackItemType.STRENGTH,
                text=(
                    "You structured your answers as you spoke — setting up the situation, saying what you "
                    "did, then landing the outcome. That's the pattern interviewers are trained to listen "
                    "for."
                ),
                evidence_question_number=number,
                evidence_quote=quote,
            )
        )

    return items


def _summary(breakdown: ScoreBreakdown) -> str:
    parts: list[str] = []

    if breakdown.scored_count == 0:
        parts.append(
            "There wasn't enough answered material in this session to assess. Nothing here reflects on "
            "you — the interview ended before there was anything to score."
        )
    else:
        content_band = _band(breakdown.content_score)
        comms_band = _band(breakdown.communication_score)
        parts.append(
            f"You answered {breakdown.answered_count} question"
            f"{'s' if breakdown.answered_count != 1 else ''}"
            + (f" and passed on {breakdown.skipped_count}" if breakdown.skipped_count else "")
            + f". The substance of your answers came out {content_band}, and how you delivered them came "
            f"out {comms_band}."
        )
        parts.append(
            "The specific strengths and improvements below each point at a question and quote what you "
            "actually said, so you can go back and hear the difference for yourself."
        )

    if breakdown.unmeasured_categories:
        missing = ", ".join(name.replace("_", " ") for name in breakdown.unmeasured_categories)
        parts.append(
            f"This report does not cover {missing} — this session captured no voice-tone or video "
            "signal, so there is genuinely nothing measured there. Those scores are left blank rather "
            "than guessed at."
        )

    parts.append(
        "One note on how this was written: no language model was available for this report, so the "
        "analysis below is rule-based. The scores and the evidence are real measurements of your "
        "session, but the wording is templated and cannot judge whether an answer was technically "
        "correct — only how complete, specific and well-structured it was."
    )
    return " ".join(parts)


def build_narrative(breakdown: ScoreBreakdown, turns: list[TurnRecord]) -> GeneratedNarrative:
    """
    Compose a report from the deterministic scores and signals alone.

    Ordering is deliberate: strengths first within each category, since Section
    4.11's report leads with what worked. Items are capped by
    `GeneratedNarrative`, so this can propose generously and let the contract
    trim.
    """
    items = _content_items(turns) + _communication_items(breakdown, turns)
    items.sort(key=lambda item: (item.category.value, 0 if item.type == FeedbackItemType.STRENGTH else 1))
    return GeneratedNarrative(summary_text=_summary(breakdown), items=items)
