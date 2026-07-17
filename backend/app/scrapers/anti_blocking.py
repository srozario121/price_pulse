"""Shared anti-blocking primitives for both fetch paths (Item 15).

Consolidates what the httpx path (``http_client``) and the Playwright path
(``amazon``) must keep identical:

* a single User-Agent pool and a *matched* header set (``Accept-Language`` +
  ``Sec-CH-UA*`` client hints that agree with the chosen UA);
* proxy rotation over the BYO ``settings.PROXY_URLS`` list (per-request pick +
  ``next_proxy()`` on a block), plus a normaliser that turns one BYO entry into
  both the httpx string and the Playwright ``proxy`` dict;
* a block/CAPTCHA classifier that runs in *both* paths, so a 200-status robot
  check is caught rather than mis-recorded as ``extraction_failed``.

This module deliberately imports nothing from the scraper fetch modules to keep
the dependency arrow one-way (``http_client``/``amazon`` → ``anti_blocking``).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from app.core.config import settings
from app.models.enums import ExtractionStatus

# ── User-Agent pool ────────────────────────────────────────────────────────────
# Kept current and matched to the browser builds encoded in the Sec-CH-UA hints
# below. Moved here from http_client so both fetch paths rotate the same pool.
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6 Mobile Safari/537.36",
]

_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
)
# Public so the Playwright path can pin just this on the browser context.
ACCEPT_LANGUAGE = "en-GB,en;q=0.9"


def choose_user_agent() -> str:
    """Return a random User-Agent from the shared pool."""
    return random.choice(USER_AGENTS)


def _platform(user_agent: str) -> str:
    if "Windows NT" in user_agent:
        return "Windows"
    if "Android" in user_agent:
        return "Android"
    if "Macintosh" in user_agent or "Mac OS X" in user_agent:
        return "macOS"
    if "Linux" in user_agent:
        return "Linux"
    return "Unknown"


def _chromium_brand(user_agent: str) -> tuple[str, str] | None:
    """Return (brand, major-version) for a Chromium UA, or None for Firefox/Safari.

    Only Chromium-family browsers (Chrome, Edge) emit ``Sec-CH-UA`` client hints;
    Firefox and Safari do not, so the header set must omit them there.
    """
    m = re.search(r"Chrome/(\d+)", user_agent)
    if not m:
        return None  # Firefox / Safari — no client hints
    version = m.group(1)
    if "Edg/" in user_agent:
        return "Microsoft Edge", version
    return "Google Chrome", version


def build_headers(user_agent: str) -> dict[str, str]:
    """Build a realistic request-header set matched to *user_agent*.

    The ``Sec-CH-UA*`` client hints are only added for Chromium-family agents
    (Chrome/Edge); a Firefox or Safari UA gets a header set without them, matching
    what those browsers actually send.
    """
    headers: dict[str, str] = {
        "User-Agent": user_agent,
        "Accept": _ACCEPT,
        "Accept-Language": ACCEPT_LANGUAGE,
        # Only advertise encodings httpx can actually decode. Requesting "br"
        # without a Brotli decoder installed makes response.text raise a
        # DecodingError on a Brotli-compressed reply, which would also break
        # classify_block. gzip/deflate are always decodable by httpx.
        "Accept-Encoding": "gzip, deflate",
        "Upgrade-Insecure-Requests": "1",
    }

    brand = _chromium_brand(user_agent)
    if brand is not None:
        name, version = brand
        headers["Sec-CH-UA"] = (
            f'"Chromium";v="{version}", "{name}";v="{version}", "Not-A.Brand";v="99"'
        )
        headers["Sec-CH-UA-Mobile"] = "?1" if "Mobile" in user_agent else "?0"
        headers["Sec-CH-UA-Platform"] = f'"{_platform(user_agent)}"'
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "none"
        headers["Sec-Fetch-User"] = "?1"

    return headers


# ── Proxy rotation ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProxyConfig:
    """One BYO proxy entry, shaped for both fetch clients.

    ``httpx`` is the URL string passed to ``httpx.AsyncClient(proxy=…)``;
    ``playwright`` is the ``{"server", "username"?, "password"?}`` dict passed to
    ``browser.new_context(proxy=…)`` (credentials go in separate keys, not the
    server URL).
    """

    httpx: str
    playwright: dict[str, str]


def normalise_proxy(proxy_url: str) -> ProxyConfig:
    """Convert one BYO proxy entry into both the httpx and Playwright shapes."""
    parsed = urlparse(proxy_url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"Malformed proxy URL: {proxy_url!r}")

    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port is not None:
        server = f"{server}:{parsed.port}"

    playwright: dict[str, str] = {"server": server}
    if parsed.username:
        playwright["username"] = unquote(parsed.username)
    if parsed.password is not None:
        playwright["password"] = unquote(parsed.password)

    return ProxyConfig(httpx=proxy_url, playwright=playwright)


class ProxyRotator:
    """Rotates over the BYO proxy list for a single fetch call.

    A fresh instance is created per ``fetch`` so each request picks its own
    starting proxy (per-request diversity); ``next_proxy()`` advances on a
    detected block or a dead proxy and wraps around. An empty list means proxying
    is disabled (``enabled`` is False and ``current()`` is None), so callers make
    a direct connection.
    """

    def __init__(self, proxies: list[str] | None = None, *, start: int | None = None) -> None:
        self._proxies: list[str] = list(settings.PROXY_URLS if proxies is None else proxies)
        if not self._proxies:
            self._index = 0
        elif start is None:
            self._index = random.randrange(len(self._proxies))
        else:
            self._index = start % len(self._proxies)

    @property
    def enabled(self) -> bool:
        return bool(self._proxies)

    @property
    def count(self) -> int:
        return len(self._proxies)

    def current(self) -> str | None:
        if not self._proxies:
            return None
        return self._proxies[self._index % len(self._proxies)]

    def next_proxy(self) -> str | None:
        """Advance to the next proxy (wrapping) and return it, or None if disabled."""
        if not self._proxies:
            return None
        self._index = (self._index + 1) % len(self._proxies)
        return self.current()


# ── Block / CAPTCHA classification ─────────────────────────────────────────────
# Substrings are matched case-insensitively against the page HTML. Markers are
# kept specific enough that ordinary product pages do not trip them.

# Robot-check interstitials / JS challenge pages (often served with HTTP 200).
_CAPTCHA_MARKERS: tuple[str, ...] = (
    "enter the characters you see below",
    "type the characters you see in this image",
    "/errors/validatecaptcha",
    "api-services-support@amazon.com",
    "we just need to make sure you're not a robot",
    "g-recaptcha",
    "grecaptcha",
    "hcaptcha",
    "px-captcha",
    "cf-browser-verification",
    "checking your browser before accessing",
    "unusual traffic",
)

# Hard access-denied / IP-ban pages.
_BLOCKED_MARKERS: tuple[str, ...] = (
    "access denied",
    "you have been blocked",
    "attention required! | cloudflare",
    "request unsuccessful. incapsula incident",
    "your ip address has been temporarily blocked",
    "rate limit exceeded",
)


def classify_block(status_code: int, html: str | None) -> ExtractionStatus | None:
    """Classify a response as BLOCKED, CAPTCHA, or neither (None).

    CAPTCHA markers win over status codes so a Cloudflare/Amazon challenge served
    with 503 or 200 is recognised as a challenge rather than a plain block. A 429
    or 503 with no challenge markers is a BLOCKED; ban markers on any status are
    also BLOCKED. Ordinary 200 product HTML returns None.
    """
    lowered = (html or "").lower()
    if any(marker in lowered for marker in _CAPTCHA_MARKERS):
        return ExtractionStatus.CAPTCHA
    if status_code in (429, 503):
        return ExtractionStatus.BLOCKED
    if any(marker in lowered for marker in _BLOCKED_MARKERS):
        return ExtractionStatus.BLOCKED
    return None
