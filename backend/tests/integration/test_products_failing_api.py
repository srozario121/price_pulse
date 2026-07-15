"""Integration tests for GET /api/v1/products/failing and monitoring_service.

Uses ``pg_async_client`` (Postgres testcontainer): ``find_failing_products`` relies
on a window-function (``row_number() OVER``) query and native ENUM columns, so it is
exercised against real Postgres rather than SQLite.
"""

from __future__ import annotations

from datetime import datetime
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


async def _create_product(client, payload: dict | None = None) -> dict:
    resp = await client.post("/api/v1/products", json=payload or PRODUCT_PAYLOAD)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _seed_record(
    pg_engine,
    product_id: int,
    *,
    status: str,
    captured_at: str,
    price: str | None = None,
) -> None:
    """Insert one PriceRecord with an explicit extraction_status + captured_at."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.price_history import PriceRecord

    dt = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    factory = async_sessionmaker(bind=pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(
            PriceRecord(
                product_id=product_id,
                price=Decimal(price) if price is not None else None,
                currency="GBP" if price is not None else None,
                extraction_status=status,
                captured_at=dt,
            )
        )
        await session.commit()


# ── GET /products/failing ───────────────────────────────────────────────────────


class TestListFailingProducts:
    @pytest.mark.asyncio
    async def test_flags_product_with_all_failing_latest(self, pg_async_client, pg_engine):
        # Arrange: latest 3 records all non-ok, no prior success.
        product = await _create_product(pg_async_client)
        pid = product["id"]
        for i, status in enumerate(["extraction_failed", "http_error", "extraction_failed"]):
            await _seed_record(
                pg_engine, pid, status=status, captured_at=f"2026-01-0{i + 1}T10:00:00Z"
            )

        # Act
        resp = await pg_async_client.get("/api/v1/products/failing")

        # Assert
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [item["product"]["id"] for item in body["items"]] == [pid]
        item = body["items"][0]
        assert item["latest_status"] == "extraction_failed"
        assert item["latest_captured_at"].startswith("2026-01-03")
        assert item["last_success_at"] is None

    @pytest.mark.asyncio
    async def test_reports_last_success_at_when_a_prior_ok_exists(self, pg_async_client, pg_engine):
        # Arrange: an early success, then the latest 3 all fail.
        product = await _create_product(pg_async_client)
        pid = product["id"]
        await _seed_record(
            pg_engine, pid, status="ok", captured_at="2026-01-01T09:00:00Z", price="9.99"
        )
        for i, status in enumerate(["extraction_failed"] * 3):
            await _seed_record(
                pg_engine, pid, status=status, captured_at=f"2026-02-0{i + 1}T10:00:00Z"
            )

        # Act
        resp = await pg_async_client.get("/api/v1/products/failing")

        # Assert
        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert item["product"]["id"] == pid
        assert item["last_success_at"].startswith("2026-01-01")

    @pytest.mark.asyncio
    async def test_recent_ok_is_not_flagged(self, pg_async_client, pg_engine):
        # Arrange: two failures then a recovery — latest record is ok.
        product = await _create_product(pg_async_client)
        pid = product["id"]
        await _seed_record(
            pg_engine, pid, status="extraction_failed", captured_at="2026-01-01T10:00:00Z"
        )
        await _seed_record(
            pg_engine, pid, status="extraction_failed", captured_at="2026-01-02T10:00:00Z"
        )
        await _seed_record(
            pg_engine, pid, status="ok", captured_at="2026-01-03T10:00:00Z", price="5.00"
        )

        # Act
        resp = await pg_async_client.get("/api/v1/products/failing")

        # Assert
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_min_failures_param_flags_single_failure(self, pg_async_client, pg_engine):
        # Arrange: a single failure — below default (3) but at/above min_failures=1.
        product = await _create_product(pg_async_client)
        pid = product["id"]
        await _seed_record(
            pg_engine, pid, status="extraction_failed", captured_at="2026-01-01T10:00:00Z"
        )

        # Default threshold does not flag it; min_failures=1 does.
        assert (await pg_async_client.get("/api/v1/products/failing")).json()["items"] == []
        resp = await pg_async_client.get("/api/v1/products/failing", params={"min_failures": 1})
        assert [item["product"]["id"] for item in resp.json()["items"]] == [pid]

    @pytest.mark.asyncio
    async def test_inactive_product_excluded(self, pg_async_client, pg_engine):
        # Arrange: a failing but inactive product is not surfaced.
        product = await _create_product(
            pg_async_client,
            {**PRODUCT_PAYLOAD, "url": "https://example.com/inactive", "is_active": False},
        )
        pid = product["id"]
        for i in range(3):
            await _seed_record(
                pg_engine,
                pid,
                status="extraction_failed",
                captured_at=f"2026-01-0{i + 1}T10:00:00Z",
            )

        resp = await pg_async_client.get("/api/v1/products/failing", params={"min_failures": 1})
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_min_failures_below_one_returns_422(self, pg_async_client):
        resp = await pg_async_client.get("/api/v1/products/failing", params={"min_failures": 0})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_paginates_with_total_and_bounded_limit(self, pg_async_client, pg_engine):
        # Arrange: three failing products (latest record of each is a failure).
        ids = []
        for n in range(3):
            product = await _create_product(
                pg_async_client, {**PRODUCT_PAYLOAD, "url": f"https://example.com/p{n}"}
            )
            pid = product["id"]
            ids.append(pid)
            await _seed_record(
                pg_engine,
                pid,
                status="extraction_failed",
                captured_at=f"2026-03-0{n + 1}T10:00:00Z",
            )

        # Act: first page of two, ordered by product id (service orders by id).
        page1 = await pg_async_client.get(
            "/api/v1/products/failing", params={"min_failures": 1, "limit": 2, "offset": 0}
        )
        page2 = await pg_async_client.get(
            "/api/v1/products/failing", params={"min_failures": 1, "limit": 2, "offset": 2}
        )

        # Assert: total is the full count; each page is the requested slice.
        assert page1.status_code == 200, page1.text
        b1 = page1.json()
        assert b1["total"] == 3
        assert b1["limit"] == 2
        assert b1["offset"] == 0
        assert [i["product"]["id"] for i in b1["items"]] == sorted(ids)[:2]

        b2 = page2.json()
        assert b2["total"] == 3
        assert [i["product"]["id"] for i in b2["items"]] == sorted(ids)[2:]

    @pytest.mark.asyncio
    async def test_limit_above_100_is_rejected(self, pg_async_client):
        # The response envelope caps limit at 100; the query param enforces it up front.
        resp = await pg_async_client.get("/api/v1/products/failing", params={"limit": 101})
        assert resp.status_code == 422


# ── monitoring_service.find_failing_products (direct) ───────────────────────────


@pytest.mark.asyncio
async def test_find_failing_products_rejects_min_failures_below_one(pg_session):
    from app.services.monitoring_service import find_failing_products

    with pytest.raises(ValueError, match="min_failures must be >= 1"):
        await find_failing_products(pg_session, min_failures=0)
