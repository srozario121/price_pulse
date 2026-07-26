"""Unit tests for the Item 16 LLM settings validators.

Arrange-Act-Assert throughout. These settings are validated at construction so a
misconfiguration fails at startup rather than from inside a Celery worker hours
later, when the first selector regeneration runs.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import (
    LLM_PROVIDERS,
    Settings,
    azure_config_error,
    is_azure_v1_endpoint,
)

_BASE = {
    "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
    "DEBUG": True,
}
_AZURE_CLASSIC = "https://my-resource.openai.azure.com"
_AZURE_V1 = "https://my-resource.openai.azure.com/openai/v1"


def _settings(**overrides) -> Settings:
    return Settings(**{**_BASE, **overrides})


class TestLLMProvider:
    def test_defaults_to_openai(self):
        assert _settings().LLM_PROVIDER == "openai"

    @pytest.mark.parametrize("provider", LLM_PROVIDERS)
    def test_every_supported_provider_is_accepted(self, provider):
        # Arrange — Azure needs its endpoint, but only when a key makes it usable
        settings = _settings(LLM_PROVIDER=provider)

        # Assert
        assert settings.LLM_PROVIDER == provider

    def test_provider_is_case_insensitive(self):
        assert _settings(LLM_PROVIDER="OpenAI").LLM_PROVIDER == "openai"

    def test_unknown_provider_is_rejected_at_startup(self):
        # Act / Assert
        with pytest.raises(ValidationError, match="LLM_PROVIDER must be one of"):
            _settings(LLM_PROVIDER="hal9000")


class TestAzureSettings:
    def test_azure_without_a_key_still_boots(self):
        # Arrange / Act — an unconfigured deployment must not fail to start
        settings = _settings(LLM_PROVIDER="azure", LLM_API_KEY="")

        # Assert
        assert settings.LLM_PROVIDER == "azure"

    def test_azure_with_a_key_requires_an_endpoint(self):
        with pytest.raises(ValidationError, match="requires AZURE_OPENAI_ENDPOINT"):
            _settings(LLM_PROVIDER="azure", LLM_API_KEY="sk-x")

    def test_azure_classic_endpoint_requires_an_api_version(self):
        with pytest.raises(ValidationError, match="requires AZURE_OPENAI_API_VERSION"):
            _settings(
                LLM_PROVIDER="azure", LLM_API_KEY="sk-x", AZURE_OPENAI_ENDPOINT=_AZURE_CLASSIC
            )

    def test_azure_v1_endpoint_rejects_an_api_version(self):
        # The v1 API refuses one, so accepting it here would only fail later
        with pytest.raises(ValidationError, match="must be empty for a v1 endpoint"):
            _settings(
                LLM_PROVIDER="azure",
                LLM_API_KEY="sk-x",
                AZURE_OPENAI_ENDPOINT=_AZURE_V1,
                AZURE_OPENAI_API_VERSION="2024-10-21",
            )

    def test_azure_classic_with_both_is_accepted(self):
        settings = _settings(
            LLM_PROVIDER="azure",
            LLM_API_KEY="sk-x",
            AZURE_OPENAI_ENDPOINT=_AZURE_CLASSIC,
            AZURE_OPENAI_API_VERSION="2024-10-21",
        )
        assert settings.AZURE_OPENAI_API_VERSION == "2024-10-21"

    def test_azure_v1_without_an_api_version_is_accepted(self):
        settings = _settings(
            LLM_PROVIDER="azure", LLM_API_KEY="sk-x", AZURE_OPENAI_ENDPOINT=_AZURE_V1
        )
        assert settings.AZURE_OPENAI_ENDPOINT == _AZURE_V1


class TestAzureConfigRule:
    """The shared rule applied at all three Azure boundaries."""

    @pytest.mark.parametrize(
        ("endpoint", "expected"),
        [
            ("https://r.openai.azure.com/openai/v1", True),
            ("https://r.openai.azure.com/openai/v1/", True),
            ("https://r.openai.azure.com", False),
            ("https://r.openai.azure.com/", False),
        ],
    )
    def test_classifies_both_endpoint_styles(self, endpoint, expected):
        assert is_azure_v1_endpoint(endpoint) is expected

    def test_valid_pairs_report_no_error(self):
        assert azure_config_error(_AZURE_CLASSIC, "2024-10-21") is None
        assert azure_config_error(_AZURE_V1, None) is None
        assert azure_config_error(_AZURE_V1, "") is None

    def test_invalid_pairs_report_an_error(self):
        assert azure_config_error(None, "2024-10-21") is not None
        assert azure_config_error("", None) is not None
        assert azure_config_error(_AZURE_CLASSIC, None) is not None
        assert azure_config_error(_AZURE_V1, "2024-10-21") is not None

    def test_field_names_are_caller_supplied(self):
        # The BYO credential body names its fields differently from the env vars,
        # so each boundary reports the names its own users see
        message = azure_config_error(
            None, None, endpoint_name="azure_endpoint", version_name="azure_api_version"
        )
        assert "azure_endpoint" in message
        assert "AZURE_OPENAI_ENDPOINT" not in message


class TestSelectorKnobs:
    def test_defaults_are_sane(self):
        # Arrange / Act
        settings = _settings()

        # Assert
        assert settings.SELECTOR_HTML_MAX_BYTES > 0
        assert settings.SELECTOR_MAX_REGEN_ATTEMPTS >= 1
        assert settings.SELECTOR_REGEN_COOLDOWN_HOURS >= 1

    @pytest.mark.parametrize(
        "field",
        [
            "SELECTOR_HTML_MAX_BYTES",
            "SELECTOR_MAX_REGEN_ATTEMPTS",
            "SELECTOR_REGEN_COOLDOWN_HOURS",
        ],
    )
    def test_non_positive_values_are_rejected(self, field):
        # A zero attempt budget or cooldown would either disable healing entirely
        # or remove the guard against hammering the provider
        with pytest.raises(ValidationError, match=f"{field} must be >= 1"):
            _settings(**{field: 0})

    def test_empty_api_key_is_the_disabled_switch(self):
        # Documented behaviour: no key ⇒ generation disabled, not an error
        assert _settings().LLM_API_KEY == ""
