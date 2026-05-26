"""Notification dispatch stub — replaced by Celery task in Item 5."""
from __future__ import annotations

import structlog

logger = structlog.get_logger()


def notify_alert(alert_id: int) -> None:
    """Stub — Item 5 replaces with send_notification.delay(alert_id)."""
    logger.info("notify_alert_stub", alert_id=alert_id)
