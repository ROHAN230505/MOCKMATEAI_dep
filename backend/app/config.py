"""
Centralized application configuration.

All settings are sourced from environment variables prefixed ``MOCKMATEAI_``
per Section 20/21.1 of MASTER_PROMPT.md. Never hardcode secrets here — this
module only defines shape and safe local-dev defaults; real deployments
supply values via a secrets manager / environment, never a committed .env.
"""
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MOCKMATEAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Environment ---
    env: Literal["development", "staging", "production"] = "development"

    # --- Datastores ---
    db_url: str = "postgresql+psycopg://mockmateai:mockmateai@localhost:5432/mockmateai"
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_redis_url: str | None = None  # falls back to redis_url if unset

    # --- JWT (Section 12.1 — RS256, short-lived access / rotated refresh) ---
    # Paths work locally, where the keypair is a pair of files. They do not
    # work on a platform that deploys from git, because the keys are secrets
    # and are therefore not in git -- so the PEM itself can be supplied
    # directly instead, and takes precedence. See `security._load_private_key`.
    jwt_private_key_path: str = "./dev_keys/jwt_private.pem"
    jwt_public_key_path: str = "./dev_keys/jwt_public.pem"
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    jwt_algorithm: str = "RS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30
    # Server-side pepper mixed into refresh-token hashing (HMAC key) so a raw
    # DB leak of `refresh_tokens.token_hash` alone can't be used to forge a
    # match without also having this secret.
    refresh_token_secret: str = "dev-only-insecure-refresh-secret-change-me"

    # --- Password reset ---
    password_reset_token_expire_minutes: int = 30

    # --- Google OAuth (Section 6.5 / 12.10) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    # Where the backend sends the browser after completing the Google
    # handshake (see routers/auth_google.py for why a one-time ticket is
    # used instead of putting tokens directly in the redirect URL).
    frontend_url: str = "http://localhost:5173"

    # --- CORS (Section 12.7 — explicit allowlist, never "*") ---
    cors_allowed_origins: str = "http://localhost:5173"

    # --- Rate limiting (Section 12.1A) ---
    rate_limit_storage_uri: str | None = None  # defaults to rate_limit_redis_url/redis_url

    # --- Recording retention (schema-only in Phase 1, used from Phase 5+) ---
    recording_retention_days: int = 90

    # --- LLM providers (Section 6.7 — "defined in config, not code, so
    # provider order/choice can change without a redeploy") ---
    # Ordered failover chain. `mock` is a real, deterministic adapter (see
    # services/ai/mock_adapter.py), kept last so a provider outage degrades
    # to a working-but-unintelligent interview rather than a dead session.
    # "auto" resolves the chain from whichever keys are actually present --
    # see `llm_provider_chain`. An explicit list still wins, because pinning
    # the order is a legitimate deployment decision.
    llm_provider_order: str = "auto"
    llm_api_key: str = ""  # primary provider
    llm_fallback_api_key_1: str = ""
    llm_fallback_api_key_2: str = ""

    # Model IDs per provider. Anthropic's default is Claude Opus 5 — do not
    # downgrade for cost without an explicit decision; that's a deployment
    # choice, which is why it's config.
    anthropic_model: str = "claude-opus-5"
    # Left blank to be resolved from the key -- see `resolved_openai_model`.
    # An explicit value always wins.
    openai_model: str = ""
    # Any OpenAI-protocol endpoint. Blank resolves from the key prefix, so a
    # Groq key alone is enough to reach Groq. An explicit value always wins,
    # which is what makes OpenRouter, Cerebras, Together and a local Ollama
    # reachable without another line of code.
    openai_base_url: str = ""

    # Section 14's "< 2 seconds perceived latency" budget is the binding
    # constraint on a live interview turn, so effort defaults low. Raise for
    # better evaluation quality at the cost of latency.
    llm_effort: str = "low"
    llm_request_timeout_seconds: float = 12.0
    # Section 6.7: "3 consecutive timeouts or >2x normal p95 latency".
    llm_degraded_after_consecutive_failures: int = 3
    llm_degraded_cooldown_seconds: float = 60.0

    # --- LLM token/cost governance (Section 9.3A) ---
    llm_max_tokens_per_turn: int = 500  # raw transcript tokens accepted per answer
    llm_max_output_tokens: int = 4096  # caps thinking + response on thinking-capable models
    # Per-session ceiling "scaled to the session's selected duration" —
    # multiplied by duration_minutes at runtime (see ai/tokens.py).
    llm_max_tokens_per_session_per_minute: int = 4000
    # Compaction threshold: once cumulative session tokens cross this
    # fraction of the ceiling, older turns are summarized instead of sent
    # verbatim (Section 9.3A) rather than hard-failing mid-interview.
    llm_compaction_threshold_ratio: float = 0.6
    llm_full_turns_kept_when_compacting: int = 4
    # Runaway-loop backstop: total LLM calls per session (Section 9.3A).
    llm_max_calls_per_session: int = 40

    # --- AI-cost-sensitive quota (Section 12.1A) ---
    ai_daily_interview_minutes_per_user: int = 180
    # Section 12.1A's export tier: transcript/PDF downloads, per user per hour.
    exports_per_hour_per_user: int = 20
    # Section 12.1A names hints per day as an AI-cost-sensitive quota
    # alongside interview minutes and resume analyses. Generous enough that
    # nobody practising in good faith meets it, low enough that a loop cannot
    # spend the account's provider budget on nudges.
    dsa_hints_per_day_per_user: int = 40
    # The third quota Section 12.1A names by example, alongside interview
    # minutes and hints.
    resume_analyses_per_day_per_user: int = 20

    # --- Optional hardening toggles ---
    # Off by default: calls an external k-anonymity API (e.g. HIBP) at signup
    # time. Real, working implementation lives in core/security.py, gated by
    # this flag so local dev/tests never depend on outbound network access.
    enable_breached_password_check: bool = False

    @field_validator("db_url")
    @classmethod
    def _psycopg_driver(cls, v: str) -> str:
        # Hosted Postgres (Render, Neon, Heroku) hands out `postgresql://` or
        # `postgres://`, which SQLAlchemy resolves to psycopg2 -- not installed.
        # Naming the driver here means the URL can be pasted as given.
        for scheme in ("postgresql://", "postgres://"):
            if v.startswith(scheme):
                return "postgresql+psycopg://" + v[len(scheme):]
        return v

    @field_validator("cors_allowed_origins")
    @classmethod
    def _non_empty_origins(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("MOCKMATEAI_CORS_ALLOWED_ORIGINS must not be empty")
        return v

    @field_validator("llm_provider_order")
    @classmethod
    def _non_empty_provider_order(cls, v: str) -> str:
        if not [p for p in v.split(",") if p.strip()]:
            raise ValueError("MOCKMATEAI_LLM_PROVIDER_ORDER must name at least one provider")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def llm_provider_list(self) -> list[str]:
        return [p.strip().lower() for p in self.llm_provider_order.split(",") if p.strip()]

    @staticmethod
    def _provider_for_key(api_key: str) -> str | None:
        """
        Which provider a key belongs to, by prefix.

        Anthropic keys are `sk-ant-...`; OpenAI's are `sk-...` (including
        `sk-proj-...`). The Anthropic test has to come first because its prefix
        is a superset of OpenAI's -- reversed, every Anthropic key would be
        handed to OpenAI and rejected as malformed at request time rather than
        at startup, which is a needlessly confusing place to find out.

        Returns None for anything unrecognised, so a typo'd or placeholder key
        degrades to `mock` instead of being sent somewhere it cannot work.
        """
        key = api_key.strip()
        if not key:
            return None
        if key.startswith("sk-ant-"):
            return "anthropic"
        # Groq speaks the OpenAI protocol, so it *is* the openai adapter -- only
        # pointed at a different host. Handled before the bare `sk-` test
        # because its prefix is unrelated, not a superset.
        if key.startswith("gsk_"):
            return "openai"
        if key.startswith("sk-"):
            return "openai"
        return None

    @property
    def llm_provider_chain(self) -> list[tuple[str, str]]:
        """
        The resolved (provider, api_key) chain, in attempt order.

        Two modes, and the reason for the second is ergonomic rather than
        architectural: with an explicit `llm_provider_order`, keys pair
        positionally against it, which is Section 21.1's env layout and stays
        exactly as it was. With the default "auto", the chain is derived from
        whichever keys are present -- so adding a key is the *only* step needed
        to switch off the deterministic mock, with no second setting to get
        wrong and no way for the order and the keys to disagree.

        Pairing is returned rather than left to the caller because the
        positional version had a real trap in it: a key placed in
        `llm_fallback_api_key_1` while the order named one provider would hand
        that provider an empty string and silently fall through to `mock`.

        `mock` is always last. It needs no key and it is what makes a missing,
        expired or rate-limited provider degrade to a working-but-unintelligent
        interview instead of a dead session.
        """
        keys = [self.llm_api_key, self.llm_fallback_api_key_1, self.llm_fallback_api_key_2]
        explicit = self.llm_provider_list

        if explicit != ["auto"]:
            chain = [
                (name, keys[index] if index < len(keys) else "")
                for index, name in enumerate(explicit)
            ]
            if not any(name == "mock" for name, _ in chain):
                chain.append(("mock", ""))
            return chain

        chain: list[tuple[str, str]] = []
        for key in keys:
            provider = self._provider_for_key(key)
            # One adapter per provider: a second Anthropic key is a spare, not
            # a second provider, and retrying the same provider twice in a row
            # just doubles the latency of an outage.
            if provider is not None and all(name != provider for name, _ in chain):
                chain.append((provider, key.strip()))
        chain.append(("mock", ""))
        return chain

    @property
    def resolved_openai_base_url(self) -> str:
        """
        Which OpenAI-protocol host to talk to.

        Explicit setting first, then inferred from the key. The inference is
        what lets "paste a key and it works" hold for a provider the code has
        never heard of by name -- the adapter is unchanged, only its base URL
        moves. Empty string means the SDK default, api.openai.com.
        """
        if self.openai_base_url.strip():
            return self.openai_base_url.strip()
        if self.llm_api_key.strip().startswith("gsk_"):
            return "https://api.groq.com/openai/v1"
        for key in (self.llm_fallback_api_key_1, self.llm_fallback_api_key_2):
            if key.strip().startswith("gsk_"):
                return "https://api.groq.com/openai/v1"
        return ""

    @property
    def resolved_openai_model(self) -> str:
        """
        Which model to ask for, given the host.

        `gpt-4o` is meaningless to Groq and vice versa, so the default has to
        follow the endpoint rather than be a constant. An explicit
        MOCKMATEAI_OPENAI_MODEL always wins, which is how you pick a different
        Groq model or an OpenRouter one.
        """
        if self.openai_model.strip():
            return self.openai_model.strip()
        if "groq.com" in self.resolved_openai_base_url:
            # Groq rotates its catalogue and retires models without notice --
            # the Llama id that was the obvious default here stopped existing
            # and returned a 404 that looks like an auth problem. So treat this
            # as a *current* best guess rather than a constant, and expect to
            # override it: `MOCKMATEAI_OPENAI_MODEL` is the escape hatch, and
            # the account's live list is one call away (see the 404 handler).
            return "openai/gpt-oss-120b"
        return "gpt-4o"

    @property
    def openai_supports_strict_json(self) -> bool:
        """
        Whether the endpoint honours `response_format: json_schema` with
        `strict: true`.

        OpenAI does. Most OpenAI-*compatible* hosts do not, and reject the
        whole request rather than degrading -- so sending it blind turns every
        evaluation into a 400 and silently drops the interview back to the mock
        adapter. Those hosts get `json_object` plus the schema in the prompt,
        which the adapter already knows how to do.
        """
        base = self.resolved_openai_base_url
        return not base or "api.openai.com" in base

    @property
    def effective_redis_url(self) -> str:
        return self.rate_limit_redis_url or self.redis_url

    @property
    def effective_rate_limit_storage_uri(self) -> str:
        return self.rate_limit_storage_uri or self.effective_redis_url

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    """Settings are cached for process lifetime; tests override via dependency_overrides."""
    return Settings()
