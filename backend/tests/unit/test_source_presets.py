"""Unit tests for the source-preset registry, /sources endpoint, and source_type
validation (Item 18). SQLite-backed via the seeded ``db_session``/``async_client``.
"""

from __future__ import annotations

import pytest

from app.services import source_preset_service


def test_builtin_presets_constant_shape() -> None:
    # Single source of truth shared by the seed migration and test seeding.
    keys = {p["source_type"] for p in source_preset_service.BUILTIN_SOURCE_PRESETS}
    assert keys == {"generic", "amazon", "ebay", "currys", "john_lewis", "facebook_marketplace"}
    required = {"source_type", "label", "host_patterns", "strategy", "queue"}
    for preset in source_preset_service.BUILTIN_SOURCE_PRESETS:
        assert required <= preset.keys()
    # Browser-driven strategies route to the playwright queue.
    by_key = {p["source_type"]: p for p in source_preset_service.BUILTIN_SOURCE_PRESETS}
    assert by_key["amazon"]["queue"] == "playwright"
    assert by_key["ebay"]["queue"] == "default"


# ── source_preset_service ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_enabled_presets_returns_six_builtins(db_session) -> None:
    presets = await source_preset_service.list_enabled_presets(db_session)
    keys = {p.source_type for p in presets}
    assert keys == {"generic", "amazon", "ebay", "currys", "john_lewis", "facebook_marketplace"}


@pytest.mark.asyncio
async def test_resolve_enabled_preset_known_key(db_session) -> None:
    preset = await source_preset_service.resolve_enabled_preset(db_session, "currys")
    assert preset is not None
    assert preset.strategy == "currys"
    assert preset.queue == "playwright"


@pytest.mark.asyncio
async def test_resolve_enabled_preset_unknown_key_is_none(db_session) -> None:
    assert await source_preset_service.resolve_enabled_preset(db_session, "nope") is None


@pytest.mark.asyncio
async def test_is_valid_source_type(db_session) -> None:
    assert await source_preset_service.is_valid_source_type(db_session, "ebay") is True
    assert await source_preset_service.is_valid_source_type(db_session, "nonexistent") is False


@pytest.mark.asyncio
async def test_disabled_preset_resolves_as_invalid(db_session) -> None:
    # A disabled preset is indistinguishable from unknown to callers.
    from sqlalchemy import select

    from app.models.source_preset import SourcePreset

    preset = await db_session.scalar(select(SourcePreset).where(SourcePreset.source_type == "ebay"))
    preset.enabled = False
    await db_session.flush()

    assert await source_preset_service.is_valid_source_type(db_session, "ebay") is False
    assert await source_preset_service.resolve_enabled_preset(db_session, "ebay") is None


@pytest.mark.asyncio
async def test_get_scraper_skips_disabled_preset(db_session) -> None:
    from sqlalchemy import select

    from app.models.source_preset import SourcePreset
    from app.scrapers.exceptions import UnknownSourceError
    from app.scrapers.registry import get_scraper

    preset = await db_session.scalar(
        select(SourcePreset).where(SourcePreset.source_type == "currys")
    )
    preset.enabled = False
    await db_session.flush()

    with pytest.raises(UnknownSourceError):
        await get_scraper("currys", db_session)


# ── GET /api/v1/sources ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_sources_endpoint_lists_enabled_presets(async_client) -> None:
    resp = await async_client.get("/api/v1/sources")
    assert resp.status_code == 200
    body = resp.json()
    keys = {item["key"] for item in body}
    assert {"generic", "amazon", "ebay", "currys", "john_lewis", "facebook_marketplace"} == keys
    # Each entry carries a human label and the routing queue.
    ebay = next(item for item in body if item["key"] == "ebay")
    assert ebay["label"] == "eBay UK"
    assert ebay["queue"] == "default"
    amazon = next(item for item in body if item["key"] == "amazon")
    assert amazon["queue"] == "playwright"


# ── source_type validation at the API boundary (422) ──────────────────────────
@pytest.mark.asyncio
async def test_create_product_unknown_source_type_returns_422(async_client) -> None:
    resp = await async_client.post(
        "/api/v1/products",
        json={"name": "X", "url": "https://ex.com/a", "source_type": "not_a_source"},
    )
    assert resp.status_code == 422
    assert "not_a_source" in resp.json()["detail"]


# NOTE: tests that *create* a product exercise the BigInteger PK autoincrement,
# which SQLite does not provide — they live in the integration tier (Postgres):
# tests/integration/test_source_presets_integration.py.
