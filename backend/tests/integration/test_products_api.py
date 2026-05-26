"""Integration tests for /api/v1/products routes.

Uses ``pg_async_client`` (Postgres testcontainer) because the Product model
uses native Postgres ENUMs that are incompatible with SQLite.
"""
from __future__ import annotations

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

PRODUCT_PAYLOAD = {
    "name": "Test Widget",
    "url": "https://example.com/widget",
    "source_type": "generic",
    "css_selector": ".price",
    "is_active": True,
}


async def _create_product(client, payload: dict | None = None) -> dict:
    """POST /products and return the response body."""
    resp = await client.post("/api/v1/products", json=payload or PRODUCT_PAYLOAD)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── POST /products ────────────────────────────────────────────────────────────


class TestCreateProduct:
    @pytest.mark.asyncio
    async def test_creates_product_201(self, pg_async_client):
        # Act
        resp = await pg_async_client.post("/api/v1/products", json=PRODUCT_PAYLOAD)
        # Assert
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == PRODUCT_PAYLOAD["name"]
        assert data["url"] == PRODUCT_PAYLOAD["url"]
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_created_product_readable_via_get(self, pg_async_client):
        # Arrange
        created = await _create_product(pg_async_client)
        # Act
        resp = await pg_async_client.get(f"/api/v1/products/{created['id']}")
        # Assert
        assert resp.status_code == 200
        assert resp.json()["name"] == created["name"]

    @pytest.mark.asyncio
    async def test_duplicate_url_returns_409(self, pg_async_client):
        # Arrange
        await _create_product(pg_async_client)
        # Act — same URL again
        resp = await pg_async_client.post("/api/v1/products", json=PRODUCT_PAYLOAD)
        # Assert
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_missing_name_returns_422(self, pg_async_client):
        bad = {**PRODUCT_PAYLOAD}
        del bad["name"]
        resp = await pg_async_client.post("/api/v1/products", json=bad)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_source_type_returns_422(self, pg_async_client):
        bad = {**PRODUCT_PAYLOAD, "source_type": "nonexistent"}
        resp = await pg_async_client.post("/api/v1/products", json=bad)
        assert resp.status_code == 422


# ── GET /products ─────────────────────────────────────────────────────────────


class TestListProducts:
    @pytest.mark.asyncio
    async def test_empty_list(self, pg_async_client):
        resp = await pg_async_client.get("/api/v1/products")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_pagination_total_reflects_all_records(self, pg_async_client):
        # Seed 15 products with distinct URLs
        for i in range(15):
            payload = {**PRODUCT_PAYLOAD, "url": f"https://example.com/product-{i}"}
            await _create_product(pg_async_client, payload)

        resp = await pg_async_client.get("/api/v1/products?limit=5&offset=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 15
        assert len(data["items"]) == 5
        assert data["limit"] == 5
        assert data["offset"] == 10

    @pytest.mark.asyncio
    async def test_is_active_filter_false(self, pg_async_client):
        # Arrange — create one active and one inactive product
        active = await _create_product(
            pg_async_client,
            {**PRODUCT_PAYLOAD, "url": "https://example.com/active", "is_active": True},
        )
        inactive = await _create_product(
            pg_async_client,
            {**PRODUCT_PAYLOAD, "url": "https://example.com/inactive", "is_active": False},
        )

        # Act
        resp = await pg_async_client.get("/api/v1/products?is_active=false")
        assert resp.status_code == 200
        data = resp.json()
        ids = [p["id"] for p in data["items"]]
        assert inactive["id"] in ids
        assert active["id"] not in ids

    @pytest.mark.asyncio
    async def test_limit_above_100_returns_422(self, pg_async_client):
        resp = await pg_async_client.get("/api/v1/products?limit=200")
        assert resp.status_code == 422


# ── GET /products/{id} ────────────────────────────────────────────────────────


class TestGetProduct:
    @pytest.mark.asyncio
    async def test_returns_404_for_missing_product(self, pg_async_client):
        resp = await pg_async_client.get("/api/v1/products/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_product_data(self, pg_async_client):
        created = await _create_product(pg_async_client)
        resp = await pg_async_client.get(f"/api/v1/products/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["url"] == PRODUCT_PAYLOAD["url"]


# ── PATCH /products/{id} ──────────────────────────────────────────────────────


class TestUpdateProduct:
    @pytest.mark.asyncio
    async def test_updates_name(self, pg_async_client):
        # Arrange
        created = await _create_product(pg_async_client)
        # Act
        resp = await pg_async_client.patch(
            f"/api/v1/products/{created['id']}",
            json={"name": "Updated Name"},
        )
        # Assert
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_patch_persists_change(self, pg_async_client):
        created = await _create_product(pg_async_client)
        await pg_async_client.patch(
            f"/api/v1/products/{created['id']}",
            json={"name": "Persisted"},
        )
        get_resp = await pg_async_client.get(f"/api/v1/products/{created['id']}")
        assert get_resp.json()["name"] == "Persisted"

    @pytest.mark.asyncio
    async def test_patch_url_conflict_returns_409(self, pg_async_client):
        # Create two products
        a = await _create_product(
            pg_async_client, {**PRODUCT_PAYLOAD, "url": "https://example.com/a"}
        )
        await _create_product(
            pg_async_client, {**PRODUCT_PAYLOAD, "url": "https://example.com/b"}
        )
        # Try to update product A's URL to product B's URL
        resp = await pg_async_client.patch(
            f"/api/v1/products/{a['id']}",
            json={"url": "https://example.com/b"},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_patch_same_url_on_same_product_ok(self, pg_async_client):
        """Updating a product with its own URL should not trigger 409."""
        created = await _create_product(pg_async_client)
        resp = await pg_async_client.patch(
            f"/api/v1/products/{created['id']}",
            json={"url": PRODUCT_PAYLOAD["url"]},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_patch_nonexistent_returns_404(self, pg_async_client):
        resp = await pg_async_client.patch(
            "/api/v1/products/99999", json={"name": "Ghost"}
        )
        assert resp.status_code == 404


# ── DELETE /products/{id} ─────────────────────────────────────────────────────


class TestDeleteProduct:
    @pytest.mark.asyncio
    async def test_delete_returns_204(self, pg_async_client):
        created = await _create_product(pg_async_client)
        resp = await pg_async_client.delete(f"/api/v1/products/{created['id']}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_deleted_product_returns_404(self, pg_async_client):
        created = await _create_product(pg_async_client)
        await pg_async_client.delete(f"/api/v1/products/{created['id']}")
        resp = await pg_async_client.get(f"/api/v1/products/{created['id']}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, pg_async_client):
        resp = await pg_async_client.delete("/api/v1/products/99999")
        assert resp.status_code == 404
