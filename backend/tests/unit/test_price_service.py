"""Unit tests for price_service.record_price."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.enums import ExtractionStatus
from app.schemas.scraper import ScrapedResult


def _make_scraped_result(
    html_hash: str = "abc123",
    price: Decimal | None = Decimal("9.99"),
    currency: str | None = "GBP",
    status: ExtractionStatus = ExtractionStatus.OK,
) -> ScrapedResult:
    return ScrapedResult(
        url="http://x.com",
        html="<html/>",
        html_hash=html_hash,
        price=price,
        currency=currency,
        scraped_at=datetime.utcnow(),
        extraction_status=status,
    )


def _make_price_record(html_hash: str | None = "abc123") -> MagicMock:
    record = MagicMock()
    record.raw_html_hash = html_hash
    return record


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_price_deduplication() -> None:
    """Same html_hash → no new row inserted; existing record returned."""
    from app.services import price_service

    existing = _make_price_record("abc123")

    mock_session = AsyncMock()
    mock_execute = AsyncMock()
    mock_execute.scalar_one_or_none = MagicMock(return_value=existing)
    mock_session.execute = AsyncMock(return_value=mock_execute)

    scraped = _make_scraped_result(html_hash="abc123")

    with patch("app.services.price_service.alert_service.evaluate_alerts", new=AsyncMock()):
        result = await price_service.record_price(1, scraped, mock_session)

    mock_session.add.assert_not_called()
    assert result is existing


@pytest.mark.asyncio
async def test_record_price_new_hash() -> None:
    """Different html_hash → new PriceRecord inserted."""
    from app.services import price_service

    existing = _make_price_record("old_hash_" + "x" * 55)

    mock_session = AsyncMock()
    mock_execute = AsyncMock()
    mock_execute.scalar_one_or_none = MagicMock(return_value=existing)
    mock_session.execute = AsyncMock(return_value=mock_execute)
    mock_session.flush = AsyncMock()

    scraped = _make_scraped_result(html_hash="new_hash_" + "y" * 55)

    with patch("app.services.price_service.alert_service.evaluate_alerts", new=AsyncMock()):
        await price_service.record_price(1, scraped, mock_session)

    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_record_price_no_existing_record() -> None:
    """No prior record → new PriceRecord inserted."""
    from app.services import price_service

    mock_session = AsyncMock()
    mock_execute = AsyncMock()
    mock_execute.scalar_one_or_none = MagicMock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_execute)
    mock_session.flush = AsyncMock()

    scraped = _make_scraped_result(html_hash="fresh_hash" + "a" * 54)

    with patch("app.services.price_service.alert_service.evaluate_alerts", new=AsyncMock()):
        await price_service.record_price(1, scraped, mock_session)

    mock_session.add.assert_called_once()


@pytest.mark.asyncio
async def test_record_price_empty_hash_always_inserts() -> None:
    """Empty html_hash (HTTP error result) always inserts, never deduplicates."""
    from app.services import price_service

    existing = _make_price_record("")  # empty hash on existing

    mock_session = AsyncMock()
    mock_execute = AsyncMock()
    mock_execute.scalar_one_or_none = MagicMock(return_value=existing)
    mock_session.execute = AsyncMock(return_value=mock_execute)
    mock_session.flush = AsyncMock()

    scraped = _make_scraped_result(
        html_hash="",
        price=None,
        currency=None,
        status=ExtractionStatus.HTTP_ERROR,
    )

    await price_service.record_price(1, scraped, mock_session)
    mock_session.add.assert_called_once()


# ---------------------------------------------------------------------------
# Alert evaluation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_price_calls_evaluate_alerts_on_ok() -> None:
    from app.services import price_service

    mock_session = AsyncMock()
    mock_execute = AsyncMock()
    mock_execute.scalar_one_or_none = MagicMock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_execute)
    mock_session.flush = AsyncMock()

    scraped = _make_scraped_result(status=ExtractionStatus.OK)
    evaluate_mock = AsyncMock()

    with patch("app.services.price_service.alert_service.evaluate_alerts", new=evaluate_mock):
        await price_service.record_price(1, scraped, mock_session)

    evaluate_mock.assert_called_once_with(1, mock_session)


@pytest.mark.asyncio
async def test_record_price_skips_evaluate_alerts_on_extraction_failed() -> None:
    from app.services import price_service

    mock_session = AsyncMock()
    mock_execute = AsyncMock()
    mock_execute.scalar_one_or_none = MagicMock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_execute)
    mock_session.flush = AsyncMock()

    scraped = _make_scraped_result(
        price=None, currency=None, status=ExtractionStatus.EXTRACTION_FAILED
    )
    evaluate_mock = AsyncMock()

    with patch("app.services.price_service.alert_service.evaluate_alerts", new=evaluate_mock):
        await price_service.record_price(1, scraped, mock_session)

    evaluate_mock.assert_not_called()


@pytest.mark.asyncio
async def test_record_price_skips_evaluate_alerts_on_http_error() -> None:
    from app.services import price_service

    mock_session = AsyncMock()
    mock_execute = AsyncMock()
    mock_execute.scalar_one_or_none = MagicMock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_execute)
    mock_session.flush = AsyncMock()

    scraped = _make_scraped_result(
        html_hash="",
        price=None,
        currency=None,
        status=ExtractionStatus.HTTP_ERROR,
    )
    evaluate_mock = AsyncMock()

    with patch("app.services.price_service.alert_service.evaluate_alerts", new=evaluate_mock):
        await price_service.record_price(1, scraped, mock_session)

    evaluate_mock.assert_not_called()
