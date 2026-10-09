"""
Deterministic, rule-based LLM adapter — the default provider.

This is NOT a stub that returns a canned string. It scores answers with
transcript heuristics that approximate Section 9.4's evaluation rubric
(relevance, completeness, specificity), so it exercises the full downstream
path for real: Section 10.3's guardrail bands, follow-up generation, skip
handling, `answer_evaluations` persistence, and token accounting.

Two reasons it earns its place beyond "works without an API key":
1. Determinism makes Section 15's AI evaluation set meaningful — the same
   candidate answer must always produce the same follow-up decision, which a
   real LLM cannot guarantee, so the guardrail regression tests would be
   flaky if they ran against a live provider.
2. Section 15 explicitly says "don't hit real paid AI APIs in CI".

What it deliberately does NOT do: understand meaning. It cannot tell a
technically wrong answer from a right one (Section 9.4's "technical
correctness" criterion), and its follow-ups are templated rather than
genuinely contextual. That is the gap a real provider closes.

It also does not implement `complete_json`, so Section 9.8's feedback-report
call falls straight through to the next provider. Faking report prose from a
rule engine would produce writing that reads like analysis without being any,
which Section 1.2's "Honesty over flattery" rules out. The deterministic
substitute lives in `services/feedback/narrative.py`, which writes from the
real computed scores and labels itself as deterministic in the report.
"""
import re

from app.services.ai.base import LLMAdapter
from app.services.ai.contracts import (
    InternalEvaluation,
    LLMRequest,
    LLMResponse,
    TokenUsage,
    TurnDecision,
    TurnDecisionResult,
)

# Section 9.3's SKIP HANDLING: "a clear pass/skip intent ... and close
# natural variants — not just an exact phrase match". Matched as whole
# phrases against a normalized transcript so "I know this one" can never
# match "i don't know".
SKIP_PHRASES = (
    "i don't know",
    "i do not know",
    "i dont know",
    "no idea",
    "not sure about this one",
    "let's move on",
    "lets move on",
    "can we skip",
    "can i skip",
    "skip this one",
    "skip this question",
    "pass on this",
    "i'll pass",
    "ill pass",
    "next question",
    "move on to the next",
    "i'm not sure, next",
    "im not sure, next",
    "i have no answer",
    "i can't answer",
    "i cannot answer",
)

# Section 9.4: "Vague ('I'm a hard worker') vs. concrete (named example,
# numbers, outcome) — this is the single strongest follow-up trigger signal."
VAGUE_MARKERS = (
    "hard worker",
    "team player",
    "fast learner",
    "people person",
    "good communicator",
    "i'm passionate",
    "im passionate",
    "i always try my best",
    "i work well with others",
    "detail oriented",
    "detail-oriented",
    "self motivated",
    "self-motivated",
)

# Concrete-specificity signals: named technologies, STAR-structure markers,
# and quantified outcomes.
TECH_MARKERS = (
    "python", "java", "javascript", "typescript", "react", "node", "sql", "postgres", "mysql",
    "mongodb", "redis", "docker", "kubernetes", "aws", "azure", "gcp", "git", "linux", "api",
    "rest", "graphql", "django", "flask", "spring", "kafka", "nginx", "terraform", "pandas",
    "numpy", "pytorch", "tensorflow", "hash map", "hashmap", "binary search", "linked list",
    "recursion", "big-o", "big o", "index", "cache", "queue", "stack", "thread", "mutex",
)
STAR_MARKERS = (
    "the situation was", "my role was", "i was responsible", "what i did was", "so i ",
    "as a result", "the result was", "in the end", "which meant", "the outcome",
    "we ended up", "this led to", "because of that", "the problem was", "the challenge was",
)
FILLER_WORDS = ("um", "uh", "like", "you know", "basically", "actually", "sort of", "kind of")

