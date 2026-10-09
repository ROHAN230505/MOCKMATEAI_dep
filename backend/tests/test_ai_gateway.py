"""
AI Provider Gateway tests (Section 6.7) — failover, session pinning, health
tracking, and the JSON output contract every adapter must satisfy.

Uses stub adapters rather than real providers, per Section 15's "don't hit
real paid AI APIs in CI".
"""
import pytest

from app.services.ai.base import LLMAdapter
from app.services.ai.contracts import (
    InternalEvaluation,
    LLMRequest,
    LLMResponse,
    TokenUsage,
    TurnDecision,
    TurnDecisionResult,
)
from app.services.ai.errors import (
    LLMInvalidResponseError,
    LLMPermanentError,
    LLMRateLimitError,
    LLMServiceError,
)
from app.services.ai.gateway import AIProviderGateway
from app.services.ai.health import ProviderHealthTracker


def _ok_response(provider: str) -> LLMResponse:
    return LLMResponse(
        result=TurnDecisionResult(
            decision=TurnDecision.NEXT_QUESTION,
            utterance="Next question.",
            internal_evaluation=InternalEvaluation(relevance_score=7, completeness_score=7),
        ),
        usage=TokenUsage(prompt_tokens=100, completion_tokens=20),
        provider=provider,
        model=f"{provider}-model",
    )


class StubAdapter(LLMAdapter):
    """Configurable stand-in: raises `error` if set, otherwise succeeds."""

    def __init__(self, name: str, *, error: Exception | None = None, configured: bool = True):
        self.name = name
        self.error = error
        self.configured = configured
        self.calls = 0

    def is_configured(self) -> bool:
        return self.configured

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return _ok_response(self.name)


def _gateway(*adapters: LLMAdapter) -> AIProviderGateway:
    gateway = AIProviderGateway()
    gateway._adapters = list(adapters)
    gateway._session_pins = {}
    gateway._health = ProviderHealthTracker(degraded_after=3, cooldown_seconds=60.0)
    return gateway


REQUEST = LLMRequest(system_prompt="sys", conversation=[{"role": "user", "content": "hi"}])


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_primary_serves_when_healthy():
    primary, fallback = StubAdapter("primary"), StubAdapter("fallback")
    response = await _gateway(primary, fallback).complete(REQUEST, session_id="s1")
    assert response.provider == "primary"
    assert fallback.calls == 0


@pytest.mark.anyio
async def test_fails_over_to_the_next_provider_on_a_retryable_error():
    """Section 6.7: retry "the **same request** against the next provider in the fallback order"."""
    primary = StubAdapter("primary", error=LLMServiceError("503", provider="primary"))
    fallback = StubAdapter("fallback")
    response = await _gateway(primary, fallback).complete(REQUEST, session_id="s1")
    assert response.provider == "fallback"
    assert primary.calls == 1 and fallback.calls == 1


@pytest.mark.anyio
async def test_does_not_fail_over_on_a_permanent_error():
    """A malformed request fails identically everywhere; retrying multiplies the same error."""
    primary = StubAdapter("primary", error=LLMPermanentError("400 bad request", provider="primary"))
    fallback = StubAdapter("fallback")

    with pytest.raises(LLMPermanentError):
        await _gateway(primary, fallback).complete(REQUEST, session_id="s1")
    assert fallback.calls == 0


@pytest.mark.anyio
async def test_unconfigured_providers_are_skipped():
    unconfigured = StubAdapter("anthropic", configured=False)
    mock = StubAdapter("mock")
    response = await _gateway(unconfigured, mock).complete(REQUEST, session_id="s1")
    assert response.provider == "mock"
    assert unconfigured.calls == 0


@pytest.mark.anyio
async def test_session_stays_pinned_to_the_fallback_provider():
    """
    Section 6.7's session consistency: "once a session has failed over to a
    secondary provider, prefer staying on it for the rest of that session
    rather than flapping back and forth on transient blips".
    """
    primary = StubAdapter("primary", error=LLMServiceError("503", provider="primary"))
    fallback = StubAdapter("fallback")
    gateway = _gateway(primary, fallback)

    first = await gateway.complete(REQUEST, session_id="s1")
    assert first.provider == "fallback"
    assert gateway.pinned_provider("s1") == "fallback"

    # Primary recovers mid-session — the pinned session must not flap back.
    primary.error = None
    second = await gateway.complete(REQUEST, session_id="s1")
    assert second.provider == "fallback"
    assert primary.calls == 1, "a pinned session should not retry the recovered primary"


