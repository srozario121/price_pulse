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


# ── Per-channel delivery helpers ──────────────────────────────────────────────


async def _deliver_email(
    log: NotificationLog,
    alert_id: int,
    payload: dict[str, object],
) -> None:
    logger.info("email_stub", alert_id=alert_id, payload=payload)
    log.status = NotificationStatus.sent


async def _deliver_whatsapp(
    log: NotificationLog,
    alert_id: int,
    whatsapp_number: str | None,
) -> None:
    if not whatsapp_number:
        logger.error("send_notification_whatsapp_number_missing", alert_id=alert_id)
        log.status = NotificationStatus.failed
        return
    logger.warning("whatsapp_stub", alert_id=alert_id, whatsapp_number=whatsapp_number)
    log.status = NotificationStatus.sent


async def _deliver_webhook(
    task: object,
    session: object,
    log: NotificationLog,
    alert_id: int,
    payload: dict[str, object],
    webhook_url: str | None,
) -> None:
    if not webhook_url:
        logger.error("send_notification_webhook_url_missing", alert_id=alert_id)
        log.status = NotificationStatus.failed
        return
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=payload, timeout=10.0)
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
        log.status = NotificationStatus.failed
        logger.warning("webhook_delivery_timeout", alert_id=alert_id, url=webhook_url)
        await session.commit()  # type: ignore[attr-defined]
        raise task.retry(exc=exc, countdown=5) from exc  # type: ignore[attr-defined]
    except httpx.HTTPError as exc:
        log.status = NotificationStatus.failed
        logger.error(
            "webhook_delivery_error", alert_id=alert_id, url=webhook_url, exc=str(exc)
        )


async def _dispatch_channel(
    task: object,
    session: object,
    log: NotificationLog,
    alert_id: int,
    payload: dict[str, object],
    channel: NotificationChannel,
    alert: PriceAlert,
) -> None:
    if channel == NotificationChannel.email:
        await _deliver_email(log, alert_id, payload)
    elif channel == NotificationChannel.webhook:
        await _deliver_webhook(task, session, log, alert_id, payload, alert.webhook_url)
    elif channel == NotificationChannel.whatsapp:
        await _deliver_whatsapp(log, alert_id, alert.whatsapp_number)
    else:
        logger.error(
            "send_notification_unknown_channel", alert_id=alert_id, channel=str(channel)
        )
        log.status = NotificationStatus.failed


async def _mark_pending_log_failed(alert_id: int) -> None:
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


async def _handle_task_failure(
    task: object,
    alert_id: int,
    exc: Exception,
) -> None:
    retry_exc_type = getattr(task, "MaxRetriesExceededError", None)
    if retry_exc_type and isinstance(exc, retry_exc_type):
        raise exc
    logger.warning("send_notification_retry", alert_id=alert_id, exc=str(exc))
    try:
        raise task.retry(exc=exc, countdown=5)  # type: ignore[attr-defined]
    except Exception as max_exc:
        if retry_exc_type and isinstance(max_exc, retry_exc_type):
            await _mark_pending_log_failed(alert_id)
            logger.error(
                "send_notification_max_retries_exceeded",
                alert_id=alert_id,
                exc=str(exc),
                exc_info=True,
            )
        raise


# ── Celery task ───────────────────────────────────────────────────────────────


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="app.tasks.notify.send_notification",
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
)
async def send_notification(self: object, alert_id: int) -> None:
    """Deliver a notification for the triggered *alert_id*."""
    try:
        async with AsyncSessionLocal() as session:
            alert_result = await session.execute(
                select(PriceAlert).where(PriceAlert.id == alert_id)
            )
            alert = alert_result.scalar_one_or_none()
            if alert is None:
                logger.warning("send_notification_alert_not_found", alert_id=alert_id)
                return

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

            price_result = await session.execute(
                select(PriceRecord)
                .where(PriceRecord.product_id == alert.product_id)
                .order_by(PriceRecord.captured_at.desc())
                .limit(1)
            )
            latest_price = price_result.scalar_one_or_none()

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

            channel = NotificationChannel(alert.channel)
            log = NotificationLog(
                alert_id=alert_id,
                channel=channel,
                payload=payload,
                status=NotificationStatus.pending,
            )
            session.add(log)
            await session.flush()

            await _dispatch_channel(self, session, log, alert_id, payload, channel, alert)
            await session.commit()

    except Exception as exc:
        await _handle_task_failure(self, alert_id, exc)
