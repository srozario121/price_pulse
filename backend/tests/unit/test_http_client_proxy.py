"""Unit tests for proxy rotation + block detection in fetch_page (Item 15).

Deterministic: the proxy rotator's random start index is pinned to 0, robots/rate-limit
are stubbed, and httpx.AsyncClient is replaced by a scripted fake that records the
``proxy`` kwarg of each attempt so we can assert *egress through* the expected proxy
and the rotation order across attempts. Arrange-Act-Assert throughout.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.enums import ExtractionStatus
from app.scrapers.http_client import fetch_page

_CAPTCHA_HTML = "<html><body>Enter the characters you see below</body></html>"
_OK_HTML = "<html><body>£19.99</body></html>"


def _resp(status: int, text: str = "body", headers: dict | None = None) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.text = text
    r.headers = headers or {}
    return r


def _client_factory(script: list):
    """Return (factory, proxies_used).

    *script* is consumed one entry per ``httpx.AsyncClient()`` construction; each is
    either ``("resp", response)`` or ``("raise", exception)``. ``proxies_used`` records
    the ``proxy`` kwarg of every construction, in order.
    """
    proxies_used: list[str | None] = []
    steps = iter(script)

    def factory(*_args, **kwargs):
        proxies_used.append(kwargs.get("proxy"))
        kind, payload = next(steps)
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        if kind == "raise":
            client.get = AsyncMock(side_effect=payload)
        else:
            client.get = AsyncMock(return_value=payload)
        return client

    return factory, proxies_used


@pytest.fixture
def _pin_rotation(monkeypatch):
    """Pin the rotator's random start to index 0 and stub robots/rate-limit."""
    monkeypatch.setattr("app.scrapers.anti_blocking.random.randrange", lambda _n: 0)
    monkeypatch.setattr("app.scrapers.http_client._check_robots", AsyncMock())
    monkeypatch.setattr("app.scrapers.http_client._apply_rate_limit", AsyncMock())


def _set_proxies(monkeypatch, proxies: list[str], max_rotations: int = 2) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "PROXY_URLS", proxies)
    monkeypatch.setattr(settings, "MAX_PROXY_ROTATIONS", max_rotations)


@pytest.mark.asyncio
async def test_request_egresses_through_configured_proxy(_pin_rotation, monkeypatch):
    # Arrange
    _set_proxies(monkeypatch, ["http://user:pass@proxy1:8080"])
    factory, proxies_used = _client_factory([("resp", _resp(200, _OK_HTML))])

    # Act
    with patch("app.scrapers.http_client.httpx.AsyncClient", side_effect=factory):
        result = await fetch_page("https://example.com/p")

    # Assert — the httpx client was constructed with the proxy (egress through it)
    assert proxies_used == ["http://user:pass@proxy1:8080"]
    assert result.extraction_status == ExtractionStatus.OK


@pytest.mark.asyncio
async def test_block_rotates_to_next_proxy_then_succeeds(_pin_rotation, monkeypatch):
    # Arrange — first two proxies are blocked (429), the third serves a good page
    _set_proxies(monkeypatch, ["p1://a", "p2://b", "p3://c"], max_rotations=2)
    factory, proxies_used = _client_factory(
        [("resp", _resp(429)), ("resp", _resp(429)), ("resp", _resp(200, _OK_HTML))]
    )

    # Act
    with patch("app.scrapers.http_client.httpx.AsyncClient", side_effect=factory):
        result = await fetch_page("https://example.com/p")

    # Assert — rotated p1 → p2 → p3 and recovered
    assert proxies_used == ["p1://a", "p2://b", "p3://c"]
    assert result.extraction_status == ExtractionStatus.OK


@pytest.mark.asyncio
async def test_block_persisting_past_budget_returns_blocked(_pin_rotation, monkeypatch):
    # Arrange — every proxy blocks; budget is 2 (so 3 attempts total)
    _set_proxies(monkeypatch, ["p1://a", "p2://b", "p3://c"], max_rotations=2)
    factory, proxies_used = _client_factory([("resp", _resp(429))] * 3)

    # Act
    with patch("app.scrapers.http_client.httpx.AsyncClient", side_effect=factory):
        result = await fetch_page("https://example.com/p")

    # Assert — no infinite loop; resolves to BLOCKED after the budget is spent
    assert len(proxies_used) == 3
    assert result.extraction_status == ExtractionStatus.BLOCKED


