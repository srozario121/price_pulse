"""Notification dispatch — wraps the Celery send_notification task.

alert_service.evaluate_alerts() calls notify_alert(alert_id) which
dispatches the Celery task asynchronously.  The function signature is
unchanged from the Item 4 stub so alert_service.py requires no edits.
"""

from __future__ import annotations

import structlog

from app.tasks.notify import send_notification

logger = structlog.get_logger()


def notify_alert(alert_id: int) -> None:
    """Enqueue a send_notification Celery task for *alert_id*."""
    send_notification.delay(alert_id)
    logger.info("notify_alert_dispatched", alert_id=alert_id)