@pytest.mark.anyio
async def test_a_new_session_fails_back_to_the_primary():
    """Section 6.7: "only fail back to the primary on the *next new* session"."""
    primary = StubAdapter("primary", error=LLMServiceError("503", provider="primary"))
    fallback = StubAdapter("fallback")
    gateway = _gateway(primary, fallback)

    await gateway.complete(REQUEST, session_id="old")
    primary.error = None

    response = await gateway.complete(REQUEST, session_id="brand-new")
    assert response.provider == "primary"


@pytest.mark.anyio
async def test_release_session_clears_the_pin():
    primary = StubAdapter("primary", error=LLMServiceError("503", provider="primary"))
    gateway = _gateway(primary, StubAdapter("fallback"))
    await gateway.complete(REQUEST, session_id="s1")
    assert gateway.pinned_provider("s1") == "fallback"

    gateway.release_session("s1")
    assert gateway.pinned_provider("s1") is None


@pytest.mark.anyio
async def test_all_providers_failing_raises_rather_than_hanging():
    primary = StubAdapter("primary", error=LLMServiceError("503", provider="primary"))
    fallback = StubAdapter("fallback", error=LLMRateLimitError("429", provider="fallback"))

    with pytest.raises(LLMRateLimitError):
        await _gateway(primary, fallback).complete(REQUEST, session_id="s1")


@pytest.mark.anyio
async def test_degraded_provider_is_tried_last_but_still_tried():
    """
    A degraded provider is de-prioritised, not removed: if every provider is
    degraded, attempting one still beats failing the candidate's turn.
    """
    primary, fallback = StubAdapter("primary"), StubAdapter("fallback")
    gateway = _gateway(primary, fallback)
    gateway.health.mark_degraded("primary")

    response = await gateway.complete(REQUEST, session_id="s1")
    assert response.provider == "fallback"

    gateway.health.mark_degraded("fallback")
    # Both degraded — a turn must still be served.
    assert (await gateway.complete(REQUEST, session_id="s2")).provider in {"primary", "fallback"}


# --------------------------------------------------------------------------
# Health tracking (Section 6.7)
# --------------------------------------------------------------------------


def test_provider_marked_degraded_after_consecutive_failures():
    tracker = ProviderHealthTracker(degraded_after=3, cooldown_seconds=60.0)
    for _ in range(2):
        tracker.record_failure("p")
    assert not tracker.is_degraded("p")

    tracker.record_failure("p")  # third consecutive
    assert tracker.is_degraded("p")


def test_a_success_resets_the_consecutive_failure_count():
    tracker = ProviderHealthTracker(degraded_after=3, cooldown_seconds=60.0)
    tracker.record_failure("p")
    tracker.record_failure("p")
    tracker.record_success("p", latency_ms=100)
    tracker.record_failure("p")
    assert not tracker.is_degraded("p"), "the streak should have been broken by the success"


def test_health_snapshot_reports_error_rate():
    tracker = ProviderHealthTracker()
    tracker.record_success("p", latency_ms=50)
    tracker.record_failure("p")
    snapshot = tracker.snapshot()["p"]
    assert snapshot["totalCalls"] == 2
    assert snapshot["totalFailures"] == 1
    assert snapshot["errorRate"] == 0.5


# --------------------------------------------------------------------------
# The strict JSON output contract (Section 9.3) + score clamping (Section 12.8)
# --------------------------------------------------------------------------


def test_parses_a_valid_turn_decision():
    parsed = LLMAdapter.parse_turn_decision(
        '{"decision": "followup", "utterance": "Tell me more.", '
        '"internal_evaluation": {"relevance_score": 4, "completeness_score": 3, "reasoning": "vague"}}'
    )
    assert parsed.decision == TurnDecision.FOLLOWUP
    assert parsed.internal_evaluation.relevance_score == 4


def test_tolerates_a_markdown_fenced_response():
    """Some providers fence JSON even when told not to; a fence is formatting, not a contract breach."""
    parsed = LLMAdapter.parse_turn_decision(
        '```json\n{"decision": "next_question", "utterance": "Next.", "internal_evaluation": null}\n```'
    )
    assert parsed.decision == TurnDecision.NEXT_QUESTION


def test_rejects_non_json():
    with pytest.raises(LLMInvalidResponseError):
        LLMAdapter.parse_turn_decision("Sure! Here's my question: what's a hash map?")


