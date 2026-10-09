"""
Anthropic (Claude) adapter — written and complete, unconfigured by default.

Set `MOCKMATEAI_LLM_PROVIDER_ORDER=anthropic,mock` and
`MOCKMATEAI_LLM_API_KEY=<key>` to activate. Requires `pip install anthropic`.

Model-specific details that are easy to get wrong on Claude Opus 5 (the
configured default) and cost a 400 or a silent quality regression:

- `temperature` / `top_p` / `top_k` are REMOVED — sending any of them is a
  400. Response style is steered by prompting only. This is why the engine's
  system prompt carries explicit style rules instead of a low temperature.
- `max_tokens` caps thinking + response text TOGETHER. Thinking is on by
  default on Opus 5, so a `max_tokens` sized tightly around the JSON answer
  truncates mid-response. Hence the deliberately generous default.
- `output_config.effort` is the cost/latency lever, not `max_tokens`.
  Defaults to "low" here for Section 14's sub-2-second turn budget.
- Thinking is left ON (adaptive, the default). Disabling it on Opus 5 can
  leak `<thinking>` tags into the visible response, which would corrupt the
  strict-JSON contract this adapter depends on — a lower `effort` is the
  supported way to buy latency back.
- `stop_reason == "refusal"` arrives as a successful HTTP 200 with empty or
  partial content. Reading `content[0]` without checking first raises
  IndexError, so the check comes first.
- `usage.input_tokens` is the UNCACHED remainder only; the full prompt cost
  is `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.

Prompt caching: the system prompt is byte-stable for a session (the engine
guarantees this — no timestamps, no per-turn interpolation), so a
`cache_control` breakpoint on it turns every turn after the first into a
cache read at ~0.1x input cost. Tools render before system, and this adapter
sends no tools, so the breakpoint covers the whole stable prefix.
"""
import json
import logging

from app.config import get_settings
from app.services.ai.base import LLMAdapter
from app.services.ai.contracts import LLMRequest, LLMResponse, RawJSONResponse, TokenUsage
from app.services.ai.errors import (
    LLMConnectionError,
    LLMNotConfiguredError,
    LLMPermanentError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMServiceError,
    LLMTimeoutError,
)

logger = logging.getLogger("mockmateai.ai.anthropic")


class AnthropicAdapter(LLMAdapter):
    name = "anthropic"

    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.llm_api_key
        self._model = settings.anthropic_model
        self._effort = settings.llm_effort
        self._timeout = settings.llm_request_timeout_seconds
        self._client = None

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        """
        Lazily constructed so the SDK is only imported when this provider is
        actually configured — the package is an optional dependency (see
        requirements.txt), and an unconfigured provider must not break app
        startup for everyone else.
        """
        if self._client is not None:
            return self._client
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise LLMNotConfiguredError(
                "The 'anthropic' package is not installed. Run: pip install anthropic",
                provider=self.name,
            ) from exc

        self._client = AsyncAnthropic(
            api_key=self._api_key,
            timeout=self._timeout,
            # The gateway owns provider-level failover; the SDK retries only
            # transient blips within a provider. Two layers of retry would
            # multiply the worst-case latency past Section 14's budget.
            max_retries=1,
        )
        return self._client

    async def _invoke(self, request: LLMRequest) -> tuple[str, TokenUsage, str]:
        """
        One Claude call, normalized to (text, usage, model).

        Shared by `complete` (Section 9.3 turn decisions) and `complete_json`
        (Section 9.8 feedback reports) so the provider-specific handling above —
        the refusal check, the cached-token arithmetic, the error mapping —
        exists exactly once and can't drift between the two call shapes.
        """
        if not self.is_configured():
            raise LLMNotConfiguredError("No Anthropic API key configured.", provider=self.name)

        import anthropic

        client = self._get_client()

        # cache_control on the (byte-stable) system prompt — see module docstring.
        system_blocks = [
            {"type": "text", "text": request.system_prompt, "cache_control": {"type": "ephemeral"}}
        ]
        messages = [{"role": m["role"], "content": m["content"]} for m in request.conversation]

        kwargs: dict = {
            "model": self._model,
            "max_tokens": request.max_output_tokens,
            "system": system_blocks,
            "messages": messages,
            "output_config": {"effort": self._effort},
        }
        if request.json_schema is not None:
            # Provider-enforced strict JSON (Section 9.3's output contract),
            # rather than merely asking for JSON in the prompt.
            kwargs["output_config"]["format"] = {
                "type": "json_schema",
                "schema": request.json_schema,
            }

        try:
            response = await client.messages.create(**kwargs)
        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError(str(exc), provider=self.name) from exc
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError(str(exc), provider=self.name) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMConnectionError(str(exc), provider=self.name) from exc
        except anthropic.APIStatusError as exc:
            # 5xx is provider-side and worth failing over; 4xx means the
            # request itself is wrong and every provider will reject it.
            if exc.status_code >= 500:
                raise LLMServiceError(str(exc), provider=self.name) from exc
            raise LLMPermanentError(f"Anthropic rejected the request ({exc.status_code}): {exc}", provider=self.name) from exc

        # Refusal check BEFORE touching content — see module docstring.
        if getattr(response, "stop_reason", None) == "refusal":
            category = getattr(getattr(response, "stop_details", None), "category", None)
            raise LLMRefusalError(
                f"Anthropic safety classifiers declined the request (category={category}).",
                provider=self.name,
            )

        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        if not text.strip():
            raise LLMServiceError("Anthropic returned no text content.", provider=self.name)

        usage = response.usage
        cached = int(getattr(usage, "cache_creation_input_tokens", 0) or 0) + int(
            getattr(usage, "cache_read_input_tokens", 0) or 0
        )
        token_usage = TokenUsage(
            # Full prompt cost, not just the uncached remainder.
            prompt_tokens=int(usage.input_tokens or 0) + cached,
            completion_tokens=int(usage.output_tokens or 0),
            cached_prompt_tokens=cached,
        )
        return text, token_usage, getattr(response, "model", self._model)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        text, token_usage, model = await self._invoke(request)
        return LLMResponse(
            result=self.parse_turn_decision(text),
            usage=token_usage,
            provider=self.name,
            model=model,
        )

    async def complete_json(self, request: LLMRequest) -> RawJSONResponse:
        text, token_usage, model = await self._invoke(request)
        return RawJSONResponse(
            payload=self.parse_json_object(text),
            usage=token_usage,
            provider=self.name,
            model=model,
        )


def build_json_repair_hint(schema: dict) -> str:
    """
    Fallback instruction for providers/models without structured-output
    support, so the JSON contract is still stated in-prompt rather than
    silently unenforced. The engine appends this only when
    `request.json_schema` can't be enforced natively.
    """
    return (
        "Respond with a single JSON object and nothing else — no markdown fence, no prose. "
        f"It must conform exactly to this JSON Schema:\n{json.dumps(schema, indent=2)}"
    )
