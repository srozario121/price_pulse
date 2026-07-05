"""Alert evaluation service — checks price thresholds and dispatches notifications."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.alert import PriceAlert
from app.models.enums import ExtractionStatus
from app.models.price_history import PriceRecord
from app.services import notifications

logger = structlog.get_logger()


def _is_cooldown_active(
    alert: PriceAlert,
    now: datetime,
    cooldown_delta: timedelta,
) -> bool:
    if alert.notified_at is None:
        return False
    notified_at_aware = (
        alert.notified_at.replace(tzinfo=UTC)
        if alert.notified_at.tzinfo is None
        else alert.notified_at
    )
    return now < notified_at_aware + cooldown_delta


def _threshold_triggered(
    price: Decimal | None,
    threshold_price: Decimal,
    direction: str,
) -> bool:
    if price is None:
        return False
    if direction == "below":
        return price < threshold_price
    if direction == "above":
        return price > threshold_price
    return False


async def evaluate_alerts(product_id: int, session: AsyncSession) -> None:
    """Compare the latest price against all active alerts for *product_id*.

    Skips evaluation if there is no price record or if the latest extraction failed.
    Respects a 24-hour cooldown per alert to avoid notification spam.
    """
    stmt = (
        select(PriceRecord)
        .where(PriceRecord.product_id == product_id)
        .order_by(PriceRecord.captured_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    latest = result.scalar_one_or_none()

    if latest is None:
        logger.warning(
            "alert_evaluation_skipped",
            product_id=product_id,
            extraction_status=None,
            reason="no_price_record",
        )
        return

    if latest.extraction_status != ExtractionStatus.OK:
        logger.warning(
            "alert_evaluation_skipped",
            product_id=product_id,
            extraction_status=latest.extraction_status,
        )
        return

    alerts_stmt = select(PriceAlert).where(
        PriceAlert.product_id == product_id,
        PriceAlert.is_active.is_(True),
    )
    alerts_result = await session.execute(alerts_stmt)
    alerts = alerts_result.scalars().all()

    now = datetime.now(tz=UTC)
    cooldown_delta = timedelta(hours=settings.ALERT_COOLDOWN_HOURS)

    for alert in alerts:
        if _is_cooldown_active(alert, now, cooldown_delta):
            logger.info("alert_cooldown_active", alert_id=alert.id, product_id=product_id)
            continue

        if _threshold_triggered(latest.price, alert.threshold_price, str(alert.direction)):
            alert.notified_at = now
            logger.info(
                "alert_triggered",
                alert_id=alert.id,
                product_id=product_id,
                direction=str(alert.direction),
                price=str(latest.price),
                threshold=str(alert.threshold_price),
            )
            notifications.notify_alert(alert.id)

    await session.flush()
