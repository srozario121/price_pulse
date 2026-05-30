"""Unit tests for the http_client helper functions introduced in the CC/Halstead refactor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFetchRobotsText:
    @pytest.mark.asyncio
    async def test_returns_cached_bytes(self) -> None:
        from app.scrapers.http_client import _fetch_robots_text

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"User-agent: *\nDisallow: /")
        result = await _fetch_robots_text("example.com", "https://example.com/robots.txt", redis)
        assert result == "User-agent: *\nDisallow: /"
        redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_cached_str(self) -> None:
        from app.scrapers.http_client import _fetch_robots_text

        redis = AsyncMock()
        redis.get = AsyncMock(return_value="User-agent: *\nAllow: /")
        result = await _fetch_robots_text("example.com", "https://example.com/robots.txt", redis)
        assert result == "User-agent: *\nAllow: /"

    @pytest.mark.asyncio
    async def test_fetches_from_http_on_cache_miss(self) -> None:
        from app.scrapers.http_client import _fetch_robots_text

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "User-agent: *\nDisallow: /admin"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.scrapers.http_client.httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_robots_text(
                "example.com", "https://example.com/robots.txt", redis
            )

        assert result == "User-agent: *\nDisallow: /admin"
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_404_returns_empty(self) -> None:
        from app.scrapers.http_client import _fetch_robots_text

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.scrapers.http_client.httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_robots_text("example.com", "https://example.com/robots.txt", None)

        assert result == ""

    @pytest.mark.asyncio
    async def test_http_exception_returns_empty(self) -> None:
        import httpx

        from app.scrapers.http_client import _fetch_robots_text

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.scrapers.http_client.httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_robots_text("example.com", "https://example.com/robots.txt", None)

        assert result == ""

    @pytest.mark.asyncio
    async def test_redis_get_exception_is_non_fatal(self) -> None:
        from app.scrapers.http_client import _fetch_robots_text

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        redis.set = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "robots"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.scrapers.http_client.httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_robots_text(
                "example.com", "https://example.com/robots.txt", redis
            )

        assert result == "robots"

    @pytest.mark.asyncio
    async def test_redis_set_exception_is_non_fatal(self) -> None:
        from app.scrapers.http_client import _fetch_robots_text

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(side_effect=Exception("redis down"))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "robots"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.scrapers.http_client.httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_robots_text(
                "example.com", "https://example.com/robots.txt", redis
            )

        assert result == "robots"

    @pytest.mark.asyncio
    async def test_no_redis_skips_cache(self) -> None:
        from app.scrapers.http_client import _fetch_robots_text

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "User-agent: *"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.scrapers.http_client.httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_robots_text("example.com", "https://example.com/robots.txt", None)

        assert result == "User-agent: *"


class TestLogIfDisallowed:
    def test_empty_robots_text_returns_early(self) -> None:
        from app.scrapers.http_client import _log_if_disallowed

        with patch("app.scrapers.http_client.logger") as mock_logger:
            _log_if_disallowed("https://example.com/product", "https://example.com/robots.txt", "")
        mock_logger.warning.assert_not_called()

    def test_allowed_path_no_warning(self) -> None:
        from app.scrapers.http_client import _log_if_disallowed

        robots_text = "User-agent: *\nAllow: /"

        with patch("app.scrapers.http_client.logger") as mock_logger:
            _log_if_disallowed(
                "https://example.com/product",
                "https://example.com/robots.txt",
                robots_text,
            )
        mock_logger.warning.assert_not_called()

    def test_disallowed_path_logs_warning(self) -> None:
        from app.scrapers.http_client import _log_if_disallowed

        robots_text = "User-agent: *\nDisallow: /"

        with patch("app.scrapers.http_client.logger") as mock_logger:
            _log_if_disallowed(
                "https://example.com/product",
                "https://example.com/robots.txt",
                robots_text,
            )
        mock_logger.warning.assert_called_once()
        call_event = mock_logger.warning.call_args[0][0]
        assert call_event == "robots_txt_disallowed"


class TestCheckRobots:
    @pytest.mark.asyncio
    async def test_delegates_to_helpers(self) -> None:
        from app.scrapers.http_client import _check_robots

        with (
            patch("app.scrapers.http_client._fetch_robots_text", new=AsyncMock(return_value="")),
            patch("app.scrapers.http_client._log_if_disallowed") as mock_log,
        ):
            await _check_robots("https://example.com/page", None)
        mock_log.assert_called_once()


class TestApplyRateLimit:
    @pytest.mark.asyncio
    async def test_none_redis_returns_immediately(self) -> None:
        from app.scrapers.http_client import _apply_rate_limit

        # No exception means it returned without doing anything
        await _apply_rate_limit("example.com", None)

    @pytest.mark.asyncio
    async def test_sleeps_when_rate_limit_key_exists(self) -> None:
        from app.scrapers.http_client import _apply_rate_limit

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"1")
        redis.set = AsyncMock()
        sleep_mock = AsyncMock()

        with patch("app.scrapers.http_client.asyncio.sleep", sleep_mock):
            await _apply_rate_limit("example.com", redis)

        sleep_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_exception_is_non_fatal(self) -> None:
        from app.scrapers.http_client import _apply_rate_limit

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=Exception("redis down"))

        # Should not raise
        await _apply_rate_limit("example.com", redis)


class TestResultForStatus:
    def test_200_returns_scraped_result(self) -> None:
        from app.models.enums import ExtractionStatus
        from app.scrapers.http_client import _result_for_status

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>hi</html>"

        result = _result_for_status("https://example.com", mock_resp, 0)
        assert result is not None
        assert result.extraction_status == ExtractionStatus.OK
        assert result.html == "<html>hi</html>"

    def test_404_returns_error_result(self) -> None:
        from app.models.enums import ExtractionStatus
        from app.scrapers.http_client import _result_for_status

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        result = _result_for_status("https://example.com", mock_resp, 0)
        assert result is not None
        assert result.extraction_status == ExtractionStatus.HTTP_ERROR

    def test_500_returns_none_for_retry(self) -> None:
        from app.scrapers.http_client import _result_for_status

        mock_resp = MagicMock()
        mock_resp.status_code = 500

        result = _result_for_status("https://example.com", mock_resp, 0)
        assert result is None

    def test_429_returns_none_for_retry(self) -> None:
        from app.scrapers.http_client import _result_for_status

        mock_resp = MagicMock()
        mock_resp.status_code = 429

        result = _result_for_status("https://example.com", mock_resp, 0)
        assert result is None

    def test_403_returns_none_for_retry(self) -> None:
        from app.scrapers.http_client import _result_for_status

        mock_resp = MagicMock()
        mock_resp.status_code = 403

        result = _result_for_status("https://example.com", mock_resp, 0)
        assert result is None
