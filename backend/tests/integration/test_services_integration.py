"""Integration tests for price_service and alert_service against Postgres."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import func, select

from app.models.alert import AlertDirection, PriceAlert
from app.models.enums import ExtractionStatus
from app.models.price_history import PriceRecord
from app.models.product import Product, SourceType
from app.schemas.scraper import ScrapedResult
from app.services import alert_service, price_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scraped_result(
    html_hash: str = "a" * 64,
    price: Decimal | None = Decimal("9.99"),
    currency: str | None = "GBP",
    status: ExtractionStatus = ExtractionStatus.OK,
    html: str = "<html/>",
) -> ScrapedResult:
    return ScrapedResult(
        url="http://example.com/product",
        html=html,
        html_hash=html_hash,
        price=price,
        currency=currency,
        scraped_at=datetime.now(UTC),
        extraction_status=status,
    )


async def _insert_product(session) -> Product:
    product = Product(
        name="Test Product",
        url="http://example.com/product",
        source_type=SourceType.generic,
        css_selector=".price",
        is_active=True,
    )
    session.add(product)
    await session.flush()
    return product


# ---------------------------------------------------------------------------
# price_service integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_price_end_to_end(pg_session) -> None:
    product = await _insert_product(pg_session)

    scraped = _make_scraped_result(
        html_hash="b" * 64,
        price=Decimal("9.99"),
        currency="GBP",
        status=ExtractionStatus.OK,
    )

    with patch(
        "app.services.price_service.alert_service.evaluate_alerts",
        return_value=None,
    ):
        record = await price_service.record_price(product.id, scraped, pg_session)

    assert record.product_id == product.id
    assert record.price == Decimal("9.99")
    assert record.currency == "GBP"
    assert record.extraction_status == "ok"


@pytest.mark.asyncio
async def test_record_price_deduplication_end_to_end(pg_session) -> None:
    product = await _insert_product(pg_session)

    existing = PriceRecord(
        product_id=product.id,
        price=Decimal("9.99"),
        currency="GBP",
        raw_html_hash="c" * 64,
        extraction_status="ok",
    )
    pg_session.add(existing)
    await pg_session.flush()

    # Count rows before
    count_before_result = await pg_session.execute(
        select(func.count()).where(PriceRecord.product_id == product.id)
    )
    count_before = count_before_result.scalar()

    # Record same hash again
    scraped = _make_scraped_result(html_hash="c" * 64)

    with patch(
        "app.services.price_service.alert_service.evaluate_alerts",
        return_value=None,
    ):
        result = await price_service.record_price(product.id, scraped, pg_session)

    count_after_result = await pg_session.execute(
        select(func.count()).where(PriceRecord.product_id == product.id)
    )
    count_after = count_after_result.scalar()

    assert count_after == count_before  # no new row inserted
    assert result.raw_html_hash == "c" * 64


@pytest.mark.asyncio
async def test_record_price_http_error_stored(pg_session) -> None:
    product = await _insert_product(pg_session)

    scraped = _make_scraped_result(
        html_hash="",
        html="",
        price=None,
        currency=None,
        status=ExtractionStatus.HTTP_ERROR,
    )

    record = await price_service.record_price(product.id, scraped, pg_session)

    assert record.price is None
    assert record.currency is None
    assert record.extraction_status == "http_error"


# ---------------------------------------------------------------------------
# alert_service integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_alerts_threshold_crossed(pg_session) -> None:
    product = await _insert_product(pg_session)

    # Insert a price record
    price_record = PriceRecord(
        product_id=product.id,
        price=Decimal("5.00"),
        currency="GBP",
        raw_html_hash="d" * 64,
        extraction_status="ok",
    )
    pg_session.add(price_record)

    # Insert an alert that should trigger (price < threshold)
    alert = PriceAlert(
        product_id=product.id,
        threshold_price=Decimal("10.00"),
        direction=AlertDirection.below,
        is_active=True,
        notified_at=None,
    )
    pg_session.add(alert)
    await pg_session.flush()

    notify_mock = MagicMock()
    with patch("app.services.alert_service.notifications.notify_alert", notify_mock):
        await alert_service.evaluate_alerts(product.id, pg_session)

    notify_mock.assert_called_once_with(alert.id)
    assert alert.notified_at is not None


@pytest.mark.asyncio
async def test_evaluate_alerts_cooldown_respected(pg_session) -> None:
    product = await _insert_product(pg_session)

    # Insert a price record
    price_record = PriceRecord(
        product_id=product.id,
        price=Decimal("5.00"),
        currency="GBP",
        raw_html_hash="e" * 64,
        extraction_status="ok",
    )
    pg_session.add(price_record)

    # Alert notified 10 minutes ago (within cooldown)
    recent = datetime.now(tz=UTC) - timedelta(minutes=10)
    alert = PriceAlert(
        product_id=product.id,
        threshold_price=Decimal("10.00"),
        direction=AlertDirection.below,
        is_active=True,
        notified_at=recent,
    )
    pg_session.add(alert)
    await pg_session.flush()

    notify_mock = MagicMock()
    with patch("app.services.alert_service.notifications.notify_alert", notify_mock):
        await alert_service.evaluate_alerts(product.id, pg_session)

    notify_mock.assert_not_called()
