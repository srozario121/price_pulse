"""Application configuration — single source of truth for all env vars.

All downstream modules (database, Celery, logging) import `settings`
rather than reading from `os.environ` directly.

CORS_ORIGINS is read from the environment as a comma-separated string
(e.g. "http://localhost:5173,https://app.example.com") and coerced to
a list[str] by the field validator.
"""

from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    SCRAPE_INTERVAL_MINUTES: int = 30
    SCRAPE_MIN_DELAY_SECONDS: int = 2
    ALERT_COOLDOWN_HOURS: int = 24

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
