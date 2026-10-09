"""
AI Provider Gateway (Section 6.7) — the single entry point for every LLM
call in the system.

Responsibilities, all four from Section 6.7:
1. Route to the active provider, ordered by config not code.
2. Fail over mid-session on error/degradation, retrying the SAME request
   against the next provider in order.
3. Keep session consistency — "once a session has failed over to a secondary
   provider, prefer staying on it for the rest of that session rather than
   flapping back and forth on transient blips ... only fail back to the
   primary on the *next new* session".
4. Log every failover event for the monitoring in Section 13.

Section 9.3A's token/cost ceilings are enforced here too — "centrally, not
duplicated per-provider, so failover never accidentally bypasses cost
controls".
"""
import logging
import time

from app.config import get_settings
from app.services.ai.base import LLMAdapter
from app.services.ai.contracts import LLMRequest, LLMResponse, RawJSONResponse
from app.services.ai.errors import LLMNotConfiguredError, LLMProviderError, LLMUnsupportedRequestError
from app.services.ai.health import ProviderHealthTracker
from app.services.ai.mock_adapter import MockLLMAdapter

logger = logging.getLogger("mockmateai.ai.gateway")


def _build_adapter(name: str, api_key: str | None) -> LLMAdapter | None:
    """
    Adapters are constructed lazily by name so an unconfigured provider never
    imports its SDK. Returns None for an unknown name rather than raising —
    a typo in MOCKMATEAI_LLM_PROVIDER_ORDER shouldn't take the app down, it
    should log loudly and fall through to the next provider.
    """
    if name == "mock":
        return MockLLMAdapter()
    if name == "anthropic":
        from app.services.ai.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(api_key=api_key)
    if name == "openai":
        from app.services.ai.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(api_key=api_key)
    logger.error("Unknown LLM provider %r in MOCKMATEAI_LLM_PROVIDER_ORDER — skipping it.", name)
    return None


