"""
AI Provider Gateway (MASTER_PROMPT.md Section 6.7).

The only module outside this package that anything else should import is
`gateway` — provider SDKs, native request/response shapes, and per-provider
error types stay behind the `LLMAdapter` interface so "the rest of the
orchestrator never needs to know which provider answered" (Section 6.7).
"""
from app.services.ai.contracts import (  # noqa: F401
    InternalEvaluation,
    LLMRequest,
    LLMResponse,
    TokenUsage,
    TurnDecision,
    TurnDecisionResult,
)
from app.services.ai.errors import (  # noqa: F401
    LLMConnectionError,
    LLMInvalidResponseError,
    LLMNotConfiguredError,
    LLMPermanentError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMServiceError,
    LLMTimeoutError,
)

__all__ = [
    "InternalEvaluation",
    "LLMRequest",
    "LLMResponse",
    "TokenUsage",
    "TurnDecision",
    "TurnDecisionResult",
    "LLMProviderError",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "LLMServiceError",
    "LLMConnectionError",
    "LLMRefusalError",
    "LLMInvalidResponseError",
    "LLMPermanentError",
    "LLMNotConfiguredError",
]