# Follow-up templates, selected by which rubric dimension scored lowest so
# the probe targets the actual weakness rather than being generic (Section
# 9.3: "'Can you clarify?' is weak").
FOLLOWUP_NO_SPECIFICS = (
    "That's a reasonable start, but it's quite general. Can you walk me through one specific example — "
    "what the situation was, what you actually did, and how it turned out?"
)
FOLLOWUP_NO_OUTCOME = (
    "You've described what you did. What was the actual outcome? If you can put a number or a "
    "concrete result on it, that would help."
)
FOLLOWUP_TOO_SHORT = (
    "Could you expand on that a little? I'd like to hear more about your reasoning and how you'd "
    "approach it in practice."
)
FOLLOWUP_VAGUE_CLAIM = (
    "You mentioned that about yourself — what's a concrete situation where that actually made a "
    "difference to the result?"
)
ACKNOWLEDGEMENTS = (
    "Thanks, that's clear.",
    "Got it, that makes sense.",
    "Understood, thank you.",
    "That's helpful, thanks.",
)
SKIP_ACKNOWLEDGEMENT = "No problem, let's move on."


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace/punctuation runs so phrase matching is robust to ASR formatting."""
    lowered = text.lower().replace("’", "'")
    return re.sub(r"\s+", " ", lowered)


# A pass phrase followed by a contrastive conjunction and real content is a
# candidate QUALIFYING their answer, not passing on it: "I don't know the exact
# syntax, but the approach is to cache it in Redis" is an answer. Treating it as
# a skip would silently discard a real answer and deny the candidate both a
# score and a follow-up — the worst possible outcome for them.
_CONTRAST_MARKERS = (" but ", " however", " though ", " although ", " that said", " even so")
_MIN_WORDS_AFTER_CONTRAST = 4


def detect_skip_intent(transcript: str) -> bool:
    """
    Section 9.3: "Do not infer skip intent from a merely short or hesitant
    answer — only from clear, explicit pass language." So an explicit phrase is
    required; length alone never implies a skip.

    The converse also has to hold: an explicit phrase alone is not sufficient
    when the candidate goes on to answer anyway (see _CONTRAST_MARKERS).
    """
    normalized = _normalize(transcript)

    earliest_phrase_end = None
    for phrase in SKIP_PHRASES:
        index = normalized.find(phrase)
        if index != -1:
            phrase_end = index + len(phrase)
            if earliest_phrase_end is None or phrase_end < earliest_phrase_end:
                earliest_phrase_end = phrase_end

    if earliest_phrase_end is None:
        return False

    # Look only AFTER the pass phrase: a contrast marker before it isn't the
    # candidate walking their pass back.
    remainder = normalized[earliest_phrase_end:]
    for marker in _CONTRAST_MARKERS:
        position = remainder.find(marker)
        if position == -1:
            continue
        after_contrast = remainder[position + len(marker) :].split()
        if len(after_contrast) >= _MIN_WORDS_AFTER_CONTRAST:
            return False

    return True


def _count_markers(normalized: str, markers) -> int:
    return sum(1 for marker in markers if marker in normalized)


def score_answer(transcript: str) -> tuple[int, int, str]:
    """
    Heuristic stand-in for Section 9.4's rubric.
    Returns (relevance_score, completeness_score, reasoning).
    """
    normalized = _normalize(transcript)
    words = normalized.split()
    word_count = len(words)

    has_numbers = bool(re.search(r"\d", normalized))
    tech_hits = _count_markers(normalized, TECH_MARKERS)
    star_hits = _count_markers(normalized, STAR_MARKERS)
    vague_hits = _count_markers(normalized, VAGUE_MARKERS)
    filler_hits = _count_markers(normalized, FILLER_WORDS)

    # Relevance: mostly length + on-topic signal, penalized for pure vagueness.
    relevance = 3
    if word_count >= 15:
        relevance += 2
    if word_count >= 40:
        relevance += 1
    if tech_hits or star_hits:
        relevance += 2
    if has_numbers:
        relevance += 1
    if vague_hits and not (tech_hits or star_hits or has_numbers):
        relevance -= 2
    relevance = max(0, min(10, relevance))

    # Completeness: rewards structure and concrete outcomes specifically.
    completeness = 2
    if word_count >= 25:
        completeness += 2
    if word_count >= 60:
        completeness += 1
    if star_hits >= 1:
        completeness += 2
    if star_hits >= 3:
        completeness += 1
    if has_numbers:
        completeness += 1
    if tech_hits >= 2:
        completeness += 1
    if word_count < 12:
        completeness -= 2
    completeness = max(0, min(10, completeness))

    reasoning = (
        f"[mock heuristic] {word_count} words; "
        f"{tech_hits} technical marker(s), {star_hits} structure marker(s), "
        f"{vague_hits} vague claim(s), {filler_hits} filler word(s), "
        f"numbers present: {has_numbers}."
    )
    return relevance, completeness, reasoning


def _choose_followup(transcript: str, relevance: int, completeness: int) -> str:
    normalized = _normalize(transcript)
    word_count = len(normalized.split())

    if word_count < 12:
        return FOLLOWUP_TOO_SHORT
    if _count_markers(normalized, VAGUE_MARKERS) and not re.search(r"\d", normalized):
        return FOLLOWUP_VAGUE_CLAIM
    if completeness < relevance:
        return FOLLOWUP_NO_OUTCOME
    return FOLLOWUP_NO_SPECIFICS


def _estimate_tokens(text: str) -> int:
    """
    ~4 characters per token — the standard rough heuristic. The mock has no
    real tokenizer, and the point here is that Section 9.3A's accounting
    path is exercised with plausible non-zero numbers, not that the count is
    exact.
    """
    return max(1, len(text) // 4)


class MockLLMAdapter(LLMAdapter):
    name = "mock"

    def is_configured(self) -> bool:
        return True  # no key required — that's the point

    async def complete(self, request: LLMRequest) -> LLMResponse:
        latest_answer = self._latest_candidate_answer(request)

        # No answer yet -> opening turn.
        if not latest_answer.strip():
            opening = self._next_planned_utterance(request) or (
                "Tell me a little about yourself and what's brought you to this interview."
            )
            result = TurnDecisionResult(
                decision=TurnDecision.NEXT_QUESTION, utterance=opening, internal_evaluation=None
            )
            return self._respond(request, result)

        if detect_skip_intent(latest_answer):
            next_question = self._next_planned_utterance(request)
            utterance = f"{SKIP_ACKNOWLEDGEMENT} {next_question}" if next_question else SKIP_ACKNOWLEDGEMENT
            result = TurnDecisionResult(
                # Section 9.3: on skip, internal_evaluation is omitted rather
                # than defaulted to 0, so a skip is never indistinguishable
                # from a scored-zero answer downstream.
                decision=TurnDecision.SKIP,
                utterance=utterance,
                internal_evaluation=None,
            )
            return self._respond(request, result)

        relevance, completeness, reasoning = score_answer(latest_answer)
        evaluation = InternalEvaluation(
            relevance_score=relevance, completeness_score=completeness, reasoning=reasoning
        )

        # The mock proposes; the deterministic guardrail layer (Section 10.3)
        # disposes. Mid-band answers are where the LLM's own judgment
        # applies, so the mock leans toward moving on to keep pacing natural
        # (Section 9.3: "not every answer needs a follow-up").
        wants_followup = relevance < 6 or completeness < 6
        if wants_followup:
            result = TurnDecisionResult(
                decision=TurnDecision.FOLLOWUP,
                utterance=_choose_followup(latest_answer, relevance, completeness),
                internal_evaluation=evaluation,
            )
        else:
            acknowledgement = ACKNOWLEDGEMENTS[len(request.conversation) % len(ACKNOWLEDGEMENTS)]
            next_question = self._next_planned_utterance(request)
            utterance = f"{acknowledgement} {next_question}" if next_question else acknowledgement
            result = TurnDecisionResult(
                decision=TurnDecision.NEXT_QUESTION, utterance=utterance, internal_evaluation=evaluation
            )

        return self._respond(request, result)

    @staticmethod
    def _latest_candidate_answer(request: LLMRequest) -> str:
        """
        Extracts the most recent answer from the engine's
        `<candidate_answer>` fence rather than just taking the last `user`
        message.

        This matters because the engine appends a per-turn *context* message
        (next planned topic, interruption notes) as the final `user` turn, so
        "last user message" would score that context block as if it were the
        candidate's answer. Reading the explicit data fence is also exactly
        what the system prompt instructs a real model to treat as candidate
        speech (Section 12.8), so the mock and a real provider agree on what
        the answer even is.
        """
        opening_tag = "<candidate_answer>"
        closing_tag = "</candidate_answer>"

        for message in reversed(request.conversation):
            content = message.get("content", "")
            start = content.find(opening_tag)
            if start == -1:
                continue
            end = content.find(closing_tag, start)
            inner = content[start + len(opening_tag) : end if end != -1 else None]
            answer = inner.strip()
            # A passed question is fenced with an explicit placeholder rather
            # than real speech; treat it as no answer so it isn't scored.
            if answer.startswith("[") and answer.endswith("]"):
                return ""
            return answer
        return ""

    @staticmethod
    def _next_planned_utterance(request: LLMRequest) -> str | None:
        """
        Reads the next planned topic from the engine's machine-readable
        marker (llm_engine.NEXT_TOPIC_MARKER). A real provider infers this
        from the prompt's planned-topics prose; the mock needs it parseable.

        Searches the per-turn conversation messages first, since that's where
        the engine puts it — keeping it OUT of the system prompt is what lets
        the system prompt stay byte-stable across a session so provider
        prompt caching actually hits. The system prompt is still searched as a
        fallback so a caller that inlines the marker there also works.
        """
        marker = "NEXT_PLANNED_TOPIC:"
        haystacks = [message.get("content", "") for message in reversed(request.conversation)]
        haystacks.append(request.system_prompt)

        for haystack in haystacks:
            for line in haystack.splitlines():
                stripped = line.strip()
                if stripped.startswith(marker):
                    topic = stripped[len(marker) :].strip()
                    return topic or None
        return None

    def _respond(self, request: LLMRequest, result: TurnDecisionResult) -> LLMResponse:
        prompt_text = request.system_prompt + "".join(m.get("content", "") for m in request.conversation)
        usage = TokenUsage(
            prompt_tokens=_estimate_tokens(prompt_text),
            completion_tokens=_estimate_tokens(result.utterance),
        )
        return LLMResponse(result=result, usage=usage, provider=self.name, model="mock-deterministic-v1")
