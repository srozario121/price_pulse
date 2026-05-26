"""Celery task: send_notification — deliver an alert notification.

Design decisions:
- bind=True: gives access to self.retry() and self.request.retries.
- Retry policy: max_retries=3, default_retry_delay=5 s.
- On max-retries exhaustion: NotificationLog.status set to 'failed',
  structlog ERROR emitted, exception re-raised.
- channel='email': structlog INFO stub (no SMTP in item 5; SMTP deferred
  to the auth/user item).
- channel='webhook': real httpx.AsyncClient POST; 'sent' on 2xx, 'failed'
  on any error; retried on TimeoutException.
- channel='whatsapp': structlog WARNING stub; status='sent' (real delivery
  implemented in follow-on item after WhatsApp provider ADR is approved).
- If webhook_url=None when channel='webhook', or whatsapp_number=None when
  channel='whatsapp', status is set to 'failed' without retrying.
"""

from __future__ import annotations

import httpx
import structlog
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.alert import PriceAlert
from app.models.notification_log import NotificationChannel, NotificationLog, NotificationStatus
from app.models.price_history import PriceRecord
from app.models.product import Product
from app.workers.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(
    bind=True,
    name="app.tasks.notify.send_notification",
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
)
async def send_notification(self: object, alert_id: int) -> None:  # type: ignore[misc]
    """Deliver a notification for the triggered *alert_id*.

    Creates a NotificationLog row and updates its status based on the
    delivery outcome.  Retries up to 3 times on transient errors.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Fetch alert
            alert_result = await session.execute(
                select(PriceAlert).where(PriceAlert.id == alert_id)
            )
            alert = alert_result.scalar_one_or_none()

            if alert is None:
                logger.warning("send_notification_alert_not_found", alert_id=alert_id)
                return

            # Fetch product
            product_result = await session.execute(
                select(Product).where(Product.id == alert.product_id)
            )
            product = product_result.scalar_one_or_none()

            if product is None:
                logger.warning(
                    "send_notification_product_not_found",
                    alert_id=alert_id,
                    product_id=alert.product_id,
                )
                return

            # Fetch latest price record
            price_result = await session.execute(
                select(PriceRecord)
                .where(PriceRecord.product_id == alert.product_id)
                .order_by(PriceRecord.captured_at.desc())
                .limit(1)
            )
            latest_price = price_result.scalar_one_or_none()

            # Build payload
            payload: dict[str, object] = {
                "product_id": product.id,
                "product_name": product.name,
                "product_url": product.url,
                "current_price": (
                    str(latest_price.price)
                    if latest_price and latest_price.price is not None
                    else None
                ),
                "threshold_price": str(alert.threshold_price),
                "direction": str(alert.direction),
            }

            # Create NotificationLog in pending state
            channel = NotificationChannel(alert.channel)
            log = NotificationLog(
                alert_id=alert_id,
                channel=channel,
                payload=payload,
                status=NotificationStatus.pending,
            )
            session.add(log)
            await session.flush()  # get log.id without committing

            # Dispatch based on channel
            if channel == NotificationChannel.email:
                logger.info(
                    "email_stub",
                    alert_id=alert_id,
                    payload=payload,
                )
                log.status = NotificationStatus.sent

            elif channel == NotificationChannel.webhook:
                webhook_url = alert.webhook_url
                if not webhook_url:
                    logger.error(
                        "send_notification_webhook_url_missing",
                        alert_id=alert_id,
                    )
                    log.status = NotificationStatus.failed
                else:
                    try:
                        async with httpx.AsyncClient() as client:
                            response = await client.post(
                                webhook_url,
                                json=payload,
                                timeout=10.0,
                            )
                        if response.is_success:
                            log.status = NotificationStatus.sent
                            logger.info(
                                "webhook_delivered",
                                alert_id=alert_id,
                                url=webhook_url,
                                status_code=response.status_code,
                            )
                        else:
                            log.status = NotificationStatus.failed
                            logger.warning(
                                "webhook_delivery_failed",
                                alert_id=alert_id,
                                url=webhook_url,
                                status_code=response.status_code,
                            )
                    except httpx.TimeoutException as exc:
                        # Transient timeout: eligible for retry
                        log.status = NotificationStatus.failed
                        logger.warning(
                            "webhook_delivery_timeout",
                            alert_id=alert_id,
                            url=webhook_url,
                        )
                        await session.commit()
                        raise self.retry(exc=exc, countdown=5)  # type: ignore[attr-defined]
                    except httpx.HTTPError as exc:
                        # Connection error, DNS failure, etc.: fail immediately, no retry
                        log.status = NotificationStatus.failed
                        logger.error(
                            "webhook_delivery_error",
                            alert_id=alert_id,
                            url=webhook_url,
                            exc=str(exc),
                        )

            elif channel == NotificationChannel.whatsapp:
                whatsapp_number = alert.whatsapp_number
                if not whatsapp_number:
                    logger.error(
                        "send_notification_whatsapp_number_missing",
                        alert_id=alert_id,
                    )
                    log.status = NotificationStatus.failed
                else:
                    logger.warning(
                        "whatsapp_stub",
                        alert_id=alert_id,
                        whatsapp_number=whatsapp_number,
                    )
                    log.status = NotificationStatus.sent

            else:
                logger.error(
                    "send_notification_unknown_channel",
                    alert_id=alert_id,
                    channel=str(channel),
                )
                log.status = NotificationStatus.failed

            await session.commit()

    except Exception as exc:
        # Avoid double-wrapping retry exceptions
        retry_exc_type = getattr(self, "MaxRetriesExceededError", None)
        if retry_exc_type and isinstance(exc, retry_exc_type):
            raise

        logger.warning(
            "send_notification_retry",
            alert_id=alert_id,
            exc=str(exc),
        )
        try:
            raise self.retry(exc=exc, countdown=5)  # type: ignore[attr-defined]
        except Exception as max_exc:
            if retry_exc_type and isinstance(max_exc, retry_exc_type):
                # Best-effort: mark any pending log as failed
                try:
                    async with AsyncSessionLocal() as session:
                        result = await session.execute(
                            select(NotificationLog)
                            .where(
                                NotificationLog.alert_id == alert_id,
                                NotificationLog.status == NotificationStatus.pending,
                            )
                            .order_by(NotificationLog.sent_at.desc())
                            .limit(1)
                        )
                        pending_log = result.scalar_one_or_none()
                        if pending_log:
                            pending_log.status = NotificationStatus.failed
                            await session.commit()
                except Exception:
                    pass  # best-effort; original error already logged

                logger.error(
                    "send_notification_max_retries_exceeded",
                    alert_id=alert_id,
                    exc=str(exc),
                    exc_info=True,
                )
            raise
