"""
Provider-agnostic contracts for the AI Provider Gateway (Section 6.7).

Section 6.7 requires that "the LLM Engine's strict JSON output contract
(Section 9.3) must be enforced identically regardless of which provider
actually served the request — the gateway (or a thin adapter layer per
provider) is responsible for translating each provider's native
call/response into the same internal `{decision, utterance,
internal_evaluation}` shape, so the rest of the orchestrator never needs to
know which provider answered."

These dataclasses/models ARE that shape. Nothing outside `app/services/ai/`
should import a provider SDK or know a provider's native response format.
"""
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TurnDecision(str, Enum):
    """Section 9.3's `decision` field."""

    NEXT_QUESTION = "next_question"
    FOLLOWUP = "followup"
    SKIP = "skip"


class InternalEvaluation(BaseModel):
    """
    Section 9.3's `internal_evaluation` block — never spoken or shown live;
    persisted to `answer_evaluations` and reused by the Feedback Generation
    Service so the two never diverge.

    Scores are clamped, not trusted: Section 12.8 requires we "validate that
    `internal_evaluation` outputs stay within expected schema/ranges
    server-side regardless of what the LLM returns, and clamp/reject
    out-of-range scores rather than trusting the model blindly."
    """

    relevance_score: int | None = Field(default=None, ge=0, le=10)
    completeness_score: int | None = Field(default=None, ge=0, le=10)
    reasoning: str | None = Field(default=None, max_length=2000)

    @field_validator("relevance_score", "completeness_score", mode="before")
    @classmethod
    def _clamp_scores(cls, value):
        """Clamp rather than reject — a slightly out-of-range score shouldn't fail a live interview turn."""
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return int(max(0, min(10, round(numeric))))


class TurnDecisionResult(BaseModel):
    """The normalized `{decision, utterance, internal_evaluation}` shape from Section 9.3."""

    decision: TurnDecision
    utterance: str = Field(min_length=1, max_length=4000)
    internal_evaluation: InternalEvaluation | None = None


@dataclass
class TokenUsage:
    """
    Per-call token accounting for Section 9.3A's cost monitoring.

    `prompt_tokens` counts the FULL prompt including cached portions —
    Anthropic's `usage.input_tokens` reports only the uncached remainder, so
    the adapter must add `cache_creation_input_tokens` +
    `cache_read_input_tokens` back in or every cached turn under-reports.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_prompt_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMResponse:
    """What every adapter returns, regardless of provider."""

    result: TurnDecisionResult
    usage: TokenUsage
    provider: str
    model: str
    truncated_transcript: bool = False


@dataclass
class RawJSONResponse:
    """
    An arbitrary provider-validated JSON object, for callers whose output
    contract isn't Section 9.3's turn decision.

    The Feedback Generation Service (Section 9.8) needs a different shape
    entirely — category strengths, improvements, evidence references — but it
    must still go through the gateway, because Section 6.7 makes the gateway
    "the single entry point for every LLM call in the system" and that's what
    gives feedback generation the same failover, health tracking and cost
    accounting an interview turn gets. So the adapter returns the parsed object
    and the *caller* validates it against its own schema.
    """

    payload: dict
    usage: TokenUsage
    provider: str
    model: str


@dataclass
class LLMRequest:
    """
    What every adapter accepts. Deliberately NOT a provider message list —
    each adapter maps this into its own native format.

    `system_prompt` must be byte-stable across turns within a session so
    prompt caching actually hits (see anthropic_adapter.py); anything that
    varies per turn belongs in `conversation`.
    """

    system_prompt: str
    conversation: list[dict[str, str]] = field(default_factory=list)
    max_output_tokens: int = 4096
    json_schema: dict | None = None
    # Names the schema for providers that require one (OpenAI's json_schema
    # mode does; Anthropic's output_config.format does not).
    schema_name: str = "turn_decision"
