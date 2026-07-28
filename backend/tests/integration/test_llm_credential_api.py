"""Integration tests for the BYO LLM credential endpoints (Item 16).

Arrange-Act-Assert throughout; real Postgres via the testcontainer so ids and the
unique-per-product constraint behave as they do in production.

The load-bearing assertion in this file is the negative one: **no response and no
DB column ever contains the plaintext API key**.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.product_llm_credential import ProductLLMCredential
from app.services import llm_credential_service
from app.services.llm import client as llm_client

pytestmark = pytest.mark.integration

_KEY = "sk-live-supersecret-f4c2"
_AZURE_CLASSIC = "https://my-resource.openai.azure.com"
_AZURE_V1 = "https://my-resource.openai.azure.com/openai/v1"


async def _create_product(client) -> dict:
    resp = await client.post(
        "/api/v1/products",
        json={
            "name": "Widget",
            "url": "https://shop.example.com/p/1",
            "source_type": "generic",
            "css_selector": ".price",
        },
    )
    assert resp.status_code == 201
    return resp.json()


class TestPutCredential:
    async def test_stores_a_credential_and_never_echoes_the_key(self, pg_async_client):
        # Arrange
        product = await _create_product(pg_async_client)

        # Act
        resp = await pg_async_client.put(
            f"/api/v1/products/{product['id']}/llm-credential",
            json={"provider": "anthropic", "model": "claude-sonnet-4-5", "api_key": _KEY},
        )

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "anthropic"
        assert body["has_key"] is True
        assert body["key_hint"].endswith("f4c2")
        # The key must not appear anywhere in the serialised response
        assert _KEY not in resp.text
        assert "api_key" not in body
        assert "encrypted_api_key" not in body

    async def test_key_is_encrypted_in_the_database(self, pg_async_client, pg_session):
        # Arrange
        product = await _create_product(pg_async_client)

        # Act
        await pg_async_client.put(
            f"/api/v1/products/{product['id']}/llm-credential",
            json={"provider": "openai", "model": "gpt-5.2", "api_key": _KEY},
        )

        # Assert — the stored column is ciphertext, and it round-trips
        row = await pg_session.scalar(
            select(ProductLLMCredential).where(ProductLLMCredential.product_id == product["id"])
        )
        assert row is not None
        assert row.encrypted_api_key != _KEY
        assert _KEY not in row.encrypted_api_key
        from app.core.crypto import decrypt_secret

        assert decrypt_secret(row.encrypted_api_key) == _KEY

    async def test_put_replaces_an_existing_credential_wholesale(self, pg_async_client, pg_session):
        # Arrange — start on Azure, then switch to OpenAI
        product = await _create_product(pg_async_client)
        await pg_async_client.put(
            f"/api/v1/products/{product['id']}/llm-credential",
            json={
                "provider": "azure",
                "model": "my-deployment",
                "api_key": _KEY,
                "azure_endpoint": _AZURE_CLASSIC,
                "azure_api_version": "2024-10-21",
            },
        )

        # Act
        resp = await pg_async_client.put(
            f"/api/v1/products/{product['id']}/llm-credential",
            json={"provider": "openai", "model": "gpt-5.2", "api_key": "sk-new-key-9999"},
        )

        # Assert — no stale Azure fields survive to be picked up later
        assert resp.status_code == 200
        assert resp.json()["azure_endpoint"] is None
        assert resp.json()["azure_api_version"] is None
        rows = (
            (
                await pg_session.execute(
                    select(ProductLLMCredential).where(
                        ProductLLMCredential.product_id == product["id"]
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1

    async def test_unknown_product_returns_404(self, pg_async_client):
        # Act
        resp = await pg_async_client.put(
            "/api/v1/products/999999/llm-credential",
            json={"provider": "openai", "model": "gpt-5.2", "api_key": _KEY},
        )

        # Assert
        assert resp.status_code == 404


class TestPutCredentialValidation:
    async def test_unsupported_provider_is_422(self, pg_async_client):
        # Arrange
        product = await _create_product(pg_async_client)

        # Act
        resp = await pg_async_client.put(
            f"/api/v1/products/{product['id']}/llm-credential",
            json={"provider": "hal9000", "model": "m", "api_key": _KEY},
        )

        # Assert — rejected at the boundary, not inside a worker hours later
        assert resp.status_code == 422

    async def test_azure_without_an_endpoint_is_422(self, pg_async_client):
        # Arrange
        product = await _create_product(pg_async_client)

        # Act
        resp = await pg_async_client.put(
            f"/api/v1/products/{product['id']}/llm-credential",
            json={"provider": "azure", "model": "m", "api_key": _KEY},
        )

        # Assert
        assert resp.status_code == 422

    async def test_azure_classic_without_an_api_version_is_422(self, pg_async_client):
        # Arrange
        product = await _create_product(pg_async_client)

        # Act
        resp = await pg_async_client.put(
            f"/api/v1/products/{product['id']}/llm-credential",
            json={
                "provider": "azure",
                "model": "m",
                "api_key": _KEY,
                "azure_endpoint": _AZURE_CLASSIC,
            },
        )

        # Assert
        assert resp.status_code == 422

    async def test_azure_v1_with_an_api_version_is_422(self, pg_async_client):
        # Arrange — the v1 API refuses an api_version
        product = await _create_product(pg_async_client)

        # Act
        resp = await pg_async_client.put(
            f"/api/v1/products/{product['id']}/llm-credential",
            json={
                "provider": "azure",
                "model": "m",
                "api_key": _KEY,
                "azure_endpoint": _AZURE_V1,
                "azure_api_version": "2024-10-21",
            },
        )

        # Assert
        assert resp.status_code == 422

    async def test_empty_api_key_is_422(self, pg_async_client):
        # Arrange
        product = await _create_product(pg_async_client)

        # Act
        resp = await pg_async_client.put(
            f"/api/v1/products/{product['id']}/llm-credential",
            json={"provider": "openai", "model": "gpt-5.2", "api_key": ""},
        )

        # Assert
        assert resp.status_code == 422


class TestGetCredential:
    async def test_returns_masked_metadata_only(self, pg_async_client):
        # Arrange
        product = await _create_product(pg_async_client)
        await pg_async_client.put(
            f"/api/v1/products/{product['id']}/llm-credential",
            json={"provider": "openai", "model": "gpt-5.2", "api_key": _KEY},
        )

        # Act
        resp = await pg_async_client.get(f"/api/v1/products/{product['id']}/llm-credential")

        # Assert
        assert resp.status_code == 200
        assert resp.json()["model"] == "gpt-5.2"
        assert resp.json()["has_key"] is True
        assert _KEY not in resp.text

    async def test_product_without_a_credential_returns_404(self, pg_async_client):
        # Arrange
        product = await _create_product(pg_async_client)

        # Act
        resp = await pg_async_client.get(f"/api/v1/products/{product['id']}/llm-credential")

        # Assert
        assert resp.status_code == 404

    async def test_unknown_product_returns_404(self, pg_async_client):
        assert (
            await pg_async_client.get("/api/v1/products/999999/llm-credential")
        ).status_code == 404


class TestDeleteCredential:
    async def test_deleting_reverts_to_the_admin_default(
        self, pg_async_client, pg_session, monkeypatch
    ):
        # Arrange — a BYO credential that currently wins over the admin default
        monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", "sk-admin")
        monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "openai")
        monkeypatch.setattr(llm_client.settings, "LLM_MODEL", "gpt-5.2")
        product = await _create_product(pg_async_client)
        await pg_async_client.put(
            f"/api/v1/products/{product['id']}/llm-credential",
            json={"provider": "anthropic", "model": "claude-sonnet-4-5", "api_key": _KEY},
        )

        # Act
        resp = await pg_async_client.delete(f"/api/v1/products/{product['id']}/llm-credential")

        # Assert
        assert resp.status_code == 204
        assert await llm_credential_service.get_credential(pg_session, product["id"]) is None
        from app.models.product import Product

        stored = await pg_session.scalar(select(Product).where(Product.id == product["id"]))
        config = await llm_client.resolve_llm_config(pg_session, stored)
        assert config is not None
        assert config.source == "admin_default"

    async def test_deleting_a_missing_credential_returns_404(self, pg_async_client):
        # Arrange
        product = await _create_product(pg_async_client)

        # Act / Assert
        resp = await pg_async_client.delete(f"/api/v1/products/{product['id']}/llm-credential")
        assert resp.status_code == 404

    async def test_deleting_the_product_cascades_to_its_credential(
        self, pg_async_client, pg_session
    ):
        # Arrange
        product = await _create_product(pg_async_client)
        await pg_async_client.put(
            f"/api/v1/products/{product['id']}/llm-credential",
            json={"provider": "openai", "model": "gpt-5.2", "api_key": _KEY},
        )

        # Act — a stored key must not outlive the product it belongs to
        assert (
            await pg_async_client.delete(f"/api/v1/products/{product['id']}")
        ).status_code == 204

        # Assert
        assert await llm_credential_service.get_credential(pg_session, product["id"]) is None
