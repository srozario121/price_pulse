"""Unit tests for proxy + stealth + block handling on the Amazon path (Item 15).

Builds a fresh mocked Playwright context per fetch attempt so proxy rotation is
observable, and records ``new_context`` kwargs + ``add_init_script`` calls to
assert the stealthed, proxied context is constructed as expected. Arrange-Act-Assert.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.enums import ExtractionStatus
from app.scrapers.amazon import _STEALTH_INIT_SCRIPT, AmazonScraper
from app.scrapers.anti_blocking import USER_AGENTS

_CAPTCHA_HTML = "<html><body>Enter the characters you see below</body></html>"
_OK_HTML = "<html><body>ok £9.99</body></html>"
_LD_OK = {"price": "9.99", "currency": "GBP"}


def _make_playwright(attempts: list[dict]):
    """Return (playwright_cm, context_kwargs, init_scripts).

    Each entry in *attempts* programs one context: ``{html, status, evaluate}``.
    ``context_kwargs`` records the kwargs of each ``new_context`` (proxy/user_agent/
    headers); ``init_scripts`` records every ``add_init_script`` payload.
    """
    context_kwargs: list[dict] = []
    init_scripts: list = []
    specs = iter(attempts)

    def _new_context(**kwargs):
        context_kwargs.append(kwargs)
        spec = next(specs)

        resp = MagicMock()
        resp.status = spec.get("status", 200)

        page = AsyncMock()
        page.goto = AsyncMock(return_value=resp)
        page.content = AsyncMock(return_value=spec["html"])
        ev = spec.get("evaluate")
        if isinstance(ev, list):
            page.evaluate = AsyncMock(side_effect=ev)
        else:
            page.evaluate = AsyncMock(return_value=ev)

        def _rec(*a, **k):
            init_scripts.append(a[0] if a else k.get("script"))

        context = AsyncMock()
        context.new_page = AsyncMock(return_value=page)
        context.add_init_script = AsyncMock(side_effect=_rec)
        context.close = AsyncMock()
        return context

    browser = AsyncMock()
    browser.new_context = AsyncMock(side_effect=_new_context)
    browser.close = AsyncMock()

    chromium = AsyncMock()
    chromium.launch = AsyncMock(return_value=browser)
    p = AsyncMock()
    p.chromium = chromium

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=p)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, context_kwargs, init_scripts


@pytest.fixture
def _pin_rotation(monkeypatch):
    monkeypatch.setattr("app.scrapers.anti_blocking.random.randrange", lambda _n: 0)


def _set_proxies(monkeypatch, proxies: list[str], max_rotations: int = 2) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "PROXY_URLS", proxies)
    monkeypatch.setattr(settings, "MAX_PROXY_ROTATIONS", max_rotations)


@pytest.mark.asyncio
async def test_context_built_with_proxy_ua_and_matched_headers(_pin_rotation, monkeypatch):
    # Arrange
    _set_proxies(monkeypatch, ["http://user:pass@px:8080"])
    cm, context_kwargs, _ = _make_playwright([{"html": _OK_HTML, "evaluate": _LD_OK}])

    # Act
    with patch("playwright.async_api.async_playwright", return_value=cm):
        result = await AmazonScraper().fetch("https://amazon.co.uk/dp/B1")

    # Assert
    assert result.extraction_status == ExtractionStatus.OK
    assert result.price == Decimal("9.99")
    kwargs = context_kwargs[0]
    assert kwargs["proxy"] == {
        "server": "http://px:8080",
        "username": "user",
        "password": "pass",
    }
    assert kwargs["user_agent"] in USER_AGENTS
    # Matched headers ride on the context, without duplicating the UA header.
    assert kwargs["extra_http_headers"]["Accept-Language"] == "en-GB,en;q=0.9"
    assert "User-Agent" not in kwargs["extra_http_headers"]


@pytest.mark.asyncio
async def test_custom_stealth_init_script_registered(_pin_rotation, monkeypatch):
    # Arrange
    _set_proxies(monkeypatch, [])
    cm, _, init_scripts = _make_playwright([{"html": _OK_HTML, "evaluate": _LD_OK}])

    # Act
    with patch("playwright.async_api.async_playwright", return_value=cm):
        await AmazonScraper().fetch("https://amazon.co.uk/dp/B1")

    # Assert — our custom top-up patches are registered on the context
    assert _STEALTH_INIT_SCRIPT in init_scripts


@pytest.mark.asyncio
async def test_200_captcha_page_classified_as_captcha(_pin_rotation, monkeypatch):
    # Arrange — no proxy; a 200 robot-check page must be CAPTCHA, not extraction_failed
    _set_proxies(monkeypatch, [])
    cm, _, _ = _make_playwright([{"html": _CAPTCHA_HTML, "status": 200}])

    # Act
    with patch("playwright.async_api.async_playwright", return_value=cm):
        result = await AmazonScraper().fetch("https://amazon.co.uk/dp/B1")

    # Assert
    assert result.extraction_status == ExtractionStatus.CAPTCHA
    assert result.price is None


@pytest.mark.asyncio
async def test_rotates_proxy_on_block_then_succeeds(_pin_rotation, monkeypatch):
    # Arrange — first proxy sees a CAPTCHA, second serves a good ld+json page
    _set_proxies(monkeypatch, ["http://p1:8080", "http://p2:8080"], max_rotations=1)
    cm, context_kwargs, _ = _make_playwright(
        [
            {"html": _CAPTCHA_HTML, "status": 200},
            {"html": _OK_HTML, "evaluate": _LD_OK},
        ]
    )

    # Act
    with patch("playwright.async_api.async_playwright", return_value=cm):
        result = await AmazonScraper().fetch("https://amazon.co.uk/dp/B1")

    # Assert — rotated to the second proxy and recovered
    assert [k["proxy"]["server"] for k in context_kwargs] == [
        "http://p1:8080",
        "http://p2:8080",
    ]
    assert result.extraction_status == ExtractionStatus.OK


@pytest.mark.asyncio
async def test_block_persists_past_budget_returns_captcha(_pin_rotation, monkeypatch):
    # Arrange — every proxy serves a CAPTCHA; budget 1 ⇒ 2 attempts
    _set_proxies(monkeypatch, ["http://p1:8080", "http://p2:8080"], max_rotations=1)
    cm, context_kwargs, _ = _make_playwright(
        [{"html": _CAPTCHA_HTML, "status": 200}, {"html": _CAPTCHA_HTML, "status": 200}]
    )

    # Act
    with patch("playwright.async_api.async_playwright", return_value=cm):
        result = await AmazonScraper().fetch("https://amazon.co.uk/dp/B1")

    # Assert — bounded, resolves to CAPTCHA
    assert len(context_kwargs) == 2
    assert result.extraction_status == ExtractionStatus.CAPTCHA
