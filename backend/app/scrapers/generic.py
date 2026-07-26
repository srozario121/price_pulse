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


def _extract_text(selector: object, css: str) -> str | None:
    """Return the visible text of the first element matching *css*, or ``None``.

    A bare element selector must yield the element's *text*, not its outer HTML —
    ``.css(x).get()`` returns markup, so a class name containing a hyphen or a
    digit (``.pdp-price``, ``.price-2``) would leak into the parsed number. That
    is a latent trap for hand-written selectors and a certainty for
    LLM-generated ones (Item 16), which routinely target hyphenated classes.

    A selector that already carries a pseudo-element (``::text``, ``::attr(...)``)
    is passed through untouched — the caller asked for something specific.
    """
    if "::" in css:
        return selector.css(css).get()  # type: ignore[attr-defined]
    matches = selector.css(css)  # type: ignore[attr-defined]
    if not matches:
        return None
    text = "".join(matches[0].css("::text").getall()).strip()
    return text or None


def _resolve_currency(selector: object, css_selector_currency: str | None) -> str:
    """Extract currency from *html* using *css_selector_currency*, defaulting to USD."""
    if css_selector_currency is None:
        return "USD"
    currency_text = _extract_text(selector, css_selector_currency)
    if currency_text is not None:
        symbol = currency_text.strip()
        return _CURRENCY_SYMBOL_MAP.get(symbol, symbol) or "USD"
    return "USD"


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

    def _candidate_selectors(self) -> list[tuple[str, str | None]]:
        """Return ``(price_selector, currency_selector)`` pairs, best first.

        The product's own configured selector wins — it was set deliberately by
        whoever added the product. The host's stored LLM-generated selector
        (Item 16) is the fallback that heals the source after markup drift.
        """
        candidates = [(self.css_selector, self.css_selector_currency)]
        learned = self.learned_selector
        if learned is not None and learned.price_selector != self.css_selector:
            candidates.append((learned.price_selector, learned.currency_selector))
        return [(price, currency) for price, currency in candidates if price is not None]

    def _match_price(self, selector: object) -> tuple[str | None, str | None]:
        """Return the first ``(price_text, currency_selector)`` a candidate matches.

        ``(None, None)`` means every candidate missed — markup drift.
        """
        for price_css, currency_css in self._candidate_selectors():
            price_text = _extract_text(selector, price_css)
            if price_text is not None:
                return price_text, currency_css
        return None, None

    async def fetch(self, url: str) -> ScrapedResult:
        """Fetch *url* and extract price using the configured CSS selectors.

        A page that loads fine but matches no selector resolves to
        ``SELECTOR_MISS`` (markup drift → regeneration), while a matched element
        whose text will not parse stays ``EXTRACTION_FAILED``.
        """
        if self.css_selector is None and self.learned_selector is None:
            raise ScraperError("css_selector is required for GenericScraper")

        result = await fetch_page(url, redis_client=self._redis_client)

        if result.extraction_status != ExtractionStatus.OK:
            return result

        html_hash = self._compute_hash(result.html)

        # Lazy import to keep module testable with simple mocking
        from parsel import Selector

        selector = Selector(text=result.html)
        raw_price_text, currency_selector = self._match_price(selector)

        if raw_price_text is None:
            logger.warning(
                "generic_scraper_no_price_match",
                url=url,
                css_selector=self.css_selector,
                had_learned_selector=self.learned_selector is not None,
            )
            return ScrapedResult(
                url=url,
                html=result.html,
                html_hash=html_hash,
                price=None,
                currency=None,
                scraped_at=datetime.now(UTC),
                extraction_status=ExtractionStatus.SELECTOR_MISS,
            )

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

        currency = _resolve_currency(selector, currency_selector)

        return ScrapedResult(
            url=url,
            html=result.html,
            html_hash=html_hash,
            price=price,
            currency=currency,
            scraped_at=datetime.now(UTC),
            extraction_status=ExtractionStatus.OK,
        )
