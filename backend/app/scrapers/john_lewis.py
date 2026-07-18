"""John Lewis scraper — Playwright path (React/SPA), UK retailer (Item 18).

johnlewis.com is a client-rendered SPA that publishes ``ld+json`` product data on
its PDPs; extraction is ld+json-first with a CSS-selector DOM fallback. Runs on
the ``playwright`` queue.
"""

from __future__ import annotations

from app.scrapers.playwright_base import PlaywrightScraper


class JohnLewisScraper(PlaywrightScraper):
    """Scraper for johnlewis.com product pages."""

    DEFAULT_CURRENCY = "GBP"
    PRICE_SELECTORS = (
        '[data-testid="product-price"] [data-testid="now-price"]',
        '[data-testid="price-now"]',
        'span[itemprop="price"]',
        ".price .price__now",
        ".ProductPrice span",
    )
