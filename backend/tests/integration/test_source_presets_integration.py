"""Integration tests for configurable monitoring sources (Item 18).

Uses the Postgres testcontainer (``pg_async_client``/``pg_session``) because
creating products exercises the BigInteger PK autoincrement, which SQLite does
not provide. The six built-in presets are seeded into the test engine (conftest).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


# ── product creation across the new source types ──────────────────────────────
@pytest.mark.parametrize("source_type", ["ebay", "currys", "john_lewis", "facebook_marketplace"])
@pytest.mark.asyncio
async def test_create_product_with_new_source_type_persists(pg_async_client, source_type):
    # ebay/currys were advertised by the old enum but had no scraper (accepted at
    # create, UnknownSourceError at scrape); john_lewis/facebook_marketplace are
    # brand new. All four are now valid, enabled presets.
    resp = await pg_async_client.post(
        "/api/v1/products",
        json={
            "name": f"{source_type} product",
            "url": f"https://example.com/{source_type}",
            "source_type": source_type,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source_type"] == source_type

    got = await pg_async_client.get(f"/api/v1/products/{body['id']}")
    assert got.status_code == 200
    assert got.json()["source_type"] == source_type


@pytest.mark.asyncio
async def test_create_generic_product_round_trips_css_selector_currency(pg_async_client):
    # css_selector_currency exists on the model but was unreachable via the API
    # before Item 18.
    resp = await pg_async_client.post(
        "/api/v1/products",
        json={
            "name": "Generic",
            "url": "https://example.com/generic-cc",
            "source_type": "generic",
            "css_selector": ".price",
            "css_selector_currency": ".currency",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["css_selector_currency"] == ".currency"


@pytest.mark.asyncio
async def test_update_product_to_disabled_or_unknown_source_type_returns_422(pg_async_client):
    created = await pg_async_client.post(
        "/api/v1/products",
        json={
            "name": "P",
            "url": "https://example.com/upd",
            "source_type": "generic",
            "css_selector": ".p",
        },
    )
    pid = created.json()["id"]
    resp = await pg_async_client.patch(f"/api/v1/products/{pid}", json={"source_type": "bogus"})
    assert resp.status_code == 422


# ── queue routing is data-driven (preset-carried) ─────────────────────────────
@pytest.mark.parametrize(
    ("source_type", "expected_queue"),
    [
        ("generic", "default"),
        ("ebay", "default"),
        ("amazon", "playwright"),
        ("currys", "playwright"),
        ("john_lewis", "playwright"),
        ("facebook_marketplace", "playwright"),
    ],
)
@pytest.mark.asyncio
async def test_queue_for_source_type_reads_preset_queue(pg_session, source_type, expected_queue):
    from app.scrapers.registry import queue_for_source_type

    assert await queue_for_source_type(source_type, pg_session) == expected_queue


# ── GET /api/v1/sources ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_sources_endpoint_returns_seeded_presets(pg_async_client):
    resp = await pg_async_client.get("/api/v1/sources")
    assert resp.status_code == 200
    keys = {item["key"] for item in resp.json()}
    assert {"generic", "amazon", "ebay", "currys", "john_lewis", "facebook_marketplace"} == keys


# ── scrape dispatch resolves the new scrapers end-to-end ──────────────────────
@pytest.mark.asyncio
async def test_get_scraper_resolves_all_seeded_sources(pg_session):
    from app.scrapers.currys import CurrysScraper
    from app.scrapers.ebay import EbayScraper
    from app.scrapers.facebook_marketplace import FacebookMarketplaceScraper
    from app.scrapers.john_lewis import JohnLewisScraper
    from app.scrapers.registry import get_scraper

    expected = {
        "ebay": EbayScraper,
        "currys": CurrysScraper,
        "john_lewis": JohnLewisScraper,
        "facebook_marketplace": FacebookMarketplaceScraper,
    }
    for source_type, cls in expected.items():
        scraper = await get_scraper(source_type, pg_session)
        assert isinstance(scraper, cls)


# ── schedule re-sync on update (routing/activity changes) ─────────────────────
@pytest.mark.asyncio
async def test_update_source_type_reregisters_schedule_on_new_queue(pg_async_client, monkeypatch):
    # Changing generic (default queue) → amazon (playwright queue) must re-register
    # the RedBeat schedule on the new queue, else the scheduled scrape lands on the
    # browserless worker and fails.
    import app.tasks.schedule as sched

    calls: list[tuple[int, str]] = []
    monkeypatch.setattr(
        sched, "register_product_schedule", lambda pid, interval, queue: calls.append((pid, queue))
    )

    created = await pg_async_client.post(
        "/api/v1/products",
        json={
            "name": "P",
            "url": "https://example.com/resync",
            "source_type": "generic",
            "css_selector": ".p",
        },
    )
    pid = created.json()["id"]
    calls.clear()

    resp = await pg_async_client.patch(f"/api/v1/products/{pid}", json={"source_type": "amazon"})
    assert resp.status_code == 200, resp.text
    assert calls and calls[-1] == (pid, "playwright")


@pytest.mark.asyncio
async def test_deactivating_product_deregisters_schedule(pg_async_client, monkeypatch):
    import app.tasks.schedule as sched

    removed: list[int] = []
    monkeypatch.setattr(sched, "deregister_product_schedule", lambda pid: removed.append(pid))

    created = await pg_async_client.post(
        "/api/v1/products",
        json={
            "name": "P",
            "url": "https://example.com/deact",
            "source_type": "generic",
            "css_selector": ".p",
        },
    )
    pid = created.json()["id"]

    resp = await pg_async_client.patch(f"/api/v1/products/{pid}", json={"is_active": False})
    assert resp.status_code == 200, resp.text
    assert pid in removed
