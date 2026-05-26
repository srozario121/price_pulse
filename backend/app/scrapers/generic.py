"""CSS-selector-driven generic scraper adapter."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import structlog

from app.models.enums import ExtractionStatus
from app.schemas.scraper import ScrapedResult
from app.scrapers.base import BaseScraper
from app.scrapers.exceptions import ScraperError
from app.scrapers.http_client import fetch_page

logger = structlog.get_logger()

# Mapping from common currency symbols to ISO 4217 codes
_CURRENCY_SYMBOL_MAP: dict[str, str] = {
    "$": "USD",
    "£": "GBP",
    "€": "EUR",
}


class GenericScraper(BaseScraper):
    """Scraper driven by CSS selectors stored on the Product record."""

    def __init__(
        self,
        css_selector: str | None = None,
        css_selector_currency: str | None = None,
        redis_client: object | None = None,
    ) -> None:
        self.css_selector = css_selector
        self.css_selector_currency = css_selector_currency
        self._redis_client = redis_client

    async def fetch(self, url: str) -> ScrapedResult:
        """Fetch *url* and extract price using the configured CSS selectors."""
        if self.css_selector is None:
            raise ScraperError("css_selector is required for GenericScraper")

        result = await fetch_page(url, redis_client=self._redis_client)

        if result.extraction_status != ExtractionStatus.OK:
            return result

        html_hash = self._compute_hash(result.html)

        # Lazy import to keep module testable with simple mocking
        from parsel import Selector  # type: ignore[import-untyped]

        selector = Selector(text=result.html)
        raw_price_text = selector.css(self.css_selector).get()

        if raw_price_text is None:
            logger.warning(
                "generic_scraper_no_price_match",
                url=url,
                css_selector=self.css_selector,
            )
            return ScrapedResult(
                url=url,
                html=result.html,
                html_hash=html_hash,
                price=None,
                currency=None,
                scraped_at=datetime.now(UTC),
                extraction_status=ExtractionStatus.EXTRACTION_FAILED,
            )

        # Strip everything except digits, decimal point, and minus sign
        cleaned = re.sub(r"[^\d.\-]", "", raw_price_text.strip())
        try:
            price = Decimal(cleaned)
        except InvalidOperation:
            logger.warning(
                "generic_scraper_price_parse_failed",
                url=url,
                raw=raw_price_text,
                cleaned=cleaned,
            )
            return ScrapedResult(
                url=url,
                html=result.html,
                html_hash=html_hash,
                price=None,
                currency=None,
                scraped_at=datetime.now(UTC),
                extraction_status=ExtractionStatus.EXTRACTION_FAILED,
            )

        # Currency extraction — append ::text to extract text content not outer HTML
        currency: str | None = None
        if self.css_selector_currency is not None:
            # Support selectors that already have ::text and those that don't
            text_selector = (
                self.css_selector_currency
                if "::text" in self.css_selector_currency
                else f"{self.css_selector_currency} ::text"
            )
            currency_text = selector.css(text_selector).get()
            if currency_text is None:
                # Try without the space (direct child text)
                currency_text = selector.css(
                    self.css_selector_currency.rstrip() + "::text"
                ).get()
            if currency_text is not None:
                symbol = currency_text.strip()
                currency = _CURRENCY_SYMBOL_MAP.get(symbol, symbol) or "USD"
            else:
                currency = "USD"
        else:
            currency = "USD"

        return ScrapedResult(
            url=url,
            html=result.html,
            html_hash=html_hash,
            price=price,
            currency=currency,
            scraped_at=datetime.now(UTC),
            extraction_status=ExtractionStatus.OK,
        )
