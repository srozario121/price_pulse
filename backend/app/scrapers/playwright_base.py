"""Shared Playwright scraper base for JavaScript-rendered retail pages.

Currys, John Lewis and Facebook Marketplace (Item 18) are all React/SPA sites
whose price is only present after client-side render, so they share the same
machinery: a stealthed headless Chromium context, per-request proxy rotation
with bounded rotate-on-block retry (Item 15), block/CAPTCHA classification
*before* extraction, then ``ld+json``-first price extraction with a configurable
CSS-selector DOM fallback.

Subclasses supply only what differs — the buy-box-first ``PRICE_SELECTORS`` and a
``DEFAULT_CURRENCY`` — and may override ``_detect_block`` to add site-specific
login-wall/challenge markers (Facebook Marketplace does).

``amazon.py`` predates this base and keeps its own richer, bespoke DOM script; it
is intentionally not refactored onto this base.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import structlog

from app.core.config import settings
from app.models.enums import ExtractionStatus
from app.schemas.scraper import ScrapedResult
from app.scrapers.anti_blocking import (
    ACCEPT_LANGUAGE,
    ProxyRotator,
    choose_user_agent,
    classify_block,
    normalise_proxy,
)
from app.scrapers.base import BaseScraper
from app.scrapers.exceptions import ScraperError

logger = structlog.get_logger()

# Currency symbols → ISO 4217 (shared with the DOM extraction script below).
_CURRENCY_SYMBOL_MAP: dict[str, str] = {"£": "GBP", "$": "USD", "€": "EUR", "₹": "INR"}

# Custom stealth top-ups layered on top of playwright-stealth (Item 15): patch the
# fingerprint surfaces bot detectors probe most. Registered via add_init_script so
# they run before page scripts on every navigation.
_STEALTH_INIT_SCRIPT = """
(() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
  Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en'] });
  if (!window.chrome) { window.chrome = { runtime: {} }; }
  try {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function (p) {
      if (p === 37445) return 'Intel Inc.';
      if (p === 37446) return 'Intel Iris OpenGL Engine';
      return getParameter.call(this, p);
    };
  } catch (e) {}
})();
"""

# Extract price from ld+json structured data (Product → offers → price).
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

# DOM fallback: try each caller-supplied CSS selector (buy-box first) and return
# the raw digit/separator run untouched — decimal-separator resolution is done in
# Python (_normalize_price_text) because it is locale-dependent.
_DOM_PRICE_SCRIPT = """
(selectors) => {
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
        return {price: num, currency: currency};
    };
    for (const sel of selectors) {
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

    The separator that appears *last* is the decimal point; earlier separators
    group thousands (``1,234.56`` → 1234.56 vs ``1.234,56`` → 1234.56). With a
    single separator kind, a trailing two-digit group is a decimal fraction.
    """
    cleaned = re.sub(r"[^0-9.,]", "", raw or "")
    if not any(ch.isdigit() for ch in cleaned):
        return None

    has_comma = "," in cleaned
    has_dot = "." in cleaned
    if has_comma and has_dot:
        if cleaned.rfind(",") > cleaned.rfind("."):
            num = cleaned.replace(".", "").replace(",", ".")
        else:
            num = cleaned.replace(",", "")
    elif has_comma:
        head, _, tail = cleaned.rpartition(",")
        num = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else cleaned.replace(",", "")
    else:
        num = cleaned.replace(".", "") if cleaned.count(".") > 1 else cleaned

    try:
        return Decimal(num)
    except InvalidOperation:
        return None


def _result(
    url: str,
    html: str,
    html_hash: str,
    *,
    price: Decimal | None,
    currency: str | None,
    status: ExtractionStatus,
) -> ScrapedResult:
    return ScrapedResult(
        url=url,
        html=html,
        html_hash=html_hash,
        price=price,
        currency=currency,
        scraped_at=datetime.now(UTC),
        extraction_status=status,
    )


class PlaywrightScraper(BaseScraper):
    """Base for browser-rendered scrapers: ld+json first, CSS-selector DOM fallback."""

    #: Buy-box-first CSS selectors tried in order for the DOM fallback.
    PRICE_SELECTORS: tuple[str, ...] = ()
    #: Currency used when neither ld+json nor a price symbol resolves one.
    DEFAULT_CURRENCY: str | None = None
    NAV_TIMEOUT_MS: int = 30_000

    def _detect_block(self, status_code: int, html: str) -> ExtractionStatus | None:
        """Classify a block/CAPTCHA before extraction. Override to add site markers."""
        return classify_block(status_code, html)

    # ── extraction ────────────────────────────────────────────────────────────
    def _from_ld(self, ld: object, url: str, html: str, html_hash: str) -> ScrapedResult | None:
        """Build an OK result from an ld+json evaluate payload, or None if no price."""
        try:
            price = Decimal(str(ld["price"]))  # type: ignore[index]
        except (InvalidOperation, KeyError, TypeError):
            return None
        currency = ld.get("currency") or self.DEFAULT_CURRENCY  # type: ignore[attr-defined]
        return _result(
            url, html, html_hash, price=price, currency=currency, status=ExtractionStatus.OK
        )

    def _from_dom(self, dom: object, url: str, html: str, html_hash: str) -> ScrapedResult | None:
        """Build an OK result from the DOM-fallback payload, or None if no price."""
        price = _normalize_price_text(str(dom.get("price", "")))  # type: ignore[attr-defined]
        if price is None:
            return None
        currency = dom.get("currency") or self.DEFAULT_CURRENCY  # type: ignore[attr-defined]
        return _result(
            url, html, html_hash, price=price, currency=currency, status=ExtractionStatus.OK
        )

    async def _extract(self, page: object, url: str, html: str, html_hash: str) -> ScrapedResult:
        """ld+json first, then the configured CSS-selector DOM fallback."""
        ld = await page.evaluate(_LD_JSON_SCRIPT)  # type: ignore[attr-defined]
        if ld is not None:
            result = self._from_ld(ld, url, html, html_hash)
            if result is not None:
                return result

        if self.PRICE_SELECTORS:
            dom = await page.evaluate(  # type: ignore[attr-defined]
                _DOM_PRICE_SCRIPT, list(self.PRICE_SELECTORS)
            )
            if dom is not None:
                result = self._from_dom(dom, url, html, html_hash)
                if result is not None:
                    logger.info(
                        "playwright_scraper_dom_fallback",
                        scraper=type(self).__name__,
                        url=url,
                        selector=dom.get("selector"),  # type: ignore[attr-defined]
                    )
                    return result

        logger.warning("playwright_scraper_no_price", scraper=type(self).__name__, url=url)
        return _result(
            url,
            html,
            html_hash,
            price=None,
            currency=None,
            status=ExtractionStatus.EXTRACTION_FAILED,
        )

    async def _navigate_and_extract(self, page: object, url: str) -> ScrapedResult:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        try:
            response = await page.goto(url, timeout=self.NAV_TIMEOUT_MS)  # type: ignore[attr-defined]
        except PlaywrightTimeoutError:
            logger.warning("playwright_scraper_timeout", scraper=type(self).__name__, url=url)
            return _result(
                url, "", "", price=None, currency=None, status=ExtractionStatus.HTTP_ERROR
            )

        html = await page.content()  # type: ignore[attr-defined]
        html_hash = self._compute_hash(html)

        status_code = response.status if response is not None else 200
        block = self._detect_block(status_code, html)
        if block is not None:
            logger.warning(
                "playwright_scraper_blocked",
                scraper=type(self).__name__,
                url=url,
                status=status_code,
                classification=block.value,
            )
            return _result(url, html, html_hash, price=None, currency=None, status=block)

        return await self._extract(page, url, html, html_hash)

    # ── context / fetch ───────────────────────────────────────────────────────
    async def _apply_stealth(self, context: object) -> None:
        """Apply playwright-stealth (best-effort), then the custom init-script top-ups."""
        try:
            from playwright_stealth import Stealth

            await Stealth().apply_stealth_async(context)
        except Exception as exc:  # noqa: BLE001 — best-effort; custom top-ups still apply
            logger.debug("playwright_stealth_unavailable", error=str(exc))
        await context.add_init_script(_STEALTH_INIT_SCRIPT)  # type: ignore[attr-defined]

    async def _build_context(self, browser: object, proxy_url: str | None) -> object:
        kwargs: dict[str, object] = {
            "user_agent": choose_user_agent(),
            "extra_http_headers": {"Accept-Language": ACCEPT_LANGUAGE},
        }
        if proxy_url is not None:
            kwargs["proxy"] = normalise_proxy(proxy_url).playwright
        return await browser.new_context(**kwargs)  # type: ignore[attr-defined]

    async def _fetch_once(self, browser: object, url: str, proxy_url: str | None) -> ScrapedResult:
        context = await self._build_context(browser, proxy_url)
        try:
            page = await context.new_page()  # type: ignore[attr-defined]
            await self._apply_stealth(context)
            return await self._navigate_and_extract(page, url)
        finally:
            await _safe_close(context)

    async def fetch(self, url: str) -> ScrapedResult:
        """Fetch *url* with a stealthed headless Chromium context and proxy rotation.

        A fresh proxy is picked per call from ``settings.PROXY_URLS`` (empty ⇒
        direct). On a detected block/CAPTCHA the fetch rotates to the next proxy up
        to ``settings.MAX_PROXY_ROTATIONS`` times before resolving to BLOCKED/CAPTCHA.
        """
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright

        rotator = ProxyRotator()
        block_budget = settings.MAX_PROXY_ROTATIONS
        browser = None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                while True:
                    result = await self._fetch_once(browser, url, rotator.current())
                    if result.extraction_status not in _BLOCK_STATUSES:
                        return result
                    if rotator.enabled and block_budget > 0:
                        block_budget -= 1
                        logger.info(
                            "playwright_rotating_proxy_on_block",
                            scraper=type(self).__name__,
                            url=url,
                            remaining_budget=block_budget,
                        )
                        rotator.next_proxy()
                        continue
                    logger.warning(
                        "playwright_block_persisted",
                        scraper=type(self).__name__,
                        url=url,
                        classification=result.extraction_status.value,
                    )
                    return result
        except Exception as exc:
            if isinstance(exc, PlaywrightTimeoutError):
                return _result(
                    url, "", "", price=None, currency=None, status=ExtractionStatus.HTTP_ERROR
                )
            raise ScraperError(f"Playwright error: {exc}") from exc
        finally:
            if browser is not None:
                await _safe_close(browser)


async def _safe_close(closable: object) -> None:
    try:
        await closable.close()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — teardown best-effort
        pass


_BLOCK_STATUSES = (ExtractionStatus.BLOCKED, ExtractionStatus.CAPTCHA)
