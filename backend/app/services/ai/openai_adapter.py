"""
OpenAI adapter — written and complete, unconfigured by default.

Set `MOCKMATEAI_LLM_PROVIDER_ORDER=openai,mock` and
`MOCKMATEAI_LLM_API_KEY=<key>` to activate. Requires `pip install openai`.

Section 6.7 names OpenAI as the example primary provider, so this exists to
prove the gateway abstraction actually holds across providers with different
native shapes — notably:

- OpenAI takes the system prompt as a `role: "system"` MESSAGE, where
  Anthropic takes a separate top-level `system` parameter.
- Strict JSON is `response_format={"type": "json_schema", ...}` with a
  `strict: true` flag, not Anthropic's `output_config.format`.
- `temperature` IS accepted here (unlike Claude Opus 5, where it 400s), so
  it's set low for output stability. That divergence living inside the
  adapter — rather than leaking into the engine — is the whole point of the
  interface.
- Usage arrives as `prompt_tokens`/`completion_tokens`, already including
  cached tokens, so no re-adding is needed (contrast the Anthropic adapter).
"""
import logging

from app.config import get_settings
from app.services.ai.anthropic_adapter import build_json_repair_hint
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

logger = logging.getLogger("mockmateai.ai.openai")


class OpenAIAdapter(LLMAdapter):
    name = "openai"

    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.llm_api_key
        self._model = settings.resolved_openai_model
        self._base_url = settings.resolved_openai_base_url
        self._strict_json = settings.openai_supports_strict_json
        self._timeout = settings.llm_request_timeout_seconds
        self._client = None

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise LLMNotConfiguredError(
                "The 'openai' package is not installed. Run: pip install openai",
                provider=self.name,
            ) from exc

        # `base_url` is what turns this from "the OpenAI adapter" into "the
        # OpenAI-protocol adapter". Groq, OpenRouter, Cerebras, Together and a
        # local Ollama all speak the same wire format, so pointing the client
        # elsewhere is the entire integration -- no second adapter, no second
        # code path to keep in step with this one.
        kwargs: dict = {"api_key": self._api_key, "timeout": self._timeout, "max_retries": 1}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def _invoke(self, request: LLMRequest) -> tuple[str, TokenUsage, str]:
        """One OpenAI call, normalized to (text, usage, model) — see the Anthropic adapter's note."""
        if not self.is_configured():
            raise LLMNotConfiguredError("No OpenAI API key configured.", provider=self.name)

        import openai

        client = self._get_client()

        messages = [{"role": "system", "content": request.system_prompt}]
        messages.extend({"role": m["role"], "content": m["content"]} for m in request.conversation)

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "temperature": 0.3,
        }
        if request.json_schema is not None:
            if self._strict_json:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.schema_name,
                        "strict": True,
                        "schema": request.json_schema,
                    },
                }
            else:
                """
                Compatible hosts mostly do not implement `strict: true`, and
                they REJECT the request rather than ignoring the flag -- so
                sending it blind turns every evaluation into a 400, and the
                gateway then fails over to the mock adapter. The interview
                keeps working and quietly stops being intelligent, which is the
                worst possible failure shape.

                `json_object` is near-universal, and the schema itself goes
                into the system prompt via the shared repair hint, so the
                contract is still stated even though it is no longer enforced
                by the API. The engine already validates what comes back, so an
                unenforced schema is a retry rather than a corrupt report.
                """
                kwargs["response_format"] = {"type": "json_object"}
                messages[0] = {
                    "role": "system",
                    "content": request.system_prompt + chr(10) + chr(10)
                    + build_json_repair_hint(request.json_schema),
                }

        try:
            response = await client.chat.completions.create(**kwargs)
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError(str(exc), provider=self.name) from exc
        except openai.RateLimitError as exc:
            raise LLMRateLimitError(str(exc), provider=self.name) from exc
        except openai.APIConnectionError as exc:
            raise LLMConnectionError(str(exc), provider=self.name) from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMServiceError(str(exc), provider=self.name) from exc
            raise LLMPermanentError(f"OpenAI rejected the request ({exc.status_code}): {exc}", provider=self.name) from exc

        choice = response.choices[0]
        if getattr(choice, "finish_reason", None) == "content_filter":
            raise LLMRefusalError("OpenAI content filter declined the request.", provider=self.name)

        text = choice.message.content or ""
        if not text.strip():
            raise LLMServiceError("OpenAI returned no text content.", provider=self.name)

        usage = response.usage
        token_usage = TokenUsage(
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
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
