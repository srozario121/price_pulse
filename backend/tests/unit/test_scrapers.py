"""Unit tests for scraper layer — BaseScraper, GenericScraper, AmazonScraper, registry."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.models.enums import ExtractionStatus
from app.schemas.scraper import ScrapedResult
from app.scrapers.base import BaseScraper
from app.scrapers.exceptions import ScraperError, UnknownSourceError
from app.scrapers.generic import GenericScraper
from app.scrapers.registry import get_scraper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok_result(url: str, html: str) -> ScrapedResult:
    return ScrapedResult(
        url=url,
        html=html,
        html_hash="a" * 64,
        price=None,
        currency=None,
        scraped_at=datetime.now(UTC),
        extraction_status=ExtractionStatus.OK,
    )


def _error_result(url: str) -> ScrapedResult:
    return ScrapedResult(
        url=url,
        html="",
        html_hash="",
        price=None,
        currency=None,
        scraped_at=datetime.now(UTC),
        extraction_status=ExtractionStatus.HTTP_ERROR,
    )


# ---------------------------------------------------------------------------
# BaseScraper
# ---------------------------------------------------------------------------


def test_base_scraper_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseScraper()  # type: ignore[abstract]


def test_compute_hash_returns_sha256() -> None:
    text = "hello"
    expected = hashlib.sha256(text.encode()).hexdigest()

    class _DummyScraper(BaseScraper):
        async def fetch(self, url: str) -> ScrapedResult:  # pragma: no cover
            return _ok_result(url, "")

    scraper = _DummyScraper()
    assert scraper._compute_hash(text) == expected


def test_compute_hash_empty_string() -> None:
    class _DummyScraper(BaseScraper):
        async def fetch(self, url: str) -> ScrapedResult:  # pragma: no cover
            return _ok_result(url, "")

    scraper = _DummyScraper()
    assert scraper._compute_hash("") == hashlib.sha256(b"").hexdigest()


# ---------------------------------------------------------------------------
# GenericScraper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generic_scraper_success() -> None:
    html = '<html><span class="price_color">£9.99</span></html>'
    mock_result = _ok_result("http://x.com", html)

    with patch("app.scrapers.generic.fetch_page", return_value=mock_result):
        scraper = GenericScraper(css_selector=".price_color")
        result = await scraper.fetch("http://x.com")

    assert result.extraction_status == ExtractionStatus.OK
    assert result.price is not None
    assert result.price == Decimal("9.99")


@pytest.mark.asyncio
async def test_generic_scraper_no_selector() -> None:
    scraper = GenericScraper()
    with pytest.raises(ScraperError, match="css_selector is required"):
        await scraper.fetch("http://x.com")


@pytest.mark.asyncio
async def test_generic_scraper_no_match() -> None:
    html = "<html><span>no price here</span></html>"
    mock_result = _ok_result("http://x.com", html)

    with patch("app.scrapers.generic.fetch_page", return_value=mock_result):
        scraper = GenericScraper(css_selector=".price_color")
        result = await scraper.fetch("http://x.com")

    assert result.extraction_status == ExtractionStatus.EXTRACTION_FAILED
    assert result.price is None


@pytest.mark.asyncio
async def test_generic_currency_mapping_gbp() -> None:
    html = '<html><span class="price">£19.99</span><span class="currency">£</span></html>'
    mock_result = _ok_result("http://x.com", html)

    with patch("app.scrapers.generic.fetch_page", return_value=mock_result):
        scraper = GenericScraper(css_selector=".price", css_selector_currency=".currency")
        result = await scraper.fetch("http://x.com")

    assert result.extraction_status == ExtractionStatus.OK
    assert result.currency == "GBP"


@pytest.mark.asyncio
async def test_generic_currency_mapping_usd() -> None:
    html = '<html><span class="price">$9.99</span><span class="currency">$</span></html>'
    mock_result = _ok_result("http://x.com", html)

    with patch("app.scrapers.generic.fetch_page", return_value=mock_result):
        scraper = GenericScraper(css_selector=".price", css_selector_currency=".currency")
        result = await scraper.fetch("http://x.com")

    assert result.currency == "USD"


@pytest.mark.asyncio
async def test_generic_currency_mapping_eur() -> None:
    html = '<html><span class="price">€9.99</span><span class="currency">€</span></html>'
    mock_result = _ok_result("http://x.com", html)

    with patch("app.scrapers.generic.fetch_page", return_value=mock_result):
        scraper = GenericScraper(css_selector=".price", css_selector_currency=".currency")
        result = await scraper.fetch("http://x.com")

    assert result.currency == "EUR"


@pytest.mark.asyncio
async def test_generic_currency_unknown_symbol() -> None:
    html = '<html><span class="price">¥9.99</span><span class="currency">¥</span></html>'
    mock_result = _ok_result("http://x.com", html)

    with patch("app.scrapers.generic.fetch_page", return_value=mock_result):
        scraper = GenericScraper(css_selector=".price", css_selector_currency=".currency")
        result = await scraper.fetch("http://x.com")

    assert result.currency == "¥"


@pytest.mark.asyncio
async def test_generic_http_error_propagated() -> None:
    mock_result = _error_result("http://x.com")

    with patch("app.scrapers.generic.fetch_page", return_value=mock_result):
        scraper = GenericScraper(css_selector=".price")
        result = await scraper.fetch("http://x.com")

    assert result.extraction_status == ExtractionStatus.HTTP_ERROR
    assert result.price is None
    assert result.html == ""


@pytest.mark.asyncio
async def test_generic_scraper_default_currency_usd() -> None:
    """When no css_selector_currency is set, currency defaults to USD."""
    html = '<html><span class="price">9.99</span></html>'
    mock_result = _ok_result("http://x.com", html)

    with patch("app.scrapers.generic.fetch_page", return_value=mock_result):
        scraper = GenericScraper(css_selector=".price")
        result = await scraper.fetch("http://x.com")

    assert result.extraction_status == ExtractionStatus.OK
    assert result.currency == "USD"


# ---------------------------------------------------------------------------
# AmazonScraper
# ---------------------------------------------------------------------------


def _make_playwright_mock(
    evaluate_result: object = None,
    html_content: str = "<html>Amazon page</html>",
    goto_side_effect: Exception | None = None,
    evaluate_side_effect: list[object] | None = None,
) -> tuple[object, object]:
    """Build a full Playwright mock chain and return (mock_playwright_cm, mock_browser).

    ``page.evaluate`` is called once for the ld+json script and, when that yields
    nothing, a second time for the DOM-price fallback. Pass ``evaluate_side_effect``
    to return distinct values for those successive calls; otherwise every call
    returns ``evaluate_result``.
    """
    mock_page = AsyncMock()
    if goto_side_effect is not None:
        mock_page.goto = AsyncMock(side_effect=goto_side_effect)
    else:
        mock_page.goto = AsyncMock()
    mock_page.content = AsyncMock(return_value=html_content)
    if evaluate_side_effect is not None:
        mock_page.evaluate = AsyncMock(side_effect=evaluate_side_effect)
    else:
        mock_page.evaluate = AsyncMock(return_value=evaluate_result)

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_p = AsyncMock()
    mock_p.chromium = mock_chromium

    mock_playwright_cm = AsyncMock()
    mock_playwright_cm.__aenter__ = AsyncMock(return_value=mock_p)
    mock_playwright_cm.__aexit__ = AsyncMock(return_value=False)

    return mock_playwright_cm, mock_browser


@pytest.mark.asyncio
async def test_amazon_scraper_success() -> None:
    from app.scrapers.amazon import AmazonScraper

    evaluate_result = {"price": "299.99", "currency": "USD"}
    mock_pw_cm, _ = _make_playwright_mock(evaluate_result)

    with patch("playwright.async_api.async_playwright", return_value=mock_pw_cm):
        scraper = AmazonScraper()
        result = await scraper.fetch("https://amazon.com/dp/B001")

    assert result.extraction_status == ExtractionStatus.OK
    assert result.price == Decimal("299.99")
    assert result.currency == "USD"


@pytest.mark.asyncio
async def test_amazon_scraper_dom_fallback_when_no_ldjson() -> None:
    """No ld+json offer block → price is read from the rendered DOM instead.

    Regression guard for amazon.co.uk pages that load fine (HTTP 200) but ship no
    ``application/ld+json``: the ld+json evaluate returns None and the DOM-price
    evaluate returns the buy-box price, which must be recorded as a success.
    """
    from app.scrapers.amazon import AmazonScraper

    mock_pw_cm, _ = _make_playwright_mock(
        evaluate_side_effect=[None, {"price": "107.5", "currency": "GBP"}],
    )

    with patch("playwright.async_api.async_playwright", return_value=mock_pw_cm):
        scraper = AmazonScraper()
        result = await scraper.fetch("https://amazon.co.uk/dp/B001")

    assert result.extraction_status == ExtractionStatus.OK
    assert result.price == Decimal("107.5")
    assert result.currency == "GBP"


@pytest.mark.asyncio
async def test_amazon_scraper_no_price_anywhere() -> None:
    """Neither ld+json nor the DOM fallback yields a price → extraction failed."""
    from app.scrapers.amazon import AmazonScraper

    mock_pw_cm, _ = _make_playwright_mock(
        evaluate_side_effect=[None, None],
    )

    with patch("playwright.async_api.async_playwright", return_value=mock_pw_cm):
        scraper = AmazonScraper()
        result = await scraper.fetch("https://amazon.com/dp/B001")

    assert result.extraction_status == ExtractionStatus.EXTRACTION_FAILED
    assert result.price is None


@pytest.mark.asyncio
async def test_amazon_scraper_timeout() -> None:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    from app.scrapers.amazon import AmazonScraper

    mock_pw_cm, _ = _make_playwright_mock(
        evaluate_result=None,
        goto_side_effect=PlaywrightTimeoutError("timeout"),
    )

    with patch("playwright.async_api.async_playwright", return_value=mock_pw_cm):
        scraper = AmazonScraper()
        result = await scraper.fetch("https://amazon.com/dp/B001")

    assert result.extraction_status == ExtractionStatus.HTTP_ERROR
    assert result.html == ""
    assert result.html_hash == ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_get_scraper_generic() -> None:
    scraper = get_scraper("generic")
    assert isinstance(scraper, GenericScraper)


def test_get_scraper_amazon() -> None:
    from app.scrapers.amazon import AmazonScraper

    scraper = get_scraper("amazon")
    assert isinstance(scraper, AmazonScraper)


def test_get_scraper_ebay_raises() -> None:
    with pytest.raises(UnknownSourceError):
        get_scraper("ebay")


def test_get_scraper_currys_raises() -> None:
    with pytest.raises(UnknownSourceError):
        get_scraper("currys")


def test_get_scraper_unknown_raises() -> None:
    with pytest.raises(UnknownSourceError):
        get_scraper("unknown_source")


def test_get_scraper_with_kwargs() -> None:
    scraper = get_scraper("generic", css_selector=".price")
    assert isinstance(scraper, GenericScraper)
    assert scraper.css_selector == ".price"


# ── queue_for_source_type ───────────────────────────────────────────────────────


def test_queue_for_source_type_amazon_uses_playwright() -> None:
    # Amazon needs a browser → must run on the playwright worker's queue.
    from app.scrapers.registry import queue_for_source_type

    assert queue_for_source_type("amazon") == "playwright"


def test_queue_for_source_type_generic_uses_default() -> None:
    from app.scrapers.registry import queue_for_source_type

    assert queue_for_source_type("generic") == "default"


def test_queue_for_source_type_unknown_falls_back_to_default() -> None:
    from app.scrapers.registry import queue_for_source_type

    assert queue_for_source_type("something-else") == "default"
