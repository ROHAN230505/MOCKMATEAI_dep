"""
Freshly generated aptitude questions, verified before anyone is scored on them.

## Why generation needs a verifier and hints do not

A hint is advice: if it is poor, the candidate ignores it. An aptitude question
is a *measurement*, and its answer key decides whether someone's correct answer
is marked wrong. A model that is 95% reliable at writing MCQs is, at ten
questions a test, wrong about one answer key every two tests -- and the
candidate has no way to discover it. That is the exact failure this codebase
refuses elsewhere: a number presented as a measurement that was never taken.

So nothing generated here reaches a candidate on the model's say-so.

## The check: solve it again, blind

Each generated question is handed back to the model **without its answer key**,
as a fresh problem to solve. The question survives only if the independent
solve agrees with the key the generator wrote.

This works because the two calls fail in uncorrelated ways. A generator that
miscounts while writing distractors has no memory of that mistake when it later
solves the question cold; it just solves it, and disagrees. What it does not
catch is a question whose *premise* is wrong in a way the model believes
consistently -- so this raises the floor a long way without being a proof, and
the curated bank remains the fallback rather than being retired.

## Why the bank is still there

Fallback on every failure: provider down, malformed payload, structural
violation, or a verification disagreement. A candidate always gets a test, and
it is always one whose answers have been checked -- by execution for the
curated bank (`tests/test_content_banks.py`), by independent re-solve for these.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.models.enums import AptitudeTopic, Difficulty
from app.services.ai.contracts import LLMRequest
from app.services.ai.errors import LLMProviderError
from app.services.ai.gateway import get_gateway

logger = logging.getLogger("mockmateai.aptitude.generator")

OPTIONS_PER_QUESTION = 4
MAX_QUESTION_CHARS = 600
MAX_OPTION_CHARS = 200

# Verifications run concurrently, but not unboundedly: a free-tier provider
# answers a burst of twelve with 429s, which would fail every question at once
# and silently drop the whole feature back to the bank.
VERIFY_CONCURRENCY = 3


@dataclass(frozen=True)
class GeneratedQuestion:
    topic: AptitudeTopic
    difficulty: Difficulty
    question_text: str
    options: list[str]
    correct_option_index: int
    # The generator's working. Not shown during the test; it is what makes a
    # disagreement debuggable instead of just a rejection count.
    why: str


GENERATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["questions"],
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["question_text", "options", "correct_option_index", "why"],
                "properties": {
                    "question_text": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "correct_option_index": {"type": "integer"},
                    "why": {"type": "string"},
                },
            },
        }
    },
}

SOLVE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer_index", "working"],
    "properties": {
        "answer_index": {"type": "integer"},
        "working": {"type": "string"},
    },
}

GENERATE_SYSTEM = (
    "You write aptitude test questions for software engineering candidates. "
    "Every question is multiple choice with exactly four options and exactly one "
    "unambiguously correct answer.\n\n"
    "RULES:\n"
    "- The correct answer must be provable from the question alone. No outside "
    "knowledge, no ambiguity, no 'best' answer among several defensible ones.\n"
    "- Distractors must be plausible and wrong, not obviously absurd. A question "
    "whose distractors can be eliminated without doing the work measures nothing.\n"
    "- Vary which position holds the correct answer. Do not put it at the same "
    "index every time.\n"
    "- No two options may be equivalent, and none may be 'all of the above' or "
    "'none of the above'.\n"
    "- `why` must show the actual working, enough that a reviewer can check the "
    "marked answer without re-deriving it themselves.\n"
    "- Keep each question self-contained and under 80 words."
)

SOLVE_SYSTEM = (
    "You are solving a multiple-choice aptitude question. You are NOT told which "
    "option is intended to be correct, and no answer key exists in what you were "
    "given.\n\n"
    "Work the problem from first principles and return the zero-based index of the "
    "single option you conclude is correct, with your working. If the question is "
    "ambiguous, under-specified, or has no correct option among those offered, "
    "return -1."
)


def structural_problem(question: dict) -> str | None:
    """
    Why this payload is unusable as a question, or None if it is well formed.

    Checked before any provider call, because a malformed question is not worth
    a verification round trip -- and because several of these are the exact
    shapes that make a question unanswerable rather than merely wrong: an index
    outside the option list, or two options that are the same string.
    """
    text = str(question.get("question_text", "")).strip()
    options = question.get("options")
    index = question.get("correct_option_index")
    why = str(question.get("why", "")).strip()

    if not text or len(text) > MAX_QUESTION_CHARS:
        return "question text missing or too long"
    if not isinstance(options, list) or len(options) != OPTIONS_PER_QUESTION:
        return f"expected exactly {OPTIONS_PER_QUESTION} options"
    cleaned = [str(o).strip() for o in options]
    if any(not o for o in cleaned):
        return "an option is empty"
    if any(len(o) > MAX_OPTION_CHARS for o in cleaned):
        return "an option is too long"
    # Case-folded, because "12 km" and "12 KM" are the same answer offered twice
    # and make the question unanswerable rather than merely easy.
    if len({o.casefold() for o in cleaned}) != OPTIONS_PER_QUESTION:
        return "two options are the same"
    if any(o.casefold() in {"all of the above", "none of the above"} for o in cleaned):
        return "all/none of the above is not a real distractor"
    if not isinstance(index, int) or not 0 <= index < OPTIONS_PER_QUESTION:
        return "correct_option_index is out of range"
    if not why:
        return "no working given"
    return None


async def _verify(question: dict) -> bool:
    """
    Solve the question again without its answer key, and require agreement.

    The options are re-sent in their original order so the index means the same
    thing in both directions; the key itself is never included, which is what
    makes this an independent solve rather than a request to agree.
    """
    options = [str(o).strip() for o in question["options"]]
    listing = "\n".join(f"{i}: {o}" for i, o in enumerate(options))
    request = LLMRequest(
        system_prompt=SOLVE_SYSTEM,
        conversation=[{"role": "user", "content": f"{question['question_text']}\n\n{listing}"}],
        max_output_tokens=600,
        json_schema=SOLVE_SCHEMA,
        schema_name="aptitude_solve",
    )
    try:
        response = await get_gateway().complete_json(request)
    except LLMProviderError as exc:
        logger.info("Verification call failed, question discarded: %s", exc)
        return False

    answer = (response.payload or {}).get("answer_index")
    if not isinstance(answer, int):
        return False
    agreed = answer == question["correct_option_index"]
    if not agreed:
        # Logged at INFO with both answers: a disagreement is the system working,
        # but a *rising* disagreement rate means the generator prompt has drifted.
        logger.info(
            "Discarded a question on verification disagreement [key=%s solver=%s] %s",
            question["correct_option_index"],
            answer,
            str(question["question_text"])[:80],
        )
    return agreed


async def generate_verified(
    *,
    topics: list[AptitudeTopic],
    difficulties: list[Difficulty],
    count: int,
) -> list[GeneratedQuestion]:
    """
    Generate `count` questions and return only those that survive verification.

    Returns fewer than asked for -- possibly none -- and that is the intended
    contract rather than a shortfall to paper over. The caller tops up from the
    curated bank, so a bad generation round degrades into a normal test instead
    of into a test with unchecked answers in it.

    Over-generates deliberately: verification rejects a proportion of what comes
    back, so asking for exactly `count` reliably returns fewer than `count`.
    """
    if count <= 0:
        return []

    topic_names = ", ".join(t.value for t in topics) if topics else "any standard aptitude topic"
    difficulty_names = ", ".join(d.value for d in difficulties) if difficulties else "a mix"
    # A quarter again, capped: enough to absorb the usual rejection rate without
    # turning one test into a dozen provider calls.
    ask_for = min(count + max(2, count // 4), count + 6)

    request = LLMRequest(
        system_prompt=GENERATE_SYSTEM,
        conversation=[
            {
                "role": "user",
                "content": (
                    f"Write {ask_for} aptitude questions.\n"
                    f"Topics: {topic_names}.\n"
                    f"Difficulty: {difficulty_names}.\n"
                    "Make them different from each other in both subject and shape -- not the "
                    "same template with different numbers."
                ),
            }
        ],
        max_output_tokens=4000,
        json_schema=GENERATE_SCHEMA,
        schema_name="aptitude_questions",
    )

    try:
        response = await get_gateway().complete_json(request)
    except LLMProviderError as exc:
        logger.warning("Aptitude generation unavailable, falling back to the bank: %s", exc)
        return []

    raw = (response.payload or {}).get("questions")
    if not isinstance(raw, list):
        logger.warning("Aptitude generation returned no question list; falling back to the bank.")
        return []

    # Structural rejects first: they cost nothing and save a round trip each.
    candidates = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        problem = structural_problem(item)
        if problem:
            logger.info("Discarded a malformed generated question (%s).", problem)
            continue
        candidates.append(item)

    semaphore = asyncio.Semaphore(VERIFY_CONCURRENCY)

    async def guarded(item: dict) -> bool:
        async with semaphore:
            return await _verify(item)

    verdicts = await asyncio.gather(*(guarded(c) for c in candidates), return_exceptions=True)

    default_topic = topics[0] if topics else AptitudeTopic.QUANTITATIVE
    default_difficulty = difficulties[0] if difficulties else Difficulty.MEDIUM

    survivors: list[GeneratedQuestion] = []
    for item, verdict in zip(candidates, verdicts):
        if verdict is not True:
            continue
        survivors.append(
            GeneratedQuestion(
                topic=default_topic,
                difficulty=default_difficulty,
                question_text=str(item["question_text"]).strip(),
                options=[str(o).strip() for o in item["options"]],
                correct_option_index=int(item["correct_option_index"]),
                why=str(item["why"]).strip(),
            )
        )

    logger.info(
        "Aptitude generation: asked %s, %s well formed, %s verified.",
        ask_for,
        len(candidates),
        len(survivors),
    )
    return survivors[:count]
