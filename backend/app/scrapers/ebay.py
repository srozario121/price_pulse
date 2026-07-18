"""eBay UK scraper — httpx path with ld+json / structured-data extraction (Item 18).

eBay serves fully-rendered HTML containing an ``application/ld+json`` Product
block on most listing pages, so it does not need a browser: it fetches via the
shared httpx client (``default`` queue) and parses price + currency out of the
structured data, with a CSS-selector DOM fallback for listings that ship without
ld+json.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import structlog

from app.models.enums import ExtractionStatus
from app.schemas.scraper import ScrapedResult
from app.scrapers.base import BaseScraper
from app.scrapers.http_client import fetch_page

logger = structlog.get_logger()

_DEFAULT_CURRENCY = "GBP"

# DOM fallback selectors (buy-box first) for listings without ld+json.
_DOM_PRICE_SELECTORS: tuple[str, ...] = (
    'meta[itemprop="price"]::attr(content)',
    ".x-price-primary .ux-textspans::text",
    'span[itemprop="price"]::text',
    ".display-price::text",
)
_DOM_CURRENCY_SELECTORS: tuple[str, ...] = (
    'meta[itemprop="priceCurrency"]::attr(content)',
    'span[itemprop="priceCurrency"]::attr(content)',
)


def _iter_ld_nodes(data: object) -> list[dict]:
    """Flatten an ld+json payload (object, list, or ``@graph``) into a node list."""
    if isinstance(data, list):
        nodes: list[dict] = []
        for entry in data:
            nodes.extend(_iter_ld_nodes(entry))
        return nodes
    if isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            return _iter_ld_nodes(data["@graph"])
        return [data]
    return []


def _offer_price(node: dict) -> tuple[str, str | None] | None:
    """Return ``(price, currency)`` from a node's ``offers`` block, if present."""
    offers = node.get("offers")
    if offers is None:
        return None
    offer = offers[0] if isinstance(offers, list) and offers else offers
    if not isinstance(offer, dict):
        return None
    price = offer.get("price")
    if price is None:
        return None
    return str(price), offer.get("priceCurrency")


def _extract_from_ld_json(html: str) -> tuple[Decimal, str | None] | None:
    """Extract ``(price, currency)`` from the first ld+json offer with a price."""
    from parsel import Selector

    selector = Selector(text=html)
    for block in selector.css('script[type="application/ld+json"]::text').getall():
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        for node in _iter_ld_nodes(data):
            found = _offer_price(node)
            if found is None:
                continue
            raw_price, currency = found
            try:
                return Decimal(raw_price), currency
            except InvalidOperation:
                continue
    return None


def _first_css(selector: object, css_list: tuple[str, ...]) -> str | None:
    """Return the first non-empty match across *css_list*, or ``None``."""
    for css in css_list:
        value = selector.css(css).get()  # type: ignore[attr-defined]
        if value:
            return value
    return None


def _extract_from_dom(html: str) -> tuple[Decimal, str | None] | None:
    """Fallback: extract ``(price, currency)`` from meta/DOM price selectors."""
    import re

    from parsel import Selector

    selector = Selector(text=html)
    raw_price = _first_css(selector, _DOM_PRICE_SELECTORS)
    if not raw_price:
        return None

    cleaned = re.sub(r"[^0-9.,]", "", raw_price).replace(",", "")
    try:
        price = Decimal(cleaned)
    except InvalidOperation:
        return None

    return price, _first_css(selector, _DOM_CURRENCY_SELECTORS)


class EbayScraper(BaseScraper):
    """Scraper for ebay.co.uk listing pages (httpx + ld+json)."""

    def __init__(self, redis_client: object | None = None) -> None:
        self._redis_client = redis_client

    async def fetch(self, url: str) -> ScrapedResult:
        result = await fetch_page(url, redis_client=self._redis_client)

        # Propagate non-OK fetches unchanged (http_error / blocked / captcha) —
        # a block must never be treated as an extraction failure.
        if result.extraction_status != ExtractionStatus.OK:
            return result

        extracted = _extract_from_ld_json(result.html) or _extract_from_dom(result.html)
        if extracted is None:
            logger.warning("ebay_scraper_no_price", url=url)
            return ScrapedResult(
                url=url,
                html=result.html,
                html_hash=result.html_hash,
                price=None,
                currency=None,
                scraped_at=datetime.now(UTC),
                extraction_status=ExtractionStatus.EXTRACTION_FAILED,
            )

        price, currency = extracted
        return ScrapedResult(
            url=url,
            html=result.html,
            html_hash=result.html_hash,
            price=price,
            currency=currency or _DEFAULT_CURRENCY,
            scraped_at=datetime.now(UTC),
            extraction_status=ExtractionStatus.OK,
        )
