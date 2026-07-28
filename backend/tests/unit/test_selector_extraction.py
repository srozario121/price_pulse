"""Unit tests for learned-selector extraction and the selector_miss taxonomy (Item 16).

Arrange-Act-Assert throughout; isolated — ``fetch_page`` and Playwright are mocked.

The central guarantee under test: ``SELECTOR_MISS`` is raised **only** for a page
that genuinely loaded and was not blocked. A CAPTCHA or 429 page has no price
either, and feeding one to selector generation would poison the stored selector
with markup from the block page.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.enums import ExtractionStatus
from app.schemas.scraper import LearnedSelector, ScrapedResult
from app.scrapers.generic import GenericScraper

_DRIFTED_HTML = (
    "<html><body><h1>Widget Pro</h1>"
    '<div id="new-buybox"><span class="pdp-price">£129.50</span></div>'
    "</body></html>"
)

_CAPTCHA_HTML = (
    "<html><head><title>Robot Check</title></head>"
    "<body>Enter the characters you see below</body></html>"
)


def _ok_page(url: str, html: str) -> ScrapedResult:
    return ScrapedResult(
        url=url,
        html=html,
        html_hash="hash",
        price=None,
        currency=None,
        scraped_at=datetime.now(UTC),
        extraction_status=ExtractionStatus.OK,
    )


# ── GenericScraper ─────────────────────────────────────────────────────────────


class TestGenericLearnedSelector:
    async def test_stale_configured_selector_falls_back_to_the_learned_one(self):
        # Arrange — the product's own selector no longer matches (markup drifted),
        # but the host has a healed selector
        page = _ok_page("https://shop.example.com/p/1", _DRIFTED_HTML)
        scraper = GenericScraper(css_selector=".old-price")
        scraper.learned_selector = LearnedSelector(price_selector="#new-buybox .pdp-price")

        # Act
        with patch("app.scrapers.generic.fetch_page", return_value=page):
            result = await scraper.fetch("https://shop.example.com/p/1")

        # Assert — the source self-healed without a code change
        assert result.extraction_status == ExtractionStatus.OK
        assert result.price == Decimal("129.50")

    async def test_configured_selector_wins_over_the_learned_one(self):
        # Arrange — both match; the deliberate, product-level choice takes priority
        html = '<div class="chosen">£10.00</div><div class="learned">£99.00</div>'
        page = _ok_page("https://shop.example.com/p/1", html)
        scraper = GenericScraper(css_selector=".chosen")
        scraper.learned_selector = LearnedSelector(price_selector=".learned")

        # Act
        with patch("app.scrapers.generic.fetch_page", return_value=page):
            result = await scraper.fetch("https://shop.example.com/p/1")

        # Assert
        assert result.price == Decimal("10.00")

    async def test_neither_selector_matching_is_a_selector_miss(self):
        # Arrange
        page = _ok_page("https://shop.example.com/p/1", "<html><body>no price</body></html>")
        scraper = GenericScraper(css_selector=".old-price")
        scraper.learned_selector = LearnedSelector(price_selector=".also-gone")

        # Act
        with patch("app.scrapers.generic.fetch_page", return_value=page):
            result = await scraper.fetch("https://shop.example.com/p/1")

        # Assert — drift, which is what triggers regeneration
        assert result.extraction_status == ExtractionStatus.SELECTOR_MISS

    async def test_matched_but_unparseable_price_stays_extraction_failed(self):
        # Arrange — the selector still matches, so the markup did NOT move; the
        # text simply will not parse. Regenerating here would be the wrong remedy.
        html = '<div class="price">call for pricing</div>'
        page = _ok_page("https://shop.example.com/p/1", html)
        scraper = GenericScraper(css_selector=".price")

        # Act
        with patch("app.scrapers.generic.fetch_page", return_value=page):
            result = await scraper.fetch("https://shop.example.com/p/1")

        # Assert
        assert result.extraction_status == ExtractionStatus.EXTRACTION_FAILED

    async def test_learned_currency_selector_is_used_with_the_learned_price(self):
        # Arrange
        html = '<div class="p">129.50</div><div class="c">£</div>'
        page = _ok_page("https://shop.example.com/p/1", html)
        scraper = GenericScraper(css_selector=".gone", css_selector_currency=".also-gone")
        scraper.learned_selector = LearnedSelector(price_selector=".p", currency_selector=".c")

        # Act
        with patch("app.scrapers.generic.fetch_page", return_value=page):
            result = await scraper.fetch("https://shop.example.com/p/1")

        # Assert — the learned pair is used together, not mixed with the stale one
        assert result.price == Decimal("129.50")
        assert result.currency == "GBP"

    async def test_a_non_ok_fetch_is_returned_untouched(self):
        # Arrange — a blocked page must never become a selector_miss
        blocked = ScrapedResult(
            url="https://shop.example.com/p/1",
            html=_CAPTCHA_HTML,
            html_hash="hash",
            price=None,
            currency=None,
            scraped_at=datetime.now(UTC),
            extraction_status=ExtractionStatus.BLOCKED,
        )
        scraper = GenericScraper(css_selector=".price")

        # Act
        with patch("app.scrapers.generic.fetch_page", return_value=blocked):
            result = await scraper.fetch("https://shop.example.com/p/1")

        # Assert
        assert result.extraction_status == ExtractionStatus.BLOCKED

    async def test_explicit_text_pseudo_element_is_passed_through(self):
        # Arrange — a caller that already specified ::text must keep that meaning
        html = '<div class="p">£11.00<span class="vat"> inc VAT</span></div>'
        page = _ok_page("https://shop.example.com/p/1", html)
        scraper = GenericScraper(css_selector=".p::text")

        # Act
        with patch("app.scrapers.generic.fetch_page", return_value=page):
            result = await scraper.fetch("https://shop.example.com/p/1")

        # Assert — only the element's own text node, not the nested span
        assert result.price == Decimal("11.00")

    async def test_hyphenated_class_name_does_not_corrupt_the_price(self):
        # Arrange — extracting outer HTML would leave the '-' of "pdp-price" in
        # the cleaned digits and yield a negative price
        page = _ok_page("https://shop.example.com/p/1", _DRIFTED_HTML)
        scraper = GenericScraper(css_selector=".pdp-price")

        # Act
        with patch("app.scrapers.generic.fetch_page", return_value=page):
            result = await scraper.fetch("https://shop.example.com/p/1")

        # Assert
        assert result.price == Decimal("129.50")

    async def test_learned_selector_alone_satisfies_the_required_selector_check(self):
        # Arrange — no product-level selector at all, only a healed host selector
        page = _ok_page("https://shop.example.com/p/1", _DRIFTED_HTML)
        scraper = GenericScraper(css_selector=None)
        scraper.learned_selector = LearnedSelector(price_selector="#new-buybox .pdp-price")

        # Act
        with patch("app.scrapers.generic.fetch_page", return_value=page):
            result = await scraper.fetch("https://shop.example.com/p/1")

        # Assert
        assert result.price == Decimal("129.50")


# ── AmazonScraper ──────────────────────────────────────────────────────────────


def _playwright_mock(*, html: str, status: int, evaluate_side_effect: list):
    """Build a Playwright async_playwright() stub returning canned page content."""
    page = MagicMock()
    response = MagicMock()
    response.status = status
    page.goto = AsyncMock(return_value=response)
    page.content = AsyncMock(return_value=html)
    page.evaluate = AsyncMock(side_effect=evaluate_side_effect)

    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.add_init_script = AsyncMock()
    context.close = AsyncMock()

    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()

    chromium = MagicMock()
    chromium.launch = AsyncMock(return_value=browser)

    playwright = MagicMock()
    playwright.chromium = chromium

    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)
    return manager, page


class TestAmazonLearnedSelector:
    async def test_learned_selector_is_tried_before_the_legacy_list(self):
        # Arrange — ld+json absent, then the learned selector hits
        from app.scrapers.amazon import AmazonScraper

        manager, page = _playwright_mock(
            html=_DRIFTED_HTML,
            status=200,
            evaluate_side_effect=[None, {"price": "129.50", "currency": "GBP"}],
        )
        scraper = AmazonScraper()
        scraper.learned_selector = LearnedSelector(price_selector="#new-buybox .pdp-price")

        # Act
        with patch("playwright.async_api.async_playwright", return_value=manager):
            result = await scraper.fetch("https://amazon.co.uk/dp/B01")

        # Assert — healed, and the legacy list was never reached
        assert result.extraction_status == ExtractionStatus.OK
        assert result.price == Decimal("129.50")
        assert page.evaluate.await_count == 2

    async def test_legacy_list_still_runs_when_the_learned_selector_misses(self):
        # Arrange — ld+json None, learned None, legacy list hits
        from app.scrapers.amazon import AmazonScraper

        manager, page = _playwright_mock(
            html=_DRIFTED_HTML,
            status=200,
            evaluate_side_effect=[None, None, {"price": "99.00", "currency": "GBP"}],
        )
        scraper = AmazonScraper()
        scraper.learned_selector = LearnedSelector(price_selector=".stale")

        # Act
        with patch("playwright.async_api.async_playwright", return_value=manager):
            result = await scraper.fetch("https://amazon.co.uk/dp/B01")

        # Assert — the existing working path remains the safety net
        assert result.extraction_status == ExtractionStatus.OK
        assert result.price == Decimal("99.00")
        assert page.evaluate.await_count == 3

    async def test_blocked_page_is_never_a_selector_miss(self):
        # Arrange — a 200-status robot check: no price, but NOT drift. Generating
        # from this page would store a selector for the CAPTCHA interstitial.
        from app.scrapers.amazon import AmazonScraper

        manager, page = _playwright_mock(
            html=_CAPTCHA_HTML, status=200, evaluate_side_effect=[None, None]
        )

        # Act
        with patch("playwright.async_api.async_playwright", return_value=manager):
            result = await AmazonScraper().fetch("https://amazon.co.uk/dp/B01")

        # Assert — classified before extraction, so no evaluate ever ran
        assert result.extraction_status == ExtractionStatus.CAPTCHA
        assert page.evaluate.await_count == 0

    async def test_ld_json_still_wins_over_the_learned_selector(self):
        # Arrange — structured data is authoritative when present
        from app.scrapers.amazon import AmazonScraper

        manager, page = _playwright_mock(
            html=_DRIFTED_HTML,
            status=200,
            evaluate_side_effect=[{"price": "42.00", "currency": "GBP"}],
        )
        scraper = AmazonScraper()
        scraper.learned_selector = LearnedSelector(price_selector="#new-buybox .pdp-price")

        # Act
        with patch("playwright.async_api.async_playwright", return_value=manager):
            result = await scraper.fetch("https://amazon.co.uk/dp/B01")

        # Assert
        assert result.price == Decimal("42.00")
        assert page.evaluate.await_count == 1


# ── Registry wiring ────────────────────────────────────────────────────────────


class TestRegistryLearnedSelector:
    async def test_learned_selector_is_attached_to_a_selector_strategy(self, db_session):
        # Arrange
        from app.scrapers.registry import get_scraper

        learned = LearnedSelector(price_selector=".p")

        # Act
        scraper = await get_scraper(
            "generic", db_session, css_selector=".x", learned_selector=learned
        )

        # Assert
        assert scraper.learned_selector is learned
        assert scraper.css_selector == ".x"

    async def test_learned_selector_is_attached_to_a_non_selector_strategy(self, db_session):
        # Arrange — AmazonScraper takes no constructor kwargs
        from app.scrapers.registry import get_scraper

        learned = LearnedSelector(price_selector=".p")

        # Act
        scraper = await get_scraper("amazon", db_session, learned_selector=learned)

        # Assert
        assert scraper.learned_selector is learned

    async def test_defaults_to_none_when_the_host_has_no_profile(self, db_session):
        # Arrange
        from app.scrapers.registry import get_scraper

        # Act
        scraper = await get_scraper("generic", db_session, css_selector=".x")

        # Assert
        assert scraper.learned_selector is None


@pytest.mark.parametrize("strategy", ["ebay", "currys", "john_lewis", "facebook_marketplace"])
async def test_other_strategies_accept_but_ignore_a_learned_selector(db_session, strategy):
    # Arrange — Item 16's scope is amazon + generic; the rest must still construct
    from app.scrapers.registry import get_scraper

    # Act
    scraper = await get_scraper(
        strategy, db_session, learned_selector=LearnedSelector(price_selector=".p")
    )

    # Assert
    assert scraper.learned_selector is not None