@pytest.mark.asyncio
async def test_captcha_persisting_past_budget_returns_captcha(_pin_rotation, monkeypatch):
    # Arrange — a 200-status robot check on every proxy
    _set_proxies(monkeypatch, ["p1://a", "p2://b"], max_rotations=1)
    factory, _ = _client_factory([("resp", _resp(200, _CAPTCHA_HTML))] * 2)

    # Act
    with patch("app.scrapers.http_client.httpx.AsyncClient", side_effect=factory):
        result = await fetch_page("https://example.com/p")

    # Assert
    assert result.extraction_status == ExtractionStatus.CAPTCHA


@pytest.mark.asyncio
async def test_dead_proxies_rotate_and_fail_bounded(_pin_rotation, monkeypatch):
    # Arrange — every proxy is unreachable
    _set_proxies(monkeypatch, ["p1://a", "p2://b"], max_rotations=2)
    factory, proxies_used = _client_factory(
        [("raise", httpx.ConnectError("boom")), ("raise", httpx.ConnectError("boom"))]
    )

    # Act
    with patch("app.scrapers.http_client.httpx.AsyncClient", side_effect=factory):
        result = await fetch_page("https://example.com/p")

    # Assert — each proxy tried once, then a bounded HTTP_ERROR (not a hang)
    assert proxies_used == ["p1://a", "p2://b"]
    assert result.extraction_status == ExtractionStatus.HTTP_ERROR


@pytest.mark.asyncio
async def test_dead_proxy_does_not_consume_block_budget(_pin_rotation, monkeypatch):
    # Arrange — p1 dead, p2 blocks, p3 ok; budget is only 1
    _set_proxies(monkeypatch, ["p1://a", "p2://b", "p3://c"], max_rotations=1)
    factory, proxies_used = _client_factory(
        [
            ("raise", httpx.ConnectError("boom")),  # p1 dead — must NOT spend block budget
            ("resp", _resp(429)),  # p2 blocked — spends the single block rotation
            ("resp", _resp(200, _OK_HTML)),  # p3 ok
        ]
    )

    # Act
    with patch("app.scrapers.http_client.httpx.AsyncClient", side_effect=factory):
        result = await fetch_page("https://example.com/p")

    # Assert — reached p3 despite budget=1, proving the dead proxy was free
    assert proxies_used == ["p1://a", "p2://b", "p3://c"]
    assert result.extraction_status == ExtractionStatus.OK


@pytest.mark.asyncio
async def test_200_captcha_with_no_proxy_records_captcha(_pin_rotation, monkeypatch):
    # Arrange — proxying disabled; a 200 robot-check page cannot be rotated away
    _set_proxies(monkeypatch, [])
    factory, proxies_used = _client_factory([("resp", _resp(200, _CAPTCHA_HTML))])

    # Act
    with patch("app.scrapers.http_client.httpx.AsyncClient", side_effect=factory):
        result = await fetch_page("https://example.com/p")

    # Assert — direct connection (no proxy), classified as CAPTCHA
    assert proxies_used == [None]
    assert result.extraction_status == ExtractionStatus.CAPTCHA


@pytest.mark.asyncio
async def test_persistent_429_no_proxy_resolves_to_blocked(_pin_rotation, monkeypatch):
    # Arrange — no proxy; a persistent 429 exhausts the transient retry chain
    _set_proxies(monkeypatch, [])
    factory, _ = _client_factory([("resp", _resp(429))] * 3)

    # Act
    with (
        patch("app.scrapers.http_client.httpx.AsyncClient", side_effect=factory),
        patch("app.scrapers.http_client.asyncio.sleep", new=AsyncMock()),
    ):
        result = await fetch_page("https://example.com/p")

    # Assert — the exhausted 429 chain resolves to BLOCKED rather than a bare HTTP_ERROR
    assert result.extraction_status == ExtractionStatus.BLOCKED
