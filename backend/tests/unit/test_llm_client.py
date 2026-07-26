"""Unit tests for LLM credential resolution and model construction (Item 16).

Arrange-Act-Assert throughout; isolated — no provider is ever contacted, only
client objects are constructed.
"""

from __future__ import annotations

import pytest

from app.core.crypto import encrypt_secret
from app.models.product import Product
from app.models.product_llm_credential import ProductLLMCredential
from app.services.llm import client as llm_client
from app.services.llm.client import (
    LLMConfig,
    LLMConfigError,
    build_model,
    resolve_llm_config,
)

_AZURE_CLASSIC = "https://my-resource.openai.azure.com"
_AZURE_V1 = "https://my-resource.openai.azure.com/openai/v1"


# ── build_model ────────────────────────────────────────────────────────────────


class TestBuildModel:
    def test_openai_builds_an_openai_chat_model(self):
        # Arrange
        config = LLMConfig(provider="openai", model="gpt-5.2", api_key="sk-x")

        # Act
        model = build_model(config)

        # Assert
        assert type(model).__name__ == "OpenAIChatModel"

    def test_anthropic_builds_an_anthropic_model(self):
        # Arrange
        config = LLMConfig(provider="anthropic", model="claude-sonnet-4-5", api_key="sk-x")

        # Act
        model = build_model(config)

        # Assert
        assert type(model).__name__ == "AnthropicModel"

    def test_openrouter_builds_an_openrouter_model(self):
        # Arrange
        config = LLMConfig(
            provider="openrouter", model="anthropic/claude-sonnet-4.6", api_key="sk-x"
        )

        # Act
        model = build_model(config)

        # Assert
        assert type(model).__name__ == "OpenRouterModel"

    def test_azure_classic_endpoint_uses_the_api_version(self):
        # Arrange
        config = LLMConfig(
            provider="azure",
            model="my-deployment",
            api_key="sk-x",
            azure_endpoint=_AZURE_CLASSIC,
            azure_api_version="2024-10-21",
        )

        # Act
        model = build_model(config)

        # Assert — Azure rides the OpenAI-compatible client
        assert type(model).__name__ == "OpenAIChatModel"

    def test_azure_v1_endpoint_needs_no_api_version(self):
        # Arrange
        config = LLMConfig(
            provider="azure", model="my-deployment", api_key="sk-x", azure_endpoint=_AZURE_V1
        )

        # Act
        model = build_model(config)

        # Assert
        assert type(model).__name__ == "OpenAIChatModel"


class TestBuildModelRejections:
    def test_unknown_provider_is_rejected(self):
        # Arrange
        config = LLMConfig(provider="hal9000", model="m", api_key="k")

        # Act / Assert
        with pytest.raises(LLMConfigError, match="Unsupported LLM provider"):
            build_model(config)

    def test_azure_without_an_endpoint_is_rejected(self):
        # Arrange
        config = LLMConfig(provider="azure", model="m", api_key="k")

        # Act / Assert
        with pytest.raises(LLMConfigError, match="requires AZURE_OPENAI_ENDPOINT"):
            build_model(config)

    def test_azure_classic_without_an_api_version_is_rejected(self):
        # Arrange
        config = LLMConfig(provider="azure", model="m", api_key="k", azure_endpoint=_AZURE_CLASSIC)

        # Act / Assert — a clear config error, not a half-built client
        with pytest.raises(LLMConfigError, match="requires AZURE_OPENAI_API_VERSION"):
            build_model(config)

    def test_azure_v1_with_an_api_version_is_rejected(self):
        # Arrange — the v1 API refuses an api_version
        config = LLMConfig(
            provider="azure",
            model="m",
            api_key="k",
            azure_endpoint=_AZURE_V1,
            azure_api_version="2024-10-21",
        )

        # Act / Assert
        with pytest.raises(LLMConfigError, match="must be empty for a v1 endpoint"):
            build_model(config)

    def test_openrouter_bare_model_name_is_rejected(self):
        # Arrange — OpenRouter requires "<upstream-provider>/<model>"
        config = LLMConfig(provider="openrouter", model="gpt-5.2", api_key="k")

        # Act / Assert
        with pytest.raises(LLMConfigError, match="<provider>/<model>"):
            build_model(config)


