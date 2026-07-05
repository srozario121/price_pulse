"""Integration tests for /api/v1/products/{id}/prices and /scrape routes.

Uses ``pg_async_client`` (Postgres testcontainer).
The Celery task is mocked so tests run without a live broker.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

PRODUCT_PAYLOAD = {
    "name": "Widget",
    "url": "https://example.com/widget",
    "source_type": "generic",
    "css_selector": ".price",
    "is_active": True,
}


async def _create_product(client, payload: dict | None = None) -> dict:
    resp = await client.post("/api/v1/products", json=payload or PRODUCT_PAYLOAD)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _seed_price_record(pg_engine, product_id: int, price: str, captured_at: str) -> None:
    """Insert a PriceRecord row directly into Postgres for seeding test data.

    ``captured_at`` is an ISO 8601 string (e.g. ``"2026-01-01T10:00:00Z"``);
    it is parsed to a timezone-aware datetime before insertion because asyncpg
    requires a datetime object, not a plain string.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.price_history import PriceRecord

    dt = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))

    factory = async_sessionmaker(bind=pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        record = PriceRecord(
            product_id=product_id,
            price=Decimal(price),
            currency="GBP",
            extraction_status="ok",
            captured_at=dt,
        )
        session.add(record)
        await session.commit()


# ── GET /products/{id}/prices ─────────────────────────────────────────────────


class TestListPrices:
    @pytest.mark.asyncio
    async def test_empty_price_history(self, pg_async_client):
        product = await _create_product(pg_async_client)
        resp = await pg_async_client.get(f"/api/v1/products/{product['id']}/prices")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_unknown_product_returns_404(self, pg_async_client):
        resp = await pg_async_client.get("/api/v1/products/99999/prices")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_price_records_returned_desc_by_captured_at(self, pg_async_client, pg_engine):
        product = await _create_product(pg_async_client)
        pid = product["id"]

        # Insert two records with different timestamps
        await _seed_price_record(pg_engine, pid, "10.00", "2026-01-01T10:00:00Z")
        await _seed_price_record(pg_engine, pid, "20.00", "2026-01-02T10:00:00Z")

        resp = await pg_async_client.get(f"/api/v1/products/{pid}/prices")
        assert resp.status_code == 200
        prices = [Decimal(item["price"]) for item in resp.json()["items"]]
        # Most recent first
        assert prices[0] == Decimal("20.00")
        assert prices[1] == Decimal("10.00")

    @pytest.mark.asyncio
    async def test_from_dt_filter(self, pg_async_client, pg_engine):
        product = await _create_product(pg_async_client)
        pid = product["id"]

        await _seed_price_record(pg_engine, pid, "5.00", "2026-01-01T00:00:00Z")
        await _seed_price_record(pg_engine, pid, "9.99", "2026-03-01T00:00:00Z")

        resp = await pg_async_client.get(
            f"/api/v1/products/{pid}/prices?from_dt=2026-02-01T00:00:00Z"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert Decimal(data["items"][0]["price"]) == Decimal("9.99")

    @pytest.mark.asyncio
    async def test_to_dt_filter(self, pg_async_client, pg_engine):
        product = await _create_product(pg_async_client)
        pid = product["id"]

        await _seed_price_record(pg_engine, pid, "5.00", "2026-01-01T00:00:00Z")
        await _seed_price_record(pg_engine, pid, "9.99", "2026-03-01T00:00:00Z")

        resp = await pg_async_client.get(
            f"/api/v1/products/{pid}/prices?to_dt=2026-02-01T00:00:00Z"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert Decimal(data["items"][0]["price"]) == Decimal("5.00")

    @pytest.mark.asyncio
    async def test_limit_above_100_returns_422(self, pg_async_client):
        product = await _create_product(pg_async_client)
        resp = await pg_async_client.get(f"/api/v1/products/{product['id']}/prices?limit=200")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_extraction_status_present_in_response(self, pg_async_client, pg_engine):
        product = await _create_product(pg_async_client)
        pid = product["id"]
        await _seed_price_record(pg_engine, pid, "15.00", "2026-01-01T00:00:00Z")

        resp = await pg_async_client.get(f"/api/v1/products/{pid}/prices")
        assert resp.status_code == 200
        assert "extraction_status" in resp.json()["items"][0]


# ── POST /products/{id}/scrape ────────────────────────────────────────────────


class TestTriggerScrape:
    @pytest.mark.asyncio
    async def test_scrape_returns_202(self, pg_async_client):
        product = await _create_product(pg_async_client)

        mock_task = MagicMock()
        mock_task.id = "test-task-id-abc"

        with patch("app.api.v1.prices.scrape_product") as mock_scrape:
            mock_scrape.delay.return_value = mock_task
            resp = await pg_async_client.post(f"/api/v1/products/{product['id']}/scrape")

        assert resp.status_code == 202
        data = resp.json()
        assert data["task_id"] == "test-task-id-abc"
        assert data["status"] == "queued"
        assert data["product"]["id"] == product["id"]

    @pytest.mark.asyncio
    async def test_scrape_inactive_product_returns_400(self, pg_async_client):
        product = await _create_product(
            pg_async_client,
            {**PRODUCT_PAYLOAD, "url": "https://example.com/inactive", "is_active": False},
        )
        resp = await pg_async_client.post(f"/api/v1/products/{product['id']}/scrape")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_scrape_nonexistent_product_returns_404(self, pg_async_client):
        resp = await pg_async_client.post("/api/v1/products/99999/scrape")
        assert resp.status_code == 404