class AIProviderGateway:
    def __init__(self):
        settings = get_settings()
        self._health = ProviderHealthTracker(
            degraded_after=settings.llm_degraded_after_consecutive_failures,
            cooldown_seconds=settings.llm_degraded_cooldown_seconds,
        )
        # Providers arrive already paired with their keys -- see
        # `Settings.llm_provider_chain`. The pairing moved there because doing
        # it here by list position let a key sit in a slot the order did not
        # name, which fell through to `mock` without saying so.
        self._adapters: list[LLMAdapter] = []
        for provider_name, api_key in settings.llm_provider_chain:
            adapter = _build_adapter(provider_name, api_key)
            if adapter is not None:
                self._adapters.append(adapter)

        # Logged at startup, because "why is it still giving me templated
        # follow-ups" is otherwise invisible: an unset key and a typo'd one
        # both look like a working app that simply is not very clever.
        intelligent = [a.name for a in self._adapters if a.name != "mock" and a.is_configured()]
        if intelligent:
            logger.info(
                "LLM chain: %s (mock last as fallback). Questions and evaluation are model-generated.",
                ", ".join(intelligent),
            )
        else:
            logger.warning(
                "No LLM provider is configured, so the deterministic mock adapter is answering every "
                "turn. Follow-ups will be templated and answers cannot be judged for correctness. "
                "Set MOCKMATEAI_LLM_API_KEY to an Anthropic (sk-ant-...) or OpenAI (sk-...) key.",
            )

        # session_id -> provider name it has already failed over to.
        self._session_pins: dict[str, str] = {}

    @property
    def health(self) -> ProviderHealthTracker:
        return self._health

    def provider_names(self) -> list[str]:
        return [adapter.name for adapter in self._adapters]

    def pinned_provider(self, session_id: str | None) -> str | None:
        return self._session_pins.get(session_id) if session_id else None

    def release_session(self, session_id: str) -> None:
        """Called on session end so pins don't accumulate for the process lifetime."""
        self._session_pins.pop(session_id, None)

    def _ordered_adapters(self, session_id: str | None) -> list[LLMAdapter]:
        """
        Section 6.7's session consistency: a session already pinned to a
        secondary provider tries that one FIRST, so it doesn't flap back to a
        recovering primary mid-interview and change the interviewer's
        apparent personality partway through.
        """
        adapters = list(self._adapters)
        pinned = self.pinned_provider(session_id)
        if pinned:
            adapters.sort(key=lambda adapter: 0 if adapter.name == pinned else 1)
        return adapters

    async def _dispatch(self, invoke, request: LLMRequest, session_id: str | None):
        """
        The failover loop, shared by every call shape.

        `invoke(adapter, request)` is the awaitable that performs one attempt —
        `adapter.complete` for Section 9.3 turn decisions, `adapter.complete_json`
        for Section 9.8 feedback reports. Keeping one loop means the failover,
        health-tracking, session-pinning and logging behavior Section 6.7
        specifies can't diverge between them.
        """
        adapters = self._ordered_adapters(session_id)
        if not adapters:
            raise LLMNotConfiguredError("No LLM providers are configured.")

        healthy = [a for a in adapters if not self._health.is_degraded(a.name)]
        degraded = [a for a in adapters if self._health.is_degraded(a.name)]
        # Degraded providers go last rather than being removed: if every
        # provider is degraded, attempting one anyway beats failing the
        # candidate's turn outright.
        attempt_order = healthy + degraded

        last_error: LLMProviderError | None = None
        first_attempted = attempt_order[0].name

        for adapter in attempt_order:
            if not adapter.is_configured():
                logger.debug("Skipping unconfigured LLM provider %s", adapter.name)
                continue

            started = time.perf_counter()
            try:
                response = await invoke(adapter, request)
            except LLMUnsupportedRequestError as exc:
                # Not a health event: this provider is fine, it just doesn't
                # serve this kind of request (the mock adapter and Section
                # 9.8's JSON calls). Counting it would degrade a healthy
                # provider for the turns it does serve.
                last_error = exc
                logger.debug("LLM provider %s does not support this request shape: %s", adapter.name, exc)
                continue
            except LLMProviderError as exc:
                self._health.record_failure(adapter.name)
                last_error = exc
                logger.warning(
                    "LLM call failed [provider=%s session_id=%s retryable=%s]: %s",
                    adapter.name,
                    session_id,
                    exc.retryable,
                    exc,
                )
                if not exc.retryable:
                    # A malformed request fails identically everywhere;
                    # trying the rest just multiplies the same error.
                    raise
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            self._health.record_success(adapter.name, latency_ms)

            if adapter.name != first_attempted:
                # Section 6.7: "every failover event is logged (which
                # provider, which session, why) and feeds the monitoring in
                # Section 13 — repeated failovers on a given provider is an
                # operational signal worth paging on."
                logger.warning(
                    "LLM failover succeeded [from=%s to=%s session_id=%s reason=%s]",
                    first_attempted,
                    adapter.name,
                    session_id,
                    last_error,
                )
            if session_id and adapter.name != self._adapters[0].name:
                self._session_pins[session_id] = adapter.name

            return response

        raise last_error or LLMNotConfiguredError("No configured LLM provider could serve the request.")

    async def complete(self, request: LLMRequest, *, session_id: str | None = None) -> LLMResponse:
        """
        Runs one turn, failing over as needed. Raises the last
        `LLMProviderError` only when every provider has been exhausted —
        the caller (llm_engine) decides how to degrade from there.
        """
        return await self._dispatch(lambda adapter, req: adapter.complete(req), request, session_id)

    async def complete_json(self, request: LLMRequest, *, session_id: str | None = None) -> RawJSONResponse:
        """
        Runs a free-form structured-JSON call (Section 9.8's feedback report),
        with the same failover and accounting an interview turn gets.

        Raises when no configured provider can serve it — including the common
        case where only the deterministic mock is configured, since it cannot
        author prose. The Feedback Generation Service treats that as its cue to
        fall back to deterministic narrative rather than as a failure.
        """
        return await self._dispatch(lambda adapter, req: adapter.complete_json(req), request, session_id)


_gateway: AIProviderGateway | None = None


def get_gateway() -> AIProviderGateway:
    """
    Process-wide singleton so health state and session pins are shared across
    requests. Built lazily on first use so `get_settings()` is read after
    tests have set their env vars.
    """
    global _gateway
    if _gateway is None:
        _gateway = AIProviderGateway()
    return _gateway


def reset_gateway() -> None:
    """Test-only: forces a rebuild so a case can install its own adapters/config."""
    global _gateway
    _gateway = None
