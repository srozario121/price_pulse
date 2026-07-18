"""Facebook Marketplace scraper — Playwright path, hardest source (Item 18).

Unlike the retail scrapers, Marketplace is a login-walled C2C platform with
aggressive bot-protection and per-listing (not fixed-catalogue) pricing; listings
expire/vanish and there is no ``ld+json`` price. It is built on Item 15's shared
anti-blocking module (proxy rotation + stealth, inherited from
:class:`PlaywrightScraper`) and — critically — its login wall / bot-check must
classify via ``classify_block`` (plus the FB-specific markers below) as
``BLOCKED``/``CAPTCHA``, **never** ``extraction_failed`` (which Item 16 reserves
for genuine selector drift and which must never feed selector generation).

ToS / robots / auth-handling risk is documented in the Item 18 ADR. This scraper
runs unauthenticated and best-effort: a login wall resolves to ``BLOCKED`` so the
product surfaces on ``/products/failing`` rather than recording a bogus price.
"""

from __future__ import annotations

from app.models.enums import ExtractionStatus
from app.scrapers.playwright_base import PlaywrightScraper

# Substrings that mark a login wall (access gated → BLOCKED) — matched
# case-insensitively against the rendered HTML.
_LOGIN_MARKERS: tuple[str, ...] = (
    "you must log in to continue",
    "log in to facebook",
    "you must log in first",
    'name="login"',
    "login_form",
)
# Substrings that mark a bot-check / checkpoint interstitial → CAPTCHA.
_CHECKPOINT_MARKERS: tuple[str, ...] = (
    "/checkpoint/",
    "security check",
    "confirm you're a human",
    "confirm you’re a human",
)


class FacebookMarketplaceScraper(PlaywrightScraper):
    """Scraper for facebook.com/marketplace listing pages."""

    DEFAULT_CURRENCY = "GBP"
    # Marketplace ships no stable test hooks; price is a symbol-prefixed span in
    # the listing header. These are heuristic and brittle by construction — a
    # miss resolves to extraction_failed (Item 16 territory), a login wall to
    # BLOCKED (below).
    PRICE_SELECTORS = (
        '[data-testid="marketplace_pdp_price"]',
        'div[role="main"] span[dir="auto"]',
    )

    def _detect_block(self, status_code: int, html: str) -> ExtractionStatus | None:
        """Classify FB login walls / checkpoints before the generic classifier."""
        base = super()._detect_block(status_code, html)
        if base is not None:
            return base
        lowered = html.lower()
        if any(marker in lowered for marker in _CHECKPOINT_MARKERS):
            return ExtractionStatus.CAPTCHA
        if any(marker in lowered for marker in _LOGIN_MARKERS):
            return ExtractionStatus.BLOCKED
        return None
