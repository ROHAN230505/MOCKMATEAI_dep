"""Adapter interface every LLM provider implements (Section 6.7)."""
import abc
import json

from app.services.ai.contracts import LLMRequest, LLMResponse, RawJSONResponse, TurnDecisionResult
from app.services.ai.errors import LLMInvalidResponseError, LLMUnsupportedRequestError


class LLMAdapter(abc.ABC):
    """
    One implementation per provider. The gateway only ever sees this
    interface, so adding a provider means adding a file here and a name to
    `MOCKMATEAI_LLM_PROVIDER_ORDER` — no orchestrator changes (Section 6.7:
    provider order/choice changes without a redeploy).
    """

    name: str

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """False when the API key/SDK is absent, so the gateway can skip to the next provider."""

    @abc.abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Run one turn. Must raise an `LLMProviderError` subclass on failure, never a provider-native exception."""

    async def complete_json(self, request: LLMRequest) -> RawJSONResponse:
        """
        Run a free-form structured-JSON call, for callers whose contract isn't
        Section 9.3's turn decision — currently the Feedback Generation Service
        (Section 9.8).

        Not abstract: an adapter that only does interview turns stays valid and
        the gateway simply moves past it (see `LLMUnsupportedRequestError`).
        Real provider adapters override this.
        """
        raise LLMUnsupportedRequestError(
            f"The {self.name} provider does not serve free-form JSON requests.", provider=self.name
        )

    @staticmethod
    def parse_json_object(raw_text: str) -> dict:
        """
        Strict-JSON parsing shared by every adapter and every call shape.

        Tolerates a fenced ```json block since some providers wrap JSON in
        markdown even when asked not to — the surrounding fence is a
        formatting artifact, not a contract violation worth failing a turn
        over.
        """
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1] if "\n" in text else text
            if text.endswith("```"):
                text = text[: -3]
            text = text.strip()

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMInvalidResponseError(f"Model did not return valid JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise LLMInvalidResponseError("Model returned JSON that is not an object.")
        return payload

    @classmethod
    def parse_turn_decision(cls, raw_text: str) -> TurnDecisionResult:
        """
        Shared validation of Section 9.3's output contract (and Section 12.8's
        clamp-don't-trust rule). Every adapter routes its raw model output
        through this, so validation is provably identical across providers
        rather than reimplemented per adapter.
        """
        payload = cls.parse_json_object(raw_text)
        try:
            return TurnDecisionResult.model_validate(payload)
        except Exception as exc:
            raise LLMInvalidResponseError(f"Model JSON did not match the required schema: {exc}") from exc
