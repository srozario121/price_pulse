"""Data-driven scraper registry, resolved from the SourcePreset table (Item 18).

The two divergent hardcoded ``SourceType`` enums (``models/product.py`` +
this module) are gone. A source type is now valid iff an *enabled* ``SourcePreset``
row exists for it; the preset declares the extraction ``strategy`` (which scraper
class runs) and the Celery ``queue`` (which worker executes it). Onboarding a new
UK retailer is therefore a data change, not a code + enum + migration change.

``strategy`` → scraper class is the one thing that stays in code (the classes are
code), mapped by ``_STRATEGY_REGISTRY`` below.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.scrapers.amazon import AmazonScraper
from app.scrapers.base import BaseScraper
from app.scrapers.currys import CurrysScraper
from app.scrapers.ebay import EbayScraper
from app.scrapers.exceptions import UnknownSourceError
from app.scrapers.facebook_marketplace import FacebookMarketplaceScraper
from app.scrapers.generic import GenericScraper
from app.scrapers.john_lewis import JohnLewisScraper
from app.services import source_preset_service

# ── Celery queue routing ────────────────────────────────────────────────────────
# Browser-driven (Playwright/Chromium) scrapers must run on the dedicated
# "playwright" worker; every httpx-based scraper runs on "default". The queue is
# now carried per-preset (data-driven) rather than a hardcoded frozenset — adding
# a browser-required retailer no longer needs a code change here.
DEFAULT_QUEUE = "default"
PLAYWRIGHT_QUEUE = "playwright"

# strategy → scraper class. The preset's ``strategy`` selects the implementation.
_STRATEGY_REGISTRY: dict[str, type[BaseScraper]] = {
    "generic": GenericScraper,
    "amazon": AmazonScraper,
    "ebay": EbayScraper,
    "currys": CurrysScraper,
    "john_lewis": JohnLewisScraper,
    "facebook_marketplace": FacebookMarketplaceScraper,
}

# Strategies whose scraper accepts the per-product CSS-selector kwargs.
_SELECTOR_STRATEGIES = frozenset({"generic"})


async def queue_for_source_type(source_type: str, session: AsyncSession) -> str:
    """Return the Celery queue that can execute *source_type*'s scraper.

    Unknown/disabled source types fall back to the default queue; the scraper
    lookup (:func:`get_scraper`) surfaces the real ``UnknownSourceError`` when the
    task actually runs, so queue routing stays best-effort and never 500s a
    schedule registration.
    """
    preset = await source_preset_service.resolve_enabled_preset(session, source_type)
    return preset.queue if preset is not None else DEFAULT_QUEUE


async def get_scraper(
    source_type: str,
    session: AsyncSession,
    *,
    css_selector: str | None = None,
    css_selector_currency: str | None = None,
) -> BaseScraper:
    """Return a configured scraper for *source_type*, resolved from its preset.

    Raises ``UnknownSourceError`` when no *enabled* preset exists for
    *source_type*, or when its preset declares a strategy with no registered
    scraper class.
    """
    preset = await source_preset_service.resolve_enabled_preset(session, source_type)
    if preset is None:
        raise UnknownSourceError(f"No enabled source preset for source_type={source_type!r}")

    scraper_cls = _STRATEGY_REGISTRY.get(preset.strategy)
    if scraper_cls is None:
        raise UnknownSourceError(
            f"Source preset {source_type!r} declares unknown strategy {preset.strategy!r}"
        )

    if preset.strategy in _SELECTOR_STRATEGIES:
        return scraper_cls(
            css_selector=css_selector,
            css_selector_currency=css_selector_currency,
        )
    return scraper_cls()