def test_rejects_an_unknown_decision_value():
    with pytest.raises(LLMInvalidResponseError):
        LLMAdapter.parse_turn_decision('{"decision": "end_interview", "utterance": "Bye."}')


def test_out_of_range_scores_are_clamped_not_trusted():
    """
    Section 12.8: "validate that `internal_evaluation` outputs stay within
    expected schema/ranges server-side regardless of what the LLM returns, and
    clamp/reject out-of-range scores rather than trusting the model blindly."
    """
    parsed = LLMAdapter.parse_turn_decision(
        '{"decision": "next_question", "utterance": "Next.", '
        '"internal_evaluation": {"relevance_score": 9999, "completeness_score": -50, "reasoning": "x"}}'
    )
    assert parsed.internal_evaluation.relevance_score == 10
    assert parsed.internal_evaluation.completeness_score == 0


def test_non_numeric_scores_become_null_rather_than_crashing():
    parsed = LLMAdapter.parse_turn_decision(
        '{"decision": "next_question", "utterance": "Next.", '
        '"internal_evaluation": {"relevance_score": "excellent", "completeness_score": null, "reasoning": null}}'
    )
    assert parsed.internal_evaluation.relevance_score is None


# --- Provider resolution from keys (the "just paste a key" path) -----------
#
# These matter more than they look. The gap they close is a *silent* one: with
# a key present but the chain not naming its provider, the app ran the
# deterministic mock and looked completely healthy while doing it -- same
# templated follow-up every turn, no error anywhere. So each case below is a
# way that used to end in "why is my API key doing nothing".


def _settings(**overrides):
    """
    A Settings instance for testing resolution logic.

    `llm_provider_order` and the key slots are defaulted explicitly because
    conftest pins them in the environment -- deliberately, so no test can make
    a live API call. Without restating them here, every one of these
    assertions would be testing that pin rather than the resolver it names.
    """
    from app.config import Settings

    overrides.setdefault("llm_provider_order", "auto")
    for slot in ("llm_api_key", "llm_fallback_api_key_1", "llm_fallback_api_key_2"):
        overrides.setdefault(slot, "")
    return Settings(cors_allowed_origins="http://localhost:5173", **overrides)


def test_no_keys_resolves_to_mock_only():
    assert [name for name, _ in _settings().llm_provider_chain] == ["mock"]


def test_an_anthropic_key_is_recognised_by_its_prefix():
    chain = _settings(llm_api_key="sk-ant-api03-example").llm_provider_chain
    assert [name for name, _ in chain] == ["anthropic", "mock"]


def test_an_openai_key_is_recognised_by_its_prefix():
    chain = _settings(llm_api_key="sk-proj-example").llm_provider_chain
    assert [name for name, _ in chain] == ["openai", "mock"]


def test_anthropic_is_matched_before_openai():
    """
    `sk-ant-` starts with `sk-`, so order of testing decides this. Reversed,
    every Anthropic key would be handed to OpenAI and rejected at request time
    -- a confusing place to discover a config problem.
    """
    provider, _ = _settings(llm_api_key="sk-ant-api03-example").llm_provider_chain[0]
    assert provider == "anthropic"


def test_a_key_in_a_fallback_slot_still_gets_used_and_keeps_its_key():
    """The exact trap positional pairing had: the key was found, the provider
    got an empty string, and the turn fell through to mock in silence."""
    chain = _settings(llm_fallback_api_key_1="sk-ant-api03-example").llm_provider_chain
    assert chain[0] == ("anthropic", "sk-ant-api03-example")


def test_two_providers_become_a_failover_chain():
    chain = _settings(
        llm_api_key="sk-ant-api03-example",
        llm_fallback_api_key_1="sk-proj-example",
    ).llm_provider_chain
    assert [name for name, _ in chain] == ["anthropic", "openai", "mock"]


def test_a_second_key_for_the_same_provider_is_not_a_second_provider():
    """Retrying the same provider back-to-back only doubles an outage's latency."""
    chain = _settings(
        llm_api_key="sk-ant-first",
        llm_fallback_api_key_1="sk-ant-second",
    ).llm_provider_chain
    assert [name for name, _ in chain] == ["anthropic", "mock"]


def test_an_unrecognised_key_degrades_to_mock_rather_than_guessing():
    """A placeholder left in .env must not be posted to a provider."""
    assert [name for name, _ in _settings(llm_api_key="your-key-here").llm_provider_chain] == ["mock"]


