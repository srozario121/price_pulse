"""Currys scraper — Playwright path (React/SPA), UK retailer (Item 18).

Currys renders its buy-box price client-side and exposes ``ld+json`` product data
on most PDPs, so extraction is ld+json-first with a CSS-selector DOM fallback for
pages that ship without structured data. Runs on the ``playwright`` queue.
"""

from __future__ import annotations

from app.scrapers.playwright_base import PlaywrightScraper


class CurrysScraper(PlaywrightScraper):
    """Scraper for currys.co.uk product pages."""

    DEFAULT_CURRENCY = "GBP"
    PRICE_SELECTORS = (
        '[data-testid="product-price"] .value',
        ".product-price__current",
        ".product-price .value",
        'span[itemprop="price"]',
        ".price .value",
    )
