"""
LLM token/cost governance (Section 9.3A).

Four independent controls, all enforced here so failover can never bypass
them (Section 9.3A: "enforced by the AI Provider Gateway centrally, not
duplicated per-provider"):

1. Per-turn ceiling — truncate an over-long raw transcript before it reaches
   the LLM context, while keeping the FULL transcript in `interview_answers`.
2. Per-session ceiling — scaled to the session's selected duration.
3. Compaction — once the session crosses a threshold, older turns collapse
   into a running summary instead of hard-failing mid-interview.
4. Call-count backstop — a pathological conversation can't spiral into
   unbounded billing even if another guardrail has a bug.

Token counting note: this uses a ~4-characters-per-token heuristic rather
than a real tokenizer. That is deliberate — the exact count is
provider-specific (Anthropic and OpenAI tokenize differently, and Anthropic's
own count changed between model generations), so a single shared estimate
that is consistently *slightly conservative* is more useful for enforcing a
budget than a number that's exact for one provider and wrong for the others.
Actual billed usage always comes back from the provider (`TokenUsage`) and is
what gets persisted to `interview_sessions.total_tokens_used`.
"""
from dataclasses import dataclass

_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def truncate_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """
    Section 9.3A: "if a candidate rambles well past this, truncate the
    transcript sent to the LLM (keep the full raw transcript in
    `interview_answers` regardless; only the LLM-context copy is capped) and
    note internally that truncation occurred, so the evaluation isn't
    silently based on a cut-off answer without anyone knowing why."

    Returns (possibly_truncated_text, was_truncated). Keeps the START of the
    answer — a rambling answer's substance is usually front-loaded, and the
    marker tells the model explicitly that it's seeing a prefix so it doesn't
    read the cut as the candidate trailing off.
    """
    if not text:
        return text, False
    max_chars = max_tokens * _CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars].rstrip() + " [...answer truncated for length...]", True


def session_token_ceiling(duration_minutes: int, per_minute: int) -> int:
    """
    Section 9.3A: "a defined budget scaled to the session's selected duration
    — a 45-minute session gets a proportionally larger budget than a
    15-minute one."
    """
    return max(1, duration_minutes) * per_minute


@dataclass
class TokenBudget:
    """Live view of one session's budget, rebuilt per turn from persisted totals."""

    tokens_used: int
    ceiling: int
    calls_made: int
    max_calls: int
    compaction_threshold: int

    @property
    def exhausted(self) -> bool:
        return self.tokens_used >= self.ceiling

    @property
    def calls_exhausted(self) -> bool:
        return self.calls_made >= self.max_calls

    @property
    def should_compact(self) -> bool:
        """True once cumulative usage crosses the threshold — compact rather than fail."""
        return self.tokens_used >= self.compaction_threshold


def build_budget(
    *,
    tokens_used: int,
    duration_minutes: int,
    calls_made: int,
    per_minute: int,
    max_calls: int,
    compaction_ratio: float,
) -> TokenBudget:
    ceiling = session_token_ceiling(duration_minutes, per_minute)
    return TokenBudget(
        tokens_used=tokens_used,
        ceiling=ceiling,
        calls_made=calls_made,
        max_calls=max_calls,
        compaction_threshold=int(ceiling * compaction_ratio),
    )


def compact_conversation(
    conversation: list[dict[str, str]], *, keep_full_turns: int
) -> list[dict[str, str]]:
    """
    Section 9.3A: "keep a running summary + the last N full turns, rather
    than the full raw transcript, once a threshold is crossed".

    The summary is built deterministically from the turns being dropped
    (rather than by making an extra LLM call to summarize) — an extra call to
    save tokens is self-defeating, and it would add latency to a turn that is
    already on Section 14's critical path.
    """
    if len(conversation) <= keep_full_turns:
        return list(conversation)

    older = conversation[:-keep_full_turns] if keep_full_turns else list(conversation)
    recent = conversation[-keep_full_turns:] if keep_full_turns else []

    asked: list[str] = []
    answered = 0
    for message in older:
        content = (message.get("content") or "").strip()
        if message.get("role") == "assistant":
            # First sentence is enough to recall which topic was covered.
            first_sentence = content.split(".")[0][:160]
            if first_sentence:
                asked.append(first_sentence)
        elif content:
            answered += 1

    summary_lines = [
        "EARLIER IN THIS INTERVIEW (compacted summary of turns already covered — "
        "do not repeat these questions or follow-up angles):",
    ]
    summary_lines.extend(f"- Asked about: {topic}" for topic in asked)
    summary_lines.append(f"- The candidate gave {answered} answer(s) to those questions.")

    return [{"role": "assistant", "content": "\n".join(summary_lines)}, *recent]