# ── resolve_llm_config ─────────────────────────────────────────────────────────


@pytest.fixture()
async def product(db_session):
    """A persisted product to hang credentials off.

    The id is explicit because SQLite does not autoincrement a ``BigInteger``
    primary key (only a bare ``INTEGER PRIMARY KEY``).
    """
    item = Product(id=1, name="Widget", url="https://shop.example.com/p/1", source_type="generic")
    db_session.add(item)
    await db_session.flush()
    return item


class TestResolveLLMConfig:
    async def test_product_byo_credential_wins_over_the_admin_default(
        self, db_session, product, monkeypatch
    ):
        # Arrange — an admin default IS configured, and so is a BYO credential
        monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", "sk-admin")
        monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "openai")
        monkeypatch.setattr(llm_client.settings, "LLM_MODEL", "gpt-5.2")
        db_session.add(
            ProductLLMCredential(
                id=1,
                product_id=product.id,
                provider="anthropic",
                model="claude-sonnet-4-5",
                encrypted_api_key=encrypt_secret("sk-byo"),
            )
        )
        await db_session.flush()

        # Act
        config = await resolve_llm_config(db_session, product)

        # Assert — the user's key and their bill, not the deployer's
        assert config is not None
        assert config.provider == "anthropic"
        assert config.api_key == "sk-byo"
        assert config.source == "product_byo"

    async def test_admin_default_is_used_when_no_byo_row_exists(
        self, db_session, product, monkeypatch
    ):
        # Arrange
        monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", "sk-admin")
        monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "openai")
        monkeypatch.setattr(llm_client.settings, "LLM_MODEL", "gpt-5.2")

        # Act
        config = await resolve_llm_config(db_session, product)

        # Assert
        assert config is not None
        assert config.api_key == "sk-admin"
        assert config.source == "admin_default"

    async def test_returns_none_when_neither_credential_is_set(
        self, db_session, product, monkeypatch
    ):
        # Arrange — the documented "generation disabled" state
        monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", "")

        # Act
        config = await resolve_llm_config(db_session, product)

        # Assert
        assert config is None

    async def test_undecryptable_byo_key_falls_back_to_the_admin_default(
        self, db_session, product, monkeypatch
    ):
        # Arrange — e.g. SECRET_KEY was rotated after the credential was stored
        monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", "sk-admin")
        monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "openai")
        monkeypatch.setattr(llm_client.settings, "LLM_MODEL", "gpt-5.2")
        db_session.add(
            ProductLLMCredential(
                id=1,
                product_id=product.id,
                provider="anthropic",
                model="claude-sonnet-4-5",
                encrypted_api_key="not-a-valid-fernet-token",
            )
        )
        await db_session.flush()

        # Act
        config = await resolve_llm_config(db_session, product)

        # Assert — degrade, never raise
        assert config is not None
        assert config.source == "admin_default"
        assert config.api_key == "sk-admin"

    async def test_azure_admin_default_carries_its_endpoint_fields(
        self, db_session, product, monkeypatch
    ):
        # Arrange
        monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", "sk-admin")
        monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "azure")
        monkeypatch.setattr(llm_client.settings, "LLM_MODEL", "my-deployment")
        monkeypatch.setattr(llm_client.settings, "AZURE_OPENAI_ENDPOINT", _AZURE_CLASSIC)
        monkeypatch.setattr(llm_client.settings, "AZURE_OPENAI_API_VERSION", "2024-10-21")

        # Act
        config = await resolve_llm_config(db_session, product)

        # Assert
        assert config is not None
        assert config.azure_endpoint == _AZURE_CLASSIC
        assert config.azure_api_version == "2024-10-21"
        assert type(build_model(config)).__name__ == "OpenAIChatModel"
