"""Amazon-specific scraper using Playwright for JavaScript-rendered pages."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import structlog

from app.models.enums import ExtractionStatus
from app.schemas.scraper import ScrapedResult
from app.scrapers.base import BaseScraper
from app.scrapers.exceptions import ScraperError

logger = structlog.get_logger()

# JavaScript snippet to extract price from ld+json structured data
_LD_JSON_SCRIPT = """
() => {
    const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
    for (const s of scripts) {
        try {
            const d = JSON.parse(s.textContent);
            const items = Array.isArray(d) ? d : [d];
            for (const item of items) {
                const offer = item.offers || (item['@type'] === 'Offer' ? item : null);
                if (offer) {
                    const o = Array.isArray(offer) ? offer[0] : offer;
                    if (o.price != null) return {price: String(o.price), currency: o.priceCurrency || null};
                }
            }
        } catch(e) {}
    }
    return null;
}
"""


def _parse_ld_result(
    ld_result: object,
    html: str,
    html_hash: str,
    url: str,
) -> ScrapedResult:
    """Parse price from ld+json evaluate result; return extraction-failed on parse error."""
    try:
        price = Decimal(str(ld_result["price"]))  # type: ignore[index]
    except (InvalidOperation, KeyError, TypeError) as exc:
        logger.warning(
            "amazon_scraper_price_parse_failed",
            url=url,
            ld_result=ld_result,
            error=str(exc),
        )
        return ScrapedResult(
            url=url,
            html=html,
            html_hash=html_hash,
            price=None,
            currency=None,
            scraped_at=datetime.now(UTC),
            extraction_status=ExtractionStatus.EXTRACTION_FAILED,
        )
    currency: str | None = ld_result.get("currency")  # type: ignore[attr-defined]
    return ScrapedResult(
        url=url,
        html=html,
        html_hash=html_hash,
        price=price,
        currency=currency,
        scraped_at=datetime.now(UTC),
        extraction_status=ExtractionStatus.OK,
    )


async def _navigate_and_extract(page: object, url: str, html_hash_fn: object) -> ScrapedResult:
    """Navigate to *url*, extract ld+json price, return a ScrapedResult."""
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    try:
        await page.goto(url, timeout=30_000)  # type: ignore[attr-defined]
    except PlaywrightTimeoutError:
        logger.warning("amazon_scraper_timeout", url=url)
        return ScrapedResult(
            url=url, html="", html_hash="", price=None, currency=None,
            scraped_at=datetime.now(UTC), extraction_status=ExtractionStatus.HTTP_ERROR,
        )

    html = await page.content()  # type: ignore[attr-defined]
    html_hash = html_hash_fn(html)  # type: ignore[operator]
    ld_result = await page.evaluate(_LD_JSON_SCRIPT)  # type: ignore[attr-defined]

    if ld_result is None:
        logger.warning("amazon_scraper_no_ldjson", url=url)
        return ScrapedResult(
            url=url, html=html, html_hash=html_hash, price=None, currency=None,
            scraped_at=datetime.now(UTC), extraction_status=ExtractionStatus.EXTRACTION_FAILED,
        )

    return _parse_ld_result(ld_result, html, html_hash, url)


class AmazonScraper(BaseScraper):
    """Playwright-based scraper for Amazon product pages."""

    async def fetch(self, url: str) -> ScrapedResult:
        """Fetch *url* using a headless Chromium browser and extract price from ld+json."""
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright

        context = None
        browser = None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()
                return await _navigate_and_extract(page, url, self._compute_hash)

        except Exception as exc:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError  # noqa: F811

            if isinstance(exc, PlaywrightTimeoutError):
                return ScrapedResult(
                    url=url, html="", html_hash="", price=None, currency=None,
                    scraped_at=datetime.now(UTC), extraction_status=ExtractionStatus.HTTP_ERROR,
                )
            raise ScraperError(f"Playwright error: {exc}") from exc
        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass
