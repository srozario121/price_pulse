"""Integration tests for /api/v1/alerts routes.

Uses ``pg_async_client`` (Postgres testcontainer).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

PRODUCT_PAYLOAD = {
    "name": "Widget",
    "url": "https://example.com/widget",
    "source_type": "generic",
    "css_selector": ".price",
    "is_active": True,
}


async def _create_product(client, url_suffix: str = "widget") -> dict:
    payload = {**PRODUCT_PAYLOAD, "url": f"https://example.com/{url_suffix}"}
    resp = await client.post("/api/v1/products", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_alert(client, product_id: int, **overrides) -> dict:
    payload = {
        "product_id": product_id,
        "threshold_price": "49.99",
        "direction": "below",
        **overrides,
    }
    resp = await client.post("/api/v1/alerts", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── POST /alerts ──────────────────────────────────────────────────────────────


class TestCreateAlert:
    @pytest.mark.asyncio
    async def test_creates_alert_201(self, pg_async_client):
        product = await _create_product(pg_async_client)
        resp = await pg_async_client.post(
            "/api/v1/alerts",
            json={
                "product_id": product["id"],
                "threshold_price": "49.99",
                "direction": "below",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["product_id"] == product["id"]
        assert Decimal(data["threshold_price"]) == Decimal("49.99")
        assert data["direction"] == "below"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_nonexistent_product_returns_404(self, pg_async_client):
        resp = await pg_async_client.post(
            "/api/v1/alerts",
            json={"product_id": 99999, "threshold_price": "10.00", "direction": "below"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_direction_returns_422(self, pg_async_client):
        product = await _create_product(pg_async_client, url_suffix="dir-test")
        resp = await pg_async_client.post(
            "/api/v1/alerts",
            json={
                "product_id": product["id"],
                "threshold_price": "10.00",
                "direction": "sideways",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_default_channel_is_email(self, pg_async_client):
        product = await _create_product(pg_async_client, url_suffix="chan-default")
        alert = await _create_alert(pg_async_client, product["id"])
        assert alert["channel"] == "email"


# ── GET /alerts ───────────────────────────────────────────────────────────────


class TestListAlerts:
    @pytest.mark.asyncio
    async def test_empty_list(self, pg_async_client):
        resp = await pg_async_client.get("/api/v1/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_filter_by_product_id(self, pg_async_client):
        p1 = await _create_product(pg_async_client, url_suffix="p1")
        p2 = await _create_product(pg_async_client, url_suffix="p2")

        a1 = await _create_alert(pg_async_client, p1["id"])
        await _create_alert(pg_async_client, p2["id"])

        resp = await pg_async_client.get(f"/api/v1/alerts?product_id={p1['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == a1["id"]

    @pytest.mark.asyncio
    async def test_filter_by_is_active(self, pg_async_client):
        product = await _create_product(pg_async_client, url_suffix="active-filter")
        active_alert = await _create_alert(pg_async_client, product["id"])
        inactive_alert = await _create_alert(pg_async_client, product["id"], is_active=False)

        resp = await pg_async_client.get("/api/v1/alerts?is_active=false")
        assert resp.status_code == 200
        ids = [a["id"] for a in resp.json()["items"]]
        assert inactive_alert["id"] in ids
        assert active_alert["id"] not in ids

    @pytest.mark.asyncio
    async def test_new_alert_present_in_product_alerts(self, pg_async_client):
        """Created alert appears in GET /alerts?product_id=X."""
        product = await _create_product(pg_async_client, url_suffix="list-check")
        alert = await _create_alert(pg_async_client, product["id"])

        resp = await pg_async_client.get(f"/api/v1/alerts?product_id={product['id']}")
        ids = [a["id"] for a in resp.json()["items"]]
        assert alert["id"] in ids


# ── GET /alerts/{id} ──────────────────────────────────────────────────────────


class TestGetAlert:
    @pytest.mark.asyncio
    async def test_returns_alert_data(self, pg_async_client):
        product = await _create_product(pg_async_client, url_suffix="get-alert")
        created = await _create_alert(pg_async_client, product["id"])

        resp = await pg_async_client.get(f"/api/v1/alerts/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_nonexistent_returns_404(self, pg_async_client):
        resp = await pg_async_client.get("/api/v1/alerts/99999")
        assert resp.status_code == 404


# ── PATCH /alerts/{id} ────────────────────────────────────────────────────────


class TestUpdateAlert:
    @pytest.mark.asyncio
    async def test_updates_threshold_price(self, pg_async_client):
        product = await _create_product(pg_async_client, url_suffix="patch-alert")
        alert = await _create_alert(pg_async_client, product["id"])

        resp = await pg_async_client.patch(
            f"/api/v1/alerts/{alert['id']}",
            json={"threshold_price": "99.99"},
        )
        assert resp.status_code == 200
        assert Decimal(resp.json()["threshold_price"]) == Decimal("99.99")

    @pytest.mark.asyncio
    async def test_patch_with_product_id_returns_422(self, pg_async_client):
        """product_id is immutable after creation — must be rejected."""
        product = await _create_product(pg_async_client, url_suffix="patch-pid")
        alert = await _create_alert(pg_async_client, product["id"])

        resp = await pg_async_client.patch(
            f"/api/v1/alerts/{alert['id']}",
            json={"product_id": 999},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_nonexistent_returns_404(self, pg_async_client):
        resp = await pg_async_client.patch("/api/v1/alerts/99999", json={"is_active": False})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_deactivate_alert(self, pg_async_client):
        product = await _create_product(pg_async_client, url_suffix="deactivate")
        alert = await _create_alert(pg_async_client, product["id"])

        resp = await pg_async_client.patch(
            f"/api/v1/alerts/{alert['id']}", json={"is_active": False}
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False


# ── DELETE /alerts/{id} ───────────────────────────────────────────────────────


class TestDeleteAlert:
    @pytest.mark.asyncio
    async def test_delete_returns_204(self, pg_async_client):
        product = await _create_product(pg_async_client, url_suffix="del-alert")
        alert = await _create_alert(pg_async_client, product["id"])

        resp = await pg_async_client.delete(f"/api/v1/alerts/{alert['id']}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_deleted_alert_returns_404(self, pg_async_client):
        product = await _create_product(pg_async_client, url_suffix="del-check")
        alert = await _create_alert(pg_async_client, product["id"])

        await pg_async_client.delete(f"/api/v1/alerts/{alert['id']}")
        resp = await pg_async_client.get(f"/api/v1/alerts/{alert['id']}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, pg_async_client):
        resp = await pg_async_client.delete("/api/v1/alerts/99999")
        assert resp.status_code == 404
