"""
Provider-agnostic error taxonomy for the gateway.

The distinction that matters for Section 6.7's failover: a *retryable*
failure (timeout, rate limit, 5xx, connection error) means "try the next
provider"; a *permanent* failure (bad request, bad API key, unknown model)
means the request itself is wrong and every provider will reject it too —
failing over would just multiply the same error across every configured
provider and mask the real cause.
"""


class LLMProviderError(Exception):
    """Base class. `retryable` drives whether the gateway fails over."""

    retryable = False

    def __init__(self, message: str, *, provider: str | None = None):
        self.provider = provider
        super().__init__(message)


class LLMTimeoutError(LLMProviderError):
    retryable = True


class LLMRateLimitError(LLMProviderError):
    retryable = True


class LLMServiceError(LLMProviderError):
    """Provider-side 5xx / overloaded."""

    retryable = True


class LLMConnectionError(LLMProviderError):
    retryable = True


class LLMRefusalError(LLMProviderError):
    """
    The provider's safety classifiers declined the request.

    Retryable across providers because different providers (and different
    models) carry different classifiers, so a refusal on one can legitimately
    succeed on another. Claude Opus 5 returns this as a successful HTTP 200
    with `stop_reason: "refusal"` — see anthropic_adapter.py.
    """

    retryable = True


class LLMInvalidResponseError(LLMProviderError):
    """
    Provider returned something that doesn't satisfy Section 9.3's JSON
    contract. Retryable: a re-roll (or another provider) may well produce
    valid output, and the alternative is failing the candidate's turn.
    """

    retryable = True


class LLMPermanentError(LLMProviderError):
    """Bad request, auth failure, unknown model — failing over won't help."""

    retryable = False


class LLMNotConfiguredError(LLMPermanentError):
    """Adapter has no API key / SDK installed. Permanent for that provider, so the gateway skips to the next."""

    retryable = True


class LLMUnsupportedRequestError(LLMProviderError):
    """
    This adapter cannot serve this *kind* of request at all.

    Raised by the deterministic mock adapter for the free-form JSON calls the
    Feedback Generation Service makes (Section 9.8): the mock is a rule engine,
    not a writer, so it can score a turn but cannot author report prose.

    Retryable so the gateway moves on to the next provider, but the gateway
    deliberately does NOT count it as a health failure — the provider isn't
    unwell, it just doesn't do this. Counting it would degrade a perfectly
    healthy provider for the interview turns it does serve.
    """

    retryable = True