def test_an_explicit_order_overrides_key_detection():
    """Pinning the chain is a deployment decision and has to keep winning."""
    chain = _settings(
        llm_provider_order="openai",
        llm_api_key="sk-ant-api03-example",
    ).llm_provider_chain
    assert [name for name, _ in chain] == ["openai", "mock"]


def test_mock_is_appended_to_an_explicit_chain_that_omits_it():
    chain = _settings(llm_provider_order="anthropic", llm_api_key="sk-ant-x").llm_provider_chain
    assert chain[-1][0] == "mock"


def test_an_explicit_chain_pairs_keys_positionally():
    chain = _settings(
        llm_provider_order="anthropic,openai",
        llm_api_key="key-a",
        llm_fallback_api_key_1="key-b",
    ).llm_provider_chain
    assert chain[0] == ("anthropic", "key-a")
    assert chain[1] == ("openai", "key-b")


def test_the_gateway_builds_adapters_from_the_resolved_chain(monkeypatch):
    """
    End to end: the gateway's adapters come from `llm_provider_chain`, not from
    splitting the raw setting. Asserted with a key in a FALLBACK slot and no
    explicit order -- the combination that used to yield mock alone.
    """
    import app.config as config_module

    resolved = _settings(llm_fallback_api_key_1="sk-ant-api03-example")
    monkeypatch.setattr(config_module, "get_settings", lambda: resolved)
    monkeypatch.setattr("app.services.ai.gateway.get_settings", lambda: resolved)

    gateway = AIProviderGateway()
    assert gateway.provider_names() == ["anthropic", "mock"]


# --- OpenAI-protocol hosts (Groq, OpenRouter, Ollama, ...) -----------------
#
# The whole point of these: a Groq key is not "an OpenAI key that happens to
# work". It is the same wire protocol at a different host with a different
# model catalogue and a smaller feature set, and every one of those three
# differences has a silent failure mode if it is got wrong -- a 401 from the
# wrong host, a 404 for `gpt-4o`, or a 400 for `strict: true` that makes the
# gateway fall back to mock while the interview appears to carry on working.


def test_a_groq_key_is_recognised():
    chain = _settings(llm_api_key="gsk_exampleexample").llm_provider_chain
    assert [name for name, _ in chain] == ["openai", "mock"]


def test_a_groq_key_points_the_client_at_groq():
    assert _settings(llm_api_key="gsk_x").resolved_openai_base_url == "https://api.groq.com/openai/v1"


def test_an_openai_key_keeps_the_sdk_default_host():
    assert _settings(llm_api_key="sk-proj-x").resolved_openai_base_url == ""


def test_the_model_follows_the_host():
    """
    `gpt-4o` is a 404 on Groq and Groq's own ids are a 404 on OpenAI, so the
    default cannot be one constant.

    Asserted as "the two hosts disagree" rather than against a literal id,
    because Groq retires models without notice -- the id this test originally
    named stopped existing within months, and a test pinned to it would have
    failed for a reason that had nothing to do with the code it covers.
    """
    groq = _settings(llm_api_key="gsk_x").resolved_openai_model
    openai = _settings(llm_api_key="sk-x").resolved_openai_model
    assert openai == "gpt-4o"
    assert groq and groq != openai


def test_an_explicit_model_always_wins():
    st = _settings(llm_api_key="gsk_x", openai_model="llama-3.1-8b-instant")
    assert st.resolved_openai_model == "llama-3.1-8b-instant"


def test_an_explicit_base_url_reaches_any_compatible_host():
    """The OpenRouter/Cerebras/Ollama path: one setting, no new adapter."""
    st = _settings(llm_api_key="sk-or-x", openai_base_url="https://openrouter.ai/api/v1")
    assert st.resolved_openai_base_url == "https://openrouter.ai/api/v1"


def test_strict_json_is_claimed_only_for_openai_itself():
    """
    The costly one to get wrong. A compatible host REJECTS `strict: true`
    rather than ignoring it, so every evaluation 400s and the gateway quietly
    degrades to mock -- an interview that still runs but has stopped thinking.
    """
    assert _settings(llm_api_key="sk-x").openai_supports_strict_json is True
    assert _settings().openai_supports_strict_json is True
    assert _settings(llm_api_key="gsk_x").openai_supports_strict_json is False
    assert _settings(
        llm_api_key="sk-or-x", openai_base_url="https://openrouter.ai/api/v1"
    ).openai_supports_strict_json is False


def test_a_groq_key_in_a_fallback_slot_still_selects_groq():
    assert _settings(llm_fallback_api_key_1="gsk_x").resolved_openai_base_url.endswith("groq.com/openai/v1")
