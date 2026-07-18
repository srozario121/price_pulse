"""Source-preset resolution and ``source_type`` validation.

The single DB-backed authority for "what is a valid source type" (Item 18).
Replaces the two divergent hardcoded ``SourceType`` enums. Module-level async
functions taking an explicit ``AsyncSession``, matching the repo's service
convention (no service classes).

Consumed by:
  * ``scrapers/registry.py`` — resolve the scraper class + Celery queue.
  * ``api/v1/products.py`` — validate ``source_type`` on create/update (422).
  * ``api/v1/sources.py`` — list enabled presets for the frontend form.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source_preset import SourcePreset

# ── Built-in presets ──────────────────────────────────────────────────────────
# The canonical six sources shipped with the platform. Single source of truth for
# both the seed migration (0007) and the test-engine seeding, so they never drift.
# queue: browser-driven scrapers (Playwright/Chromium) run on "playwright";
# httpx-based scrapers run on "default".
BUILTIN_SOURCE_PRESETS: list[dict[str, object]] = [
    {
        "source_type": "generic",
        "label": "Generic (CSS selector)",
        "host_patterns": [],
        "strategy": "generic",
        "queue": "default",
    },
    {
        "source_type": "amazon",
        "label": "Amazon",
        "host_patterns": ["amazon.co.uk", "amazon.com"],
        "strategy": "amazon",
        "queue": "playwright",
    },
    {
        "source_type": "ebay",
        "label": "eBay UK",
        "host_patterns": ["ebay.co.uk"],
        "strategy": "ebay",
        "queue": "default",
    },
    {
        "source_type": "currys",
        "label": "Currys",
        "host_patterns": ["currys.co.uk"],
        "strategy": "currys",
        "queue": "playwright",
    },
    {
        "source_type": "john_lewis",
        "label": "John Lewis",
        "host_patterns": ["johnlewis.com"],
        "strategy": "john_lewis",
        "queue": "playwright",
    },
    {
        "source_type": "facebook_marketplace",
        "label": "Facebook Marketplace",
        "host_patterns": ["facebook.com"],
        "strategy": "facebook_marketplace",
        "queue": "playwright",
    },
]


async def list_enabled_presets(session: AsyncSession) -> list[SourcePreset]:
    """Return all enabled presets, ordered by ``source_type`` for stable output."""
    result = await session.execute(
        select(SourcePreset)
        .where(SourcePreset.enabled.is_(True))
        .order_by(SourcePreset.source_type)
    )
    return list(result.scalars().all())


async def resolve_enabled_preset(session: AsyncSession, source_type: str) -> SourcePreset | None:
    """Return the *enabled* preset for *source_type*, or ``None``.

    A disabled preset resolves to ``None`` — from the caller's perspective a
    disabled source is indistinguishable from an unknown one.
    """
    return await session.scalar(
        select(SourcePreset).where(
            SourcePreset.source_type == source_type,
            SourcePreset.enabled.is_(True),
        )
    )


async def is_valid_source_type(session: AsyncSession, source_type: str) -> bool:
    """True iff *source_type* is a known and enabled preset key."""
    return await resolve_enabled_preset(session, source_type) is not None
