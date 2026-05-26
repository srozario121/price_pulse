"""Unit tests for the shared HTTP client (fetch_page)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.enums import ExtractionStatus
from app.scrapers.http_client import fetch_page


def _make_response(status_code: int, text: str = "body", headers: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}
    return resp


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_client_success() -> None:
    mock_response = _make_response(200, "<html>Product page</html>")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.scrapers.http_client.httpx.AsyncClient", return_value=mock_client),
        patch("app.scrapers.http_client._check_robots", new=AsyncMock()),
        patch("app.scrapers.http_client._apply_rate_limit", new=AsyncMock()),
    ):
        result = await fetch_page("http://example.com/product")

    assert result.extraction_status == ExtractionStatus.OK
    assert result.html == "<html>Product page</html>"
    assert result.html_hash != ""
    assert result.price is None


# ---------------------------------------------------------------------------
# Retry on 5xx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_client_retries_5xx() -> None:
    """Three 500 responses → HTTP_ERROR after all retries exhausted."""
    mock_response = _make_response(500)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.scrapers.http_client.httpx.AsyncClient", return_value=mock_client),
        patch("app.scrapers.http_client._check_robots", new=AsyncMock()),
        patch("app.scrapers.http_client._apply_rate_limit", new=AsyncMock()),
        patch("app.scrapers.http_client.asyncio.sleep", new=AsyncMock()),
    ):
        result = await fetch_page("http://example.com/product")

    assert result.extraction_status == ExtractionStatus.HTTP_ERROR
    assert result.html == ""
    assert result.html_hash == ""
    # 3 retries → 3 calls
    assert mock_client.get.call_count == 3


# ---------------------------------------------------------------------------
# 429 with Retry-After header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_client_429_retry_after() -> None:
    """429 with Retry-After header → sleep that many seconds."""
    resp_429 = _make_response(429, headers={"Retry-After": "1"})
    resp_200 = _make_response(200, "<html>ok</html>")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[resp_429, resp_200])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    sleep_mock = AsyncMock()

    with (
        patch("app.scrapers.http_client.httpx.AsyncClient", return_value=mock_client),
        patch("app.scrapers.http_client._check_robots", new=AsyncMock()),
        patch("app.scrapers.http_client._apply_rate_limit", new=AsyncMock()),
        patch("app.scrapers.http_client.asyncio.sleep", new=sleep_mock),
    ):
        result = await fetch_page("http://example.com/product")

    # Should have slept for 1 second (Retry-After value)
    sleep_mock.assert_called_once_with(1.0)
    assert result.extraction_status == ExtractionStatus.OK


# ---------------------------------------------------------------------------
# User-Agent varies across calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_client_user_agent_varies() -> None:
    """User-Agent header should differ across multiple calls (with high probability)."""
    captured_headers: list[str] = []

    async def fake_get(url: str, headers: dict) -> MagicMock:
        captured_headers.append(headers.get("User-Agent", ""))
        return _make_response(200, "<html>ok</html>")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.scrapers.http_client.httpx.AsyncClient", return_value=mock_client),
        patch("app.scrapers.http_client._check_robots", new=AsyncMock()),
        patch("app.scrapers.http_client._apply_rate_limit", new=AsyncMock()),
    ):
        for _ in range(20):
            await fetch_page("http://example.com/product")

    # With 8 user agents and 20 calls, the chance of ALL being identical is (1/8)^19 ≈ 0
    assert len(set(captured_headers)) > 1


# ---------------------------------------------------------------------------
# Rate-limit key set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_client_rate_limit_key_set() -> None:
    """When redis_client is provided, a rate_limit:{domain} key should be set."""
    mock_response = _make_response(200, "<html>ok</html>")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock()

    with (
        patch("app.scrapers.http_client.httpx.AsyncClient", return_value=mock_client),
        patch("app.scrapers.http_client._check_robots", new=AsyncMock()),
    ):
        await fetch_page("http://example.com/product", redis_client=redis_mock)

    # set() should have been called with the rate_limit key
    set_calls = [str(call) for call in redis_mock.set.call_args_list]
    assert any("rate_limit:example.com" in c for c in set_calls)


# ---------------------------------------------------------------------------
# Non-retryable error (404)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_client_404_returns_error() -> None:
    mock_response = _make_response(404)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.scrapers.http_client.httpx.AsyncClient", return_value=mock_client),
        patch("app.scrapers.http_client._check_robots", new=AsyncMock()),
        patch("app.scrapers.http_client._apply_rate_limit", new=AsyncMock()),
    ):
        result = await fetch_page("http://example.com/missing")

    assert result.extraction_status == ExtractionStatus.HTTP_ERROR
    # Only one attempt for non-retryable
    assert mock_client.get.call_count == 1
