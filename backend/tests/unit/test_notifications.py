"""Unit tests for app.services.notifications.notify_alert.

Item 5 replaces the stub with a Celery task dispatch.  These tests verify
that notify_alert calls send_notification.delay(alert_id) and returns None.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_notify_alert_returns_none() -> None:
    """notify_alert returns None (fire-and-forget Celery dispatch)."""
    with patch("app.services.notifications.send_notification") as mock_task:
        mock_task.delay = MagicMock()
        from app.services.notifications import notify_alert

        result = notify_alert(42)

    assert result is None


def test_notify_alert_dispatches_celery_task() -> None:
    """notify_alert calls send_notification.delay(alert_id)."""
    with patch("app.services.notifications.send_notification") as mock_task:
        mock_task.delay = MagicMock()
        from app.services.notifications import notify_alert

        notify_alert(99)

    mock_task.delay.assert_called_once_with(99)


def test_notify_alert_accepts_any_alert_id() -> None:
    """notify_alert dispatches for any integer alert_id without raising."""
    with patch("app.services.notifications.send_notification") as mock_task:
        mock_task.delay = MagicMock()
        from app.services.notifications import notify_alert

        for alert_id in [0, 1, 99, 10_000]:
            notify_alert(alert_id)

    assert mock_task.delay.call_count == 4
