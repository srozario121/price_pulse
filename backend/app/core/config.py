"""Application configuration — single source of truth for all env vars.

All downstream modules (database, Celery, logging) import `settings`
rather than reading from `os.environ` directly.

CORS_ORIGINS is read from the environment as a comma-separated string
(e.g. "http://localhost:5173,https://app.example.com") and coerced to
a list[str] by the field validator.
"""

from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Proxy URL schemes accepted in PROXY_URLS (Item 15 anti-blocking).
_PROXY_SCHEMES = ("http", "https", "socks5", "socks5h", "socks4")

# LLM providers reachable through Pydantic AI for selector generation (Item 16).
# Public because both the Settings validator and the per-product BYO credential
# API validate against the same set — one list, two boundaries.
LLM_PROVIDERS = ("openai", "anthropic", "azure", "openrouter")

# Providers whose client accepts a custom API endpoint. OpenRouter's is fixed by
# the service, and Azure carries its endpoint in AZURE_OPENAI_ENDPOINT — so
# setting LLM_BASE_URL alongside either is a configuration mistake, not a no-op.
BASE_URL_PROVIDERS = ("openai", "anthropic")


def is_azure_v1_endpoint(endpoint: str) -> bool:
    """True when *endpoint* targets Azure's v1 API (or a Foundry serverless model).

    The two Azure endpoint styles take opposite configuration, so telling them
    apart is what lets every boundary report a precise error.
    """
    return endpoint.rstrip("/").endswith("/openai/v1")


def base_url_config_error(
    provider: str,
    base_url: str | None,
    *,
    field_name: str = "LLM_BASE_URL",
) -> str | None:
    """Return why *base_url* cannot be used with *provider*, or ``None`` if it can.

    Silently ignoring a base URL the provider cannot honour would be the worst
    outcome: traffic would keep going to the public API while the operator
    believed it was routed through their gateway.
    """
    if not base_url:
        return None
    if provider not in BASE_URL_PROVIDERS:
        return (
            f"{field_name} is not supported for provider {provider!r} — only "
            f"{' and '.join(BASE_URL_PROVIDERS)} accept a custom endpoint "
            f"(OpenRouter's is fixed; Azure uses AZURE_OPENAI_ENDPOINT)"
        )
    return None


def azure_config_error(
    endpoint: str | None,
    api_version: str | None,
    *,
    endpoint_name: str = "AZURE_OPENAI_ENDPOINT",
    version_name: str = "AZURE_OPENAI_API_VERSION",
) -> str | None:
    """Return why an Azure endpoint/API-version pair is unusable, or ``None`` if it is.

    The single home for this rule, applied at all three boundaries that can
    accept Azure settings: the env admin default (``Settings``), the per-product
    BYO credential body, and model construction. The classic
    ``https://<resource>.openai.azure.com`` form *requires* an API version; the
    newer ``…/openai/v1`` form *rejects* one — so a naive "both are required"
    check would wrongly refuse valid v1 configurations. The ``*_name`` arguments
    let each caller name the fields as its own users see them.
    """
    if not endpoint:
        return f"Azure OpenAI requires {endpoint_name} to be set"
    if is_azure_v1_endpoint(endpoint):
        if api_version:
            return (
                f"{version_name} must be empty for a v1 endpoint "
                f"({endpoint_name} ending in /openai/v1), which does not accept one"
            )
        return None
    if not api_version:
        return (
            f"Azure OpenAI requires {version_name} for a classic "
            f"https://<resource>.openai.azure.com endpoint"
        )
    return None


