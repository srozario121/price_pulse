"""Unit tests for alert_service.evaluate_alerts."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.enums import ExtractionStatus


def _make_price_record(
    price: Decimal | None = Decimal("5.00"),
    extraction_status: str = "ok",
) -> MagicMock:
    record = MagicMock()
    record.price = price
    record.extraction_status = extraction_status
    return record


def _make_alert(
    alert_id: int = 1,
    direction: str = "below",
    threshold: Decimal = Decimal("10.00"),
    is_active: bool = True,
    notified_at: datetime | None = None,
) -> MagicMock:
    alert = MagicMock()
    alert.id = alert_id
    alert.direction = direction
    alert.threshold_price = threshold
    alert.is_active = is_active
    alert.notified_at = notified_at
    return alert


def _make_session(latest_record: object, alerts: list) -> AsyncMock:
    session = AsyncMock()

    # First execute call → price record
    price_execute = AsyncMock()
    price_execute.scalar_one_or_none = MagicMock(return_value=latest_record)

    # Second execute call → alerts
    alerts_execute = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=alerts)
    alerts_execute.scalars = MagicMock(return_value=scalars_mock)

    session.execute = AsyncMock(side_effect=[price_execute, alerts_execute])
    session.flush = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_alerts_below_triggered() -> None:
    from app.services import alert_service

    record = _make_price_record(price=Decimal("5.00"), extraction_status="ok")
    alert = _make_alert(direction="below", threshold=Decimal("10.00"), notified_at=None)
    session = _make_session(record, [alert])

    notify_mock = MagicMock()
    with patch("app.services.alert_service.notifications.notify_alert", notify_mock):
        await alert_service.evaluate_alerts(1, session)

    notify_mock.assert_called_once_with(alert.id)
    assert alert.notified_at is not None


@pytest.mark.asyncio
async def test_evaluate_alerts_above_triggered() -> None:
    from app.services import alert_service

    record = _make_price_record(price=Decimal("20.00"), extraction_status="ok")
    alert = _make_alert(direction="above", threshold=Decimal("15.00"), notified_at=None)
    session = _make_session(record, [alert])

    notify_mock = MagicMock()
    with patch("app.services.alert_service.notifications.notify_alert", notify_mock):
        await alert_service.evaluate_alerts(1, session)

    notify_mock.assert_called_once_with(alert.id)
    assert alert.notified_at is not None


@pytest.mark.asyncio
async def test_evaluate_alerts_cooldown() -> None:
    """Alert notified 1 hour ago → should NOT re-trigger within 24h cooldown."""
    from app.services import alert_service

    recent_notified = datetime.now(tz=UTC) - timedelta(hours=1)
    record = _make_price_record(price=Decimal("5.00"), extraction_status="ok")
    alert = _make_alert(
        direction="below",
        threshold=Decimal("10.00"),
        notified_at=recent_notified,
    )
    session = _make_session(record, [alert])

    notify_mock = MagicMock()
    with patch("app.services.alert_service.notifications.notify_alert", notify_mock):
        await alert_service.evaluate_alerts(1, session)

    notify_mock.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_alerts_cooldown_expired() -> None:
    """Alert notified 25 hours ago → should re-trigger (cooldown expired)."""
    from app.services import alert_service

    old_notified = datetime.now(tz=UTC) - timedelta(hours=25)
    record = _make_price_record(price=Decimal("5.00"), extraction_status="ok")
    alert = _make_alert(
        direction="below",
        threshold=Decimal("10.00"),
        notified_at=old_notified,
    )
    session = _make_session(record, [alert])

    notify_mock = MagicMock()
    with patch("app.services.alert_service.notifications.notify_alert", notify_mock):
        await alert_service.evaluate_alerts(1, session)

    notify_mock.assert_called_once_with(alert.id)


@pytest.mark.asyncio
async def test_evaluate_alerts_extraction_failed() -> None:
    """extraction_status=extraction_failed → early return, no notification."""
    from app.services import alert_service

    record = _make_price_record(
        price=None, extraction_status=ExtractionStatus.EXTRACTION_FAILED
    )
    price_execute = AsyncMock()
    price_execute.scalar_one_or_none = MagicMock(return_value=record)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=price_execute)
    session.flush = AsyncMock()

    notify_mock = MagicMock()
    with patch("app.services.alert_service.notifications.notify_alert", notify_mock):
        await alert_service.evaluate_alerts(1, session)

    notify_mock.assert_not_called()
    # Only one execute call (no alert query)
    assert session.execute.call_count == 1


@pytest.mark.asyncio
async def test_evaluate_alerts_no_record() -> None:
    """No PriceRecord found → early return."""
    from app.services import alert_service

    price_execute = AsyncMock()
    price_execute.scalar_one_or_none = MagicMock(return_value=None)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=price_execute)
    session.flush = AsyncMock()

    notify_mock = MagicMock()
    with patch("app.services.alert_service.notifications.notify_alert", notify_mock):
        await alert_service.evaluate_alerts(1, session)

    notify_mock.assert_not_called()
    assert session.execute.call_count == 1


@pytest.mark.asyncio
async def test_evaluate_alerts_threshold_not_crossed() -> None:
    """Price is above threshold but direction=below → NOT triggered."""
    from app.services import alert_service

    record = _make_price_record(price=Decimal("15.00"), extraction_status="ok")
    alert = _make_alert(direction="below", threshold=Decimal("10.00"), notified_at=None)
    session = _make_session(record, [alert])

    notify_mock = MagicMock()
    with patch("app.services.alert_service.notifications.notify_alert", notify_mock):
        await alert_service.evaluate_alerts(1, session)

    notify_mock.assert_not_called()
    assert alert.notified_at is None


@pytest.mark.asyncio
async def test_evaluate_alerts_http_error_skipped() -> None:
    """extraction_status=http_error → early return."""
    from app.services import alert_service

    record = _make_price_record(price=None, extraction_status=ExtractionStatus.HTTP_ERROR)
    price_execute = AsyncMock()
    price_execute.scalar_one_or_none = MagicMock(return_value=record)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=price_execute)
    session.flush = AsyncMock()

    notify_mock = MagicMock()
    with patch("app.services.alert_service.notifications.notify_alert", notify_mock):
        await alert_service.evaluate_alerts(1, session)

    notify_mock.assert_not_called()
