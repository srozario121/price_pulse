"""Unit tests for the Item 18 UK source scrapers (isolated — no network).

Covers the eBay httpx+ld+json path (fetch layer mocked) and the Playwright-based
Currys / John Lewis / Facebook Marketplace scrapers (Playwright chain mocked),
including the shared ``PlaywrightScraper`` base behaviour (ld+json first, DOM
fallback, block classification, timeout) and Facebook's login-wall detection.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.enums import ExtractionStatus
from app.schemas.scraper import ScrapedResult


# ── eBay (httpx + ld+json) ────────────────────────────────────────────────────
def _fetch_result(html: str, status: ExtractionStatus = ExtractionStatus.OK) -> ScrapedResult:
    return ScrapedResult(
        url="https://www.ebay.co.uk/itm/123",
        html=html,
        html_hash="hash",
        price=None,
        currency=None,
        scraped_at=datetime.now(UTC),
        extraction_status=status,
    )


_EBAY_LD_HTML = """
<html><head>
<script type="application/ld+json">
{"@type": "Product", "name": "Widget",
 "offers": {"@type": "Offer", "price": "249.99", "priceCurrency": "GBP"}}
</script></head><body>ok</body></html>
"""


@pytest.mark.asyncio
async def test_ebay_extracts_price_from_ld_json() -> None:
    from app.scrapers.ebay import EbayScraper

    with patch(
        "app.scrapers.ebay.fetch_page", AsyncMock(return_value=_fetch_result(_EBAY_LD_HTML))
    ):
        result = await EbayScraper().fetch("https://www.ebay.co.uk/itm/123")

    assert result.extraction_status == ExtractionStatus.OK
    assert result.price == Decimal("249.99")
    assert result.currency == "GBP"


@pytest.mark.asyncio
async def test_ebay_falls_back_to_dom_meta_price() -> None:
    from app.scrapers.ebay import EbayScraper

    html = '<html><body><meta itemprop="price" content="79.95">'
    html += '<meta itemprop="priceCurrency" content="GBP"></body></html>'
    with patch("app.scrapers.ebay.fetch_page", AsyncMock(return_value=_fetch_result(html))):
        result = await EbayScraper().fetch("https://www.ebay.co.uk/itm/x")

    assert result.extraction_status == ExtractionStatus.OK
    assert result.price == Decimal("79.95")
    assert result.currency == "GBP"


@pytest.mark.asyncio
async def test_ebay_no_price_yields_extraction_failed() -> None:
    from app.scrapers.ebay import EbayScraper

    html = "<html><body>no price here</body></html>"
    with patch("app.scrapers.ebay.fetch_page", AsyncMock(return_value=_fetch_result(html))):
        result = await EbayScraper().fetch("https://www.ebay.co.uk/itm/x")

    assert result.extraction_status == ExtractionStatus.EXTRACTION_FAILED
    assert result.price is None


@pytest.mark.asyncio
async def test_ebay_propagates_blocked_without_extraction() -> None:
    # A blocked fetch must never be re-classified as an extraction failure.
    from app.scrapers.ebay import EbayScraper

    blocked = _fetch_result("<html>robot check</html>", status=ExtractionStatus.BLOCKED)
    with patch("app.scrapers.ebay.fetch_page", AsyncMock(return_value=blocked)):
        result = await EbayScraper().fetch("https://www.ebay.co.uk/itm/x")

    assert result.extraction_status == ExtractionStatus.BLOCKED


@pytest.mark.asyncio
async def test_ebay_default_currency_when_ld_json_omits_it() -> None:
    from app.scrapers.ebay import EbayScraper

    html = '<script type="application/ld+json">{"offers": {"price": "10.00"}}</script>'
    with patch("app.scrapers.ebay.fetch_page", AsyncMock(return_value=_fetch_result(html))):
        result = await EbayScraper().fetch("https://www.ebay.co.uk/itm/x")

    assert result.price == Decimal("10.00")
    assert result.currency == "GBP"  # default


# ── Playwright scrapers (Currys / John Lewis / Facebook) ──────────────────────
def _make_playwright(
    *,
    evaluate_result: object = None,
    evaluate_side_effect: list[object] | None = None,
    html: str = "<html>ok</html>",
    status: int = 200,
    goto_exc: Exception | None = None,
) -> object:
    """Build a mocked ``async_playwright()`` context manager chain."""
    mock_page = AsyncMock()
    response = MagicMock()
    response.status = status
    mock_page.goto = (
        AsyncMock(side_effect=goto_exc)
        if goto_exc is not None
        else AsyncMock(return_value=response)
    )
    mock_page.content = AsyncMock(return_value=html)
    if evaluate_side_effect is not None:
        mock_page.evaluate = AsyncMock(side_effect=evaluate_side_effect)
    else:
        mock_page.evaluate = AsyncMock(return_value=evaluate_result)

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.add_init_script = AsyncMock()
    mock_context.close = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_p = AsyncMock()
    mock_p.chromium = mock_chromium

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_p)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_currys_extracts_ld_json_price() -> None:
    from app.scrapers.currys import CurrysScraper

    cm = _make_playwright(evaluate_result={"price": "899.00", "currency": "GBP"})
    with patch("playwright.async_api.async_playwright", return_value=cm):
        result = await CurrysScraper().fetch("https://www.currys.co.uk/products/x")

    assert result.extraction_status == ExtractionStatus.OK
    assert result.price == Decimal("899.00")
    assert result.currency == "GBP"


@pytest.mark.asyncio
async def test_john_lewis_dom_fallback_when_no_ld_json() -> None:
    from app.scrapers.john_lewis import JohnLewisScraper

    # ld+json evaluate returns None → DOM-price evaluate returns the buy-box price.
    cm = _make_playwright(
        evaluate_side_effect=[None, {"price": "1.299,00", "currency": "GBP", "selector": ".x"}],
    )
    with patch("playwright.async_api.async_playwright", return_value=cm):
        result = await JohnLewisScraper().fetch("https://www.johnlewis.com/p/x")

    assert result.extraction_status == ExtractionStatus.OK
    assert result.price == Decimal("1299.00")  # locale separator resolved
    assert result.currency == "GBP"


@pytest.mark.asyncio
async def test_currys_no_price_anywhere_yields_extraction_failed() -> None:
    from app.scrapers.currys import CurrysScraper

    cm = _make_playwright(evaluate_side_effect=[None, None])
    with patch("playwright.async_api.async_playwright", return_value=cm):
        result = await CurrysScraper().fetch("https://www.currys.co.uk/products/x")

    assert result.extraction_status == ExtractionStatus.EXTRACTION_FAILED
    assert result.price is None


@pytest.mark.asyncio
async def test_playwright_scraper_timeout_is_http_error() -> None:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    from app.scrapers.currys import CurrysScraper

    cm = _make_playwright(goto_exc=PlaywrightTimeoutError("timeout"))
    with patch("playwright.async_api.async_playwright", return_value=cm):
        result = await CurrysScraper().fetch("https://www.currys.co.uk/products/x")

    assert result.extraction_status == ExtractionStatus.HTTP_ERROR


# ── Facebook Marketplace login-wall / bot-check classification ─────────────────
@pytest.mark.asyncio
async def test_facebook_login_wall_classifies_as_blocked_not_failed() -> None:
    from app.scrapers.facebook_marketplace import FacebookMarketplaceScraper

    login_html = (
        "<html><body>You must log in to continue.<form id='login_form'></form></body></html>"
    )
    cm = _make_playwright(html=login_html)
    with patch("playwright.async_api.async_playwright", return_value=cm):
        result = await FacebookMarketplaceScraper().fetch(
            "https://www.facebook.com/marketplace/item/1"
        )

    assert result.extraction_status == ExtractionStatus.BLOCKED
    assert result.price is None


@pytest.mark.asyncio
async def test_facebook_checkpoint_classifies_as_captcha() -> None:
    from app.scrapers.facebook_marketplace import FacebookMarketplaceScraper

    challenge_html = "<html><body>Please complete this security check</body></html>"
    cm = _make_playwright(html=challenge_html)
    with patch("playwright.async_api.async_playwright", return_value=cm):
        result = await FacebookMarketplaceScraper().fetch(
            "https://www.facebook.com/marketplace/item/2"
        )

    assert result.extraction_status == ExtractionStatus.CAPTCHA


def test_facebook_detect_block_returns_none_for_normal_page() -> None:
    from app.scrapers.facebook_marketplace import FacebookMarketplaceScraper

    assert FacebookMarketplaceScraper()._detect_block(200, "<html>a normal listing</html>") is None