class Settings(BaseSettings):
    """Pydantic settings loaded from environment variables (and .env file)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://price_pulse:price_pulse@localhost:5432/price_pulse"

    # ── Redis / Celery ────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = ""  # falls back to REDIS_URL when empty
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = ""

    # ── App behaviour ─────────────────────────────────────────────────────────
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    # Verify the DB schema is at the Alembic head during application startup and
    # refuse to start otherwise. Disabled by the E2E overlay, which provisions
    # its schema via create_all rather than the migration chain.
    MIGRATION_CHECK_ON_STARTUP: bool = True
    SCRAPE_INTERVAL_MINUTES: int = 30
    SCRAPE_MIN_DELAY_SECONDS: int = 2
    ALERT_COOLDOWN_HOURS: int = 24
    # Item 17: ScrapeJob rows older than this are deleted by the daily
    # ``prune_scrape_jobs`` beat task. At a 30-min cadence × every active product
    # the table grows unbounded without a prune; the default bounds it to a week.
    SCRAPE_JOB_RETENTION_DAYS: int = 7

    # ── Anti-blocking (Item 15) ───────────────────────────────────────────────
    # Bring-your-own rotating-proxy list, comma-separated in the env var
    # (e.g. "http://user:pass@host1:port,http://user:pass@host2:port"), coerced
    # to list[str] like CORS_ORIGINS. Empty ⇒ proxying disabled (direct egress).
    # A residential/rotating list is expected in production so scheduled scrapes
    # of bot-protected retailers are not single-IP and trivially bannable.
    # NoDecode: skip pydantic-settings' JSON pre-decode so the raw env string
    # (empty, or comma-separated) reaches parse_proxy_urls rather than crashing
    # json.loads on a non-JSON value.
    PROXY_URLS: Annotated[list[str], NoDecode] = []
    # Max proxy rotations per fetch when a block/CAPTCHA is detected before the
    # scrape resolves to BLOCKED/CAPTCHA. A dead/unreachable proxy rotates too
    # but does not consume this budget.
    MAX_PROXY_ROTATIONS: int = 2

    # ── LLM selector generation (Item 16) ─────────────────────────────────────
    # Admin-default LLM credentials used when a product carries no bring-your-own
    # credential. The repo has no auth/user system yet, so this deployer-level
    # default plus the per-product BYO row are the only two credential scopes.
    # Empty LLM_API_KEY ⇒ the admin default is disabled; with no product BYO
    # credential either, selector generation is a no-op and extraction falls back
    # to its existing behaviour (recording ``selector_miss``).
    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "gpt-5.2"
    LLM_API_KEY: str = ""
    # Override the provider's API endpoint — for an LLM gateway, an egress proxy,
    # or a self-hosted OpenAI-compatible server. Empty ⇒ the provider's own
    # default (https://api.openai.com/v1 for OpenAI). Only ``openai`` and
    # ``anthropic`` accept one: OpenRouter's endpoint is fixed, and Azure carries
    # its endpoint in AZURE_OPENAI_ENDPOINT instead.
    LLM_BASE_URL: str = ""
    # Azure-only — required (both) when LLM_PROVIDER=azure.
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = ""
    # Max bytes of trimmed page HTML sent to the LLM in one generation call.
    SELECTOR_HTML_MAX_BYTES: int = 120_000
    # Consecutive failed generate-and-validate attempts before a host's profile is
    # parked as ``failed`` — bounds spend on a page that can never be healed.
    SELECTOR_MAX_REGEN_ATTEMPTS: int = 3
    # Minimum hours between regeneration attempts for one host. Together with the
    # attempt budget this stops a permanently-broken page hammering the provider.
    SELECTOR_REGEN_COOLDOWN_HOURS: int = 6

    # ── E2E test hooks ────────────────────────────────────────────────────────
    # Mounts gated test-only control endpoints under /api/v1/_test/ when true.
    # MUST stay false outside the e2e docker-compose overlay — it is set to true
    # only by docker-compose.e2e.yml so the hooks never exist in production.
    E2E_TEST_HOOKS: bool = False

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Env var: comma-separated string "http://localhost:5173,https://..."
    # Defaults to ["*"] when DEBUG=True; required (non-empty) in production.
    CORS_ORIGINS: list[str] = []

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:  # noqa: ANN401
        """Accept a comma-separated string or a list; return list[str]."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return v
        return []

    @field_validator("PROXY_URLS", mode="before")
    @classmethod
    def parse_proxy_urls(cls, v: Any) -> list[str]:  # noqa: ANN401
        """Accept a comma-separated string or list; validate each proxy URL.

        A malformed entry raises here (at startup / Settings construction) rather
        than surfacing as an opaque runtime crash mid-scrape.
        """
        if isinstance(v, str):
            items = [p.strip() for p in v.split(",") if p.strip()]
        elif isinstance(v, list):
            items = [str(p).strip() for p in v if str(p).strip()]
        else:
            return []
        for entry in items:
            parsed = urlparse(entry)
            if parsed.scheme not in _PROXY_SCHEMES or not parsed.hostname:
                raise ValueError(
                    f"Invalid proxy URL in PROXY_URLS: {entry!r} — expected "
                    f"scheme://[user:pass@]host[:port] with one of {_PROXY_SCHEMES}"
                )
        return items

    @field_validator("MAX_PROXY_ROTATIONS")
    @classmethod
    def max_proxy_rotations_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("MAX_PROXY_ROTATIONS must be >= 0")
        return v

    @field_validator("SCRAPE_JOB_RETENTION_DAYS")
    @classmethod
    def scrape_job_retention_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("SCRAPE_JOB_RETENTION_DAYS must be >= 1")
        return v

    @field_validator("LLM_PROVIDER")
    @classmethod
    def llm_provider_supported(cls, v: str) -> str:
        """Reject an unknown provider at startup, not mid-scrape.

        A typo'd provider would otherwise surface only when the first selector
        regeneration runs — hours after deploy, inside a Celery worker.
        """
        provider = v.strip().lower()
        if provider not in LLM_PROVIDERS:
            raise ValueError(f"LLM_PROVIDER must be one of {LLM_PROVIDERS}, got {v!r}")
        return provider

    @field_validator("LLM_BASE_URL")
    @classmethod
    def llm_base_url_well_formed(cls, v: str) -> str:
        """Reject a malformed base URL at startup rather than on the first call."""
        url = v.strip()
        if not url:
            return ""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(
                f"LLM_BASE_URL must be an http(s) URL like "
                f"https://gateway.example.com/v1, got {v!r}"
            )
        return url

    @field_validator(
        "SELECTOR_HTML_MAX_BYTES",
        "SELECTOR_MAX_REGEN_ATTEMPTS",
        "SELECTOR_REGEN_COOLDOWN_HOURS",
    )
    @classmethod
    def selector_knobs_positive(cls, v: int, info: Any) -> int:  # noqa: ANN401
        if v < 1:
            raise ValueError(f"{info.field_name} must be >= 1")
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v

    @field_validator("CELERY_BROKER_URL", mode="before")
    @classmethod
    def default_broker_to_redis(cls, v: Any, info: Any) -> str:  # noqa: ANN401
        """Fall back to REDIS_URL when CELERY_BROKER_URL is not set."""
        if not v:
            data = info.data if hasattr(info, "data") else {}
            return str(data.get("REDIS_URL", "redis://localhost:6379/0"))
        return str(v)

    @model_validator(mode="after")
    def validate_azure_llm_config(self) -> "Settings":
        """Check the admin-default LLM endpoint settings — fail fast, not mid-scrape.

        Azure's endpoint/API-version pair is only enforced when the admin default
        is actually usable (a key is set); an unconfigured deployment that never
        generates selectors must still boot. ``LLM_BASE_URL`` is checked
        unconditionally, because a base URL set against a provider that cannot
        honour it is a mistake whether or not a key is present.

        Both rules live in shared helpers, applied identically by the BYO
        credential body and by model construction.
        """
        base_url_error = base_url_config_error(self.LLM_PROVIDER, self.LLM_BASE_URL)
        if base_url_error:
            raise ValueError(base_url_error)
        if self.LLM_PROVIDER != "azure" or not self.LLM_API_KEY:
            return self
        error = azure_config_error(self.AZURE_OPENAI_ENDPOINT, self.AZURE_OPENAI_API_VERSION)
        if error:
            raise ValueError(error)
        return self

    @model_validator(mode="after")
    def validate_cors_origins(self) -> "Settings":
        """Enforce CORS rules based on DEBUG flag."""
        if not self.CORS_ORIGINS:
            if self.DEBUG:
                self.CORS_ORIGINS = ["*"]
            else:
                raise ValueError(
                    "CORS_ORIGINS must be set (non-empty) when DEBUG=false. "
                    "Set CORS_ORIGINS to a comma-separated list of allowed origins."
                )
        return self


# Module-level singleton — import this everywhere, not Settings()
settings = Settings()
