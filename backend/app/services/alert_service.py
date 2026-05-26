"""Alert evaluation service — checks price thresholds and dispatches notifications."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import PriceAlert
from app.models.enums import ExtractionStatus
from app.models.price_history import PriceRecord
from app.services import notifications

logger = structlog.get_logger()

_ALERT_COOLDOWN_HOURS = 24  # promoted to settings in Item 5


async def evaluate_alerts(product_id: int, session: AsyncSession) -> None:
    """Compare the latest price against all active alerts for *product_id*.

    Skips evaluation if there is no price record or if the latest extraction failed.
    Respects a 24-hour cooldown per alert to avoid notification spam.
    """
    # Fetch latest price record
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

    # Fetch all active alerts for this product
    alerts_stmt = select(PriceAlert).where(
        PriceAlert.product_id == product_id,
        PriceAlert.is_active.is_(True),
    )
    alerts_result = await session.execute(alerts_stmt)
    alerts = alerts_result.scalars().all()

    now = datetime.now(tz=UTC)
    cooldown_delta = timedelta(hours=_ALERT_COOLDOWN_HOURS)

    for alert in alerts:
        # 24h cooldown check
        if alert.notified_at is not None:
            notified_at_aware = (
                alert.notified_at.replace(tzinfo=UTC)
                if alert.notified_at.tzinfo is None
                else alert.notified_at
            )
            if now < notified_at_aware + cooldown_delta:
                logger.info(
                    "alert_cooldown_active",
                    alert_id=alert.id,
                    product_id=product_id,
                )
                continue

        # Direction-based threshold check
        price = latest.price
        triggered = False

        if alert.direction == "below" and price is not None and price < alert.threshold_price:
            triggered = True
        elif alert.direction == "above" and price is not None and price > alert.threshold_price:
            triggered = True

        if triggered:
            alert.notified_at = now
            logger.info(
                "alert_triggered",
                alert_id=alert.id,
                product_id=product_id,
                direction=str(alert.direction),
                price=str(price),
                threshold=str(alert.threshold_price),
            )
            notifications.notify_alert(alert.id)

    await session.flush()
