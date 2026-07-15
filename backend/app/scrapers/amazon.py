"""Amazon-specific scraper using Playwright for JavaScript-rendered pages."""

from __future__ import annotations

import re
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

# Fallback: read the price straight out of the rendered DOM. Amazon's regional
# storefronts (notably amazon.co.uk) frequently ship product pages with NO
# ``application/ld+json`` offer block, so ``_LD_JSON_SCRIPT`` returns null even
# though the page loaded fine (HTTP 200, real title). The visible buy-box price
# lives in a ``.a-offscreen`` span; selectors are tried buy-box-first so we take
# the actual purchasable price, not a struck-through list price or a
# subscribe-&-save variant. Currency is inferred from the symbol.
_DOM_PRICE_SCRIPT = """
() => {
    const SELECTORS = [
        '#corePrice_feature_div span.a-offscreen',
        '#corePriceDisplay_desktop_feature_div span.a-price[data-a-color="base"] span.a-offscreen',
        '#corePriceDisplay_desktop_feature_div span.a-offscreen',
        '#priceblock_ourprice',
        '#priceblock_dealprice',
        '#priceblock_saleprice',
        'span.a-price[data-a-color="base"] span.a-offscreen',
        'span.a-price span.a-offscreen',
        '.a-price .a-offscreen',
    ];
    const SYMBOL = {'£': 'GBP', '$': 'USD', '\\u20ac': 'EUR', '\\u20b9': 'INR'};
    const parse = (raw) => {
        if (!raw) return null;
        const text = raw.trim();
        let currency = null;
        for (const sym of Object.keys(SYMBOL)) {
            if (text.indexOf(sym) !== -1) { currency = SYMBOL[sym]; break; }
        }
        const num = text.replace(/[^0-9.,]/g, '');
        if (!/[0-9]/.test(num)) return null;
        // Return the raw digit/separator run untouched. Which of '.'/',' is the
        // decimal point is locale-dependent (1,234.56 in en-US vs 1.234,56 in
        // de-DE) and cannot be decided reliably here, so normalisation is done
        // in Python by _normalize_price_text.
        return {price: num, currency: currency};
    };
    for (const sel of SELECTORS) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
            const r = parse(el.textContent);
            if (r) { r.selector = sel; return r; }
        }
    }
    return null;
}
"""


def _normalize_price_text(raw: str) -> Decimal | None:
    """Convert a locale-formatted price string to a Decimal, or None if unparseable.

    Amazon renders prices in the marketplace's locale, so the roles of ``.`` and
    ``,`` differ: ``1,234.56`` (en-US/en-GB) vs ``1.234,56`` (de/fr/es/it). The
    separator that appears *last* is the decimal point; earlier separators group
    thousands. When only one kind of separator is present, a trailing group of
    exactly two digits is read as a decimal fraction (``1234,56`` -> 1234.56),
    otherwise the separators group thousands (``1,234`` -> 1234, ``1.234.567`` ->
    1234567).
    """
    cleaned = re.sub(r"[^0-9.,]", "", raw or "")
    if not any(ch.isdigit() for ch in cleaned):
        return None

    has_comma = "," in cleaned
    has_dot = "." in cleaned
    if has_comma and has_dot:
        if cleaned.rfind(",") > cleaned.rfind("."):
            num = cleaned.replace(".", "").replace(",", ".")  # 1.234,56 -> 1234.56
        else:
            num = cleaned.replace(",", "")  # 1,234.56 -> 1234.56
    elif has_comma:
        head, _, tail = cleaned.rpartition(",")
        num = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else cleaned.replace(",", "")
    else:
        num = cleaned.replace(".", "") if cleaned.count(".") > 1 else cleaned

    try:
        return Decimal(num)
    except InvalidOperation:
        return None


def _parse_dom_result(
    dom_result: object,
    html: str,
    html_hash: str,
    url: str,
) -> ScrapedResult:
    """Parse a DOM-fallback result, normalising its locale-formatted price string.

    The DOM script returns the price as the raw digit/separator run from the
    rendered buy-box (e.g. ``"1.234,56"``); normalise it to a canonical decimal
    string and reuse :func:`_parse_ld_result` for the ScrapedResult assembly. A
    string that does not yield a price is passed through without a ``price`` key
    so ``_parse_ld_result`` emits its standard extraction-failed result.
    """
    price = _normalize_price_text(str(dom_result.get("price", "")))  # type: ignore[attr-defined]
    normalised: dict[str, object] = {"currency": dom_result.get("currency")}  # type: ignore[attr-defined]
    if price is not None:
        normalised["price"] = str(price)
    return _parse_ld_result(normalised, html, html_hash, url)


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
            url=url,
            html="",
            html_hash="",
            price=None,
            currency=None,
            scraped_at=datetime.now(UTC),
            extraction_status=ExtractionStatus.HTTP_ERROR,
        )

    html = await page.content()  # type: ignore[attr-defined]
    html_hash = html_hash_fn(html)  # type: ignore[operator]
    ld_result = await page.evaluate(_LD_JSON_SCRIPT)  # type: ignore[attr-defined]

    if ld_result is None:
        # No structured-data offer block — fall back to the rendered DOM price.
        dom_result = await page.evaluate(_DOM_PRICE_SCRIPT)  # type: ignore[attr-defined]
        if dom_result is None:
            logger.warning("amazon_scraper_no_price", url=url)
            return ScrapedResult(
                url=url,
                html=html,
                html_hash=html_hash,
                price=None,
                currency=None,
                scraped_at=datetime.now(UTC),
                extraction_status=ExtractionStatus.EXTRACTION_FAILED,
            )
        logger.info("amazon_scraper_dom_fallback", url=url, selector=dom_result.get("selector"))
        return _parse_dom_result(dom_result, html, html_hash, url)

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
                    url=url,
                    html="",
                    html_hash="",
                    price=None,
                    currency=None,
                    scraped_at=datetime.now(UTC),
                    extraction_status=ExtractionStatus.HTTP_ERROR,
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
