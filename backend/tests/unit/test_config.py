"""Unit tests for app.core.config — Settings validation.

All tests use monkeypatch to inject env vars and re-instantiate Settings
from scratch so they are independent of the module-level singleton.
"""

import pytest
from pydantic import ValidationError


def make_settings(**kwargs):
    """Create a fresh Settings instance with the given env vars."""

    # Temporarily override env — build Settings from kwargs directly
    from app.core.config import Settings

    return Settings(**kwargs)  # type: ignore[call-arg]


class TestSecretKey:
    """SECRET_KEY must be at least 32 characters."""

    def test_valid_secret_key_accepted(self):
        # Arrange
        key = "a" * 32

        # Act
        s = make_settings(
            SECRET_KEY=key,
            DEBUG=True,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
        )

        # Assert
        assert s.SECRET_KEY == key

    def test_short_secret_key_raises(self):
        # Arrange
        key = "too-short"  # < 32 chars

        # Act / Assert
        with pytest.raises(ValidationError, match="SECRET_KEY must be at least 32"):
            make_settings(
                SECRET_KEY=key,
                DEBUG=True,
                DATABASE_URL="sqlite+aiosqlite:///:memory:",
            )

    def test_empty_secret_key_raises(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError, match="SECRET_KEY must be at least 32"):
            make_settings(
                SECRET_KEY="",
                DEBUG=True,
                DATABASE_URL="sqlite+aiosqlite:///:memory:",
            )


class TestCorsOrigins:
    """CORS_ORIGINS defaults and production enforcement."""

    def test_debug_true_defaults_to_wildcard(self, monkeypatch):
        # Arrange — clear CORS_ORIGINS from env so the default logic triggers
        monkeypatch.delenv("CORS_ORIGINS", raising=False)

        # Act
        s = make_settings(
            SECRET_KEY="a" * 32,
            DEBUG=True,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            CORS_ORIGINS=[],
        )

        # Assert — model_validator should replace empty list with ["*"] in debug mode
        assert s.CORS_ORIGINS == ["*"]

    def test_explicit_origins_preserved(self):
        # Arrange
        origins = ["http://localhost:5173", "https://app.example.com"]

        # Act
        s = make_settings(
            SECRET_KEY="a" * 32,
            DEBUG=True,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            CORS_ORIGINS=origins,
        )

        # Assert
        assert s.CORS_ORIGINS == origins

    def test_empty_cors_origins_in_production_raises(self):
        # Arrange — DEBUG=false, empty CORS_ORIGINS

        # Act / Assert
        with pytest.raises(ValidationError, match="CORS_ORIGINS must be set"):
            make_settings(
                SECRET_KEY="a" * 32,
                DEBUG=False,
                DATABASE_URL="sqlite+aiosqlite:///:memory:",
                CORS_ORIGINS=[],
            )

    def test_production_with_origins_accepted(self):
        # Arrange
        origins = ["https://app.example.com"]

        # Act
        s = make_settings(
            SECRET_KEY="a" * 32,
            DEBUG=False,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            CORS_ORIGINS=origins,
        )

        # Assert
        assert s.CORS_ORIGINS == origins


class TestCeleryBrokerUrl:
    """CELERY_BROKER_URL falls back to REDIS_URL when not set."""

    def test_defaults_to_redis_url(self):
        # Arrange
        redis = "redis://myredis:6379/1"

        # Act
        s = make_settings(
            SECRET_KEY="a" * 32,
            DEBUG=True,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            REDIS_URL=redis,
        )

        # Assert
        assert s.CELERY_BROKER_URL == redis

    def test_explicit_broker_url_overrides_redis(self):
        # Arrange
        broker = "redis://broker:6379/2"
        redis = "redis://myredis:6379/1"

        # Act
        s = make_settings(
            SECRET_KEY="a" * 32,
            DEBUG=True,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            REDIS_URL=redis,
            CELERY_BROKER_URL=broker,
        )

        # Assert
        assert s.CELERY_BROKER_URL == broker


class TestDefaults:
    """Sensible defaults are present when not overridden."""

    def test_default_scrape_interval(self):
        # Arrange / Act
        s = make_settings(
            SECRET_KEY="a" * 32,
            DEBUG=True,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
        )

        # Assert
        assert s.SCRAPE_INTERVAL_MINUTES == 30

    def test_default_log_level(self):
        # Arrange / Act
        s = make_settings(
            SECRET_KEY="a" * 32,
            DEBUG=True,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
        )

        # Assert
        assert s.LOG_LEVEL == "INFO"
