"""Integration tests for the scrape-job read endpoints (Item 17).

Uses ``pg_async_client`` (Postgres testcontainer): the endpoints query the real
``scrape_job`` table with ordering/pagination/filters over seeded rows.
"""

from __future__ import annotations

from datetime import datetime

import pytest

PRODUCT_PAYLOAD = {
    "name": "Widget",
    "url": "https://example.com/widget",
    "source_type": "generic",
    "css_selector": ".price",
    "is_active": True,
}


async def _create_product(client, url: str = "https://example.com/widget") -> dict:
    payload = {**PRODUCT_PAYLOAD, "url": url}
    resp = await client.post("/api/v1/products", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _seed_job(
    pg_engine,
    *,
    product_id: int,
    task_id: str,
    status: str = "queued",
    queue: str = "default",
    trigger: str = "scheduled",
    enqueued_at: str = "2026-07-19T10:00:00Z",
    extraction_status: str | None = None,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.scrape_job import ScrapeJob

    dt = datetime.fromisoformat(enqueued_at.replace("Z", "+00:00"))
    factory = async_sessionmaker(bind=pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(
            ScrapeJob(
                product_id=product_id,
                task_id=task_id,
                status=status,
                queue=queue,
                trigger=trigger,
                enqueued_at=dt,
                extraction_status=extraction_status,
            )
        )
        await session.commit()


# ── GET /scrape-jobs ────────────────────────────────────────────────────────────


class TestListScrapeJobs:
    @pytest.mark.asyncio
    async def test_orders_newest_first_and_paginates(self, pg_async_client, pg_engine):
        # Arrange
        product = await _create_product(pg_async_client)
        pid = product["id"]
        await _seed_job(pg_engine, product_id=pid, task_id="t1", enqueued_at="2026-07-19T10:00:00Z")
        await _seed_job(pg_engine, product_id=pid, task_id="t2", enqueued_at="2026-07-19T11:00:00Z")
        await _seed_job(pg_engine, product_id=pid, task_id="t3", enqueued_at="2026-07-19T12:00:00Z")

        # Act
        resp = await pg_async_client.get("/api/v1/scrape-jobs", params={"limit": 2})

        # Assert — newest first, page of 2, total 3
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 3
        assert [j["task_id"] for j in body["items"]] == ["t3", "t2"]

    @pytest.mark.asyncio
    async def test_filters_by_product_status_queue_task_id(self, pg_async_client, pg_engine):
        # Arrange
        p1 = await _create_product(pg_async_client, url="https://example.com/a")
        p2 = await _create_product(pg_async_client, url="https://example.com/b")
        await _seed_job(
            pg_engine, product_id=p1["id"], task_id="ok-1", status="success", queue="default"
        )
        await _seed_job(
            pg_engine, product_id=p1["id"], task_id="fail-1", status="failure", queue="playwright"
        )
        await _seed_job(
            pg_engine, product_id=p2["id"], task_id="ok-2", status="success", queue="default"
        )

        # Act / Assert — product filter
        r = await pg_async_client.get("/api/v1/scrape-jobs", params={"product_id": p2["id"]})
        assert [j["task_id"] for j in r.json()["items"]] == ["ok-2"]

        # status filter
        r = await pg_async_client.get("/api/v1/scrape-jobs", params={"status": "failure"})
        assert [j["task_id"] for j in r.json()["items"]] == ["fail-1"]

        # queue filter
        r = await pg_async_client.get("/api/v1/scrape-jobs", params={"queue": "playwright"})
        assert [j["task_id"] for j in r.json()["items"]] == ["fail-1"]

        # task_id filter
        r = await pg_async_client.get("/api/v1/scrape-jobs", params={"task_id": "ok-1"})
        assert [j["task_id"] for j in r.json()["items"]] == ["ok-1"]

    @pytest.mark.asyncio
    async def test_unknown_status_is_422(self, pg_async_client):
        resp = await pg_async_client.get("/api/v1/scrape-jobs", params={"status": "bogus"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_limit_over_100_is_422(self, pg_async_client):
        resp = await pg_async_client.get("/api/v1/scrape-jobs", params={"limit": 101})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_absent_product_id_is_empty_not_404(self, pg_async_client):
        resp = await pg_async_client.get("/api/v1/scrape-jobs", params={"product_id": 999999})
        assert resp.status_code == 200
        assert resp.json()["items"] == []


# ── GET /products/{id}/scrape-jobs ──────────────────────────────────────────────


class TestListProductScrapeJobs:
    @pytest.mark.asyncio
    async def test_scoped_to_product(self, pg_async_client, pg_engine):
        p1 = await _create_product(pg_async_client, url="https://example.com/a")
        p2 = await _create_product(pg_async_client, url="https://example.com/b")
        await _seed_job(pg_engine, product_id=p1["id"], task_id="a1")
        await _seed_job(pg_engine, product_id=p2["id"], task_id="b1")

        resp = await pg_async_client.get(f"/api/v1/products/{p1['id']}/scrape-jobs")
        assert resp.status_code == 200
        assert [j["task_id"] for j in resp.json()["items"]] == ["a1"]

    @pytest.mark.asyncio
    async def test_unknown_product_is_404(self, pg_async_client):
        resp = await pg_async_client.get("/api/v1/products/999999/scrape-jobs")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_product_without_jobs_is_empty(self, pg_async_client):
        product = await _create_product(pg_async_client)
        resp = await pg_async_client.get(f"/api/v1/products/{product['id']}/scrape-jobs")
        assert resp.status_code == 200
        assert resp.json()["items"] == []


# ── GET /scrape-jobs/queue-depth ────────────────────────────────────────────────


class TestQueueDepth:
    @pytest.mark.asyncio
    async def test_degrades_gracefully_without_broker(self, pg_async_client):
        # No live broker/worker in the test env → best-effort payload with the
        # known queues present and unknown/zero counts, never a 500 or a hang.
        resp = await pg_async_client.get("/api/v1/scrape-jobs/queue-depth")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        queue_names = {q["queue"] for q in body["queues"]}
        assert {"default", "playwright"} <= queue_names
        assert "workers_online" in body
