"""Extra unit tests to cover scrape.py exception/retry branches."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_session_mock() -> AsyncMock:
    exec_result = AsyncMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=MagicMock())
    session = AsyncMock()
    session.execute = AsyncMock(return_value=exec_result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_scrape_product_logs_retry_warning_on_exception() -> None:
    """Exception during scraping: retry warning is logged before re-raise."""
    from app.tasks.scrape import scrape_product

    retry_exc = RuntimeError("retry raised")

    session = _make_session_mock()
    retry_mock = MagicMock(side_effect=retry_exc)

    with (
        patch("app.tasks.scrape.AsyncSessionLocal", return_value=session),
        patch("app.tasks.scrape.get_scraper", side_effect=ValueError("scraper failed")),
        patch("app.tasks.scrape.logger") as log_mock,
    ):
        # Monkey-patch retry on the task instance so self.retry = retry_mock
        original_retry = getattr(scrape_product, "_orig_retry", None)
        scrape_product.retry = retry_mock  # type: ignore[attr-defined]
        try:
            with pytest.raises(RuntimeError, match="retry raised"):
                await scrape_product(product_id=1)
        finally:
            if original_retry is not None:
                scrape_product.retry = original_retry  # type: ignore[attr-defined]
            else:
                try:
                    del scrape_product.retry  # type: ignore[attr-defined]
                except AttributeError:
                    pass

    warning_calls = [c[0][0] for c in log_mock.warning.call_args_list]
    assert "scrape_product_retry" in warning_calls


@pytest.mark.asyncio
async def test_scrape_product_max_retries_exceeded_logs_error() -> None:
    """MaxRetriesExceededError: error is logged and re-raised."""
    from app.tasks.scrape import scrape_product

    class FakeMaxRetries(Exception):
        pass

    max_exc = FakeMaxRetries("max retries")
    retry_mock = MagicMock(side_effect=max_exc)

    session = _make_session_mock()

    with (
        patch("app.tasks.scrape.AsyncSessionLocal", return_value=session),
        patch("app.tasks.scrape.get_scraper", side_effect=ValueError("fail")),
        patch("app.tasks.scrape.logger") as log_mock,
    ):
        scrape_product.retry = retry_mock  # type: ignore[attr-defined]
        scrape_product.MaxRetriesExceededError = FakeMaxRetries  # type: ignore[attr-defined]
        try:
            with pytest.raises(FakeMaxRetries):
                await scrape_product(product_id=1)
        finally:
            try:
                del scrape_product.retry  # type: ignore[attr-defined]
                del scrape_product.MaxRetriesExceededError  # type: ignore[attr-defined]
            except AttributeError:
                pass

    error_calls = [c[0][0] for c in log_mock.error.call_args_list]
    assert "scrape_product_max_retries_exceeded" in error_calls
