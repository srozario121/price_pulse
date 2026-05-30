"""Unit tests for the notify.py helper functions introduced in the CC refactor."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_log() -> MagicMock:
    log = MagicMock()
    from app.models.notification_log import NotificationStatus
    log.status = NotificationStatus.pending
    return log


class TestDeliverWebhook:
    @pytest.mark.asyncio
    async def test_non_success_response_sets_failed(self) -> None:
        from app.models.notification_log import NotificationStatus
        from app.tasks.notify import _deliver_webhook

        log = _make_log()
        mock_resp = MagicMock()
        mock_resp.is_success = False
        mock_resp.status_code = 400
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.tasks.notify.httpx.AsyncClient", return_value=mock_client):
            await _deliver_webhook(
                MagicMock(), MagicMock(), log, 1, {}, "https://hooks.example.com"
            )

        assert log.status == NotificationStatus.failed

    @pytest.mark.asyncio
    async def test_timeout_exception_commits_and_retries(self) -> None:
        import httpx

        from app.models.notification_log import NotificationStatus
        from app.tasks.notify import _deliver_webhook

        log = _make_log()
        session = AsyncMock()
        task = MagicMock()
        task.retry = MagicMock(side_effect=RuntimeError("retry triggered"))

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.tasks.notify.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="retry triggered"):
                await _deliver_webhook(task, session, log, 1, {}, "https://hooks.example.com")

        assert log.status == NotificationStatus.failed
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_error_sets_failed_no_retry(self) -> None:
        import httpx

        from app.models.notification_log import NotificationStatus
        from app.tasks.notify import _deliver_webhook

        log = _make_log()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPError("connection refused")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        task = MagicMock()
        with patch("app.tasks.notify.httpx.AsyncClient", return_value=mock_client):
            await _deliver_webhook(task, MagicMock(), log, 1, {}, "https://hooks.example.com")

        assert log.status == NotificationStatus.failed
        task.retry.assert_not_called()


class TestDispatchChannel:
    @pytest.mark.asyncio
    async def test_unknown_channel_sets_failed(self) -> None:
        from app.models.notification_log import NotificationChannel, NotificationStatus
        from app.tasks.notify import _dispatch_channel

        log = _make_log()

        # Craft a channel value that doesn't match any known enum member
        unknown = MagicMock(spec=NotificationChannel)
        unknown.__eq__ = lambda self, other: False

        alert = MagicMock()
        await _dispatch_channel(
            MagicMock(), MagicMock(), log, 1, {}, unknown, alert
        )
        assert log.status == NotificationStatus.failed


class TestMarkPendingLogFailed:
    @pytest.mark.asyncio
    async def test_marks_pending_log_as_failed(self) -> None:
        from app.models.notification_log import NotificationStatus
        from app.tasks.notify import _mark_pending_log_failed

        pending_log = MagicMock()
        pending_log.status = NotificationStatus.pending

        exec_result = AsyncMock()
        exec_result.scalar_one_or_none = MagicMock(return_value=pending_log)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=exec_result)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.tasks.notify.AsyncSessionLocal", return_value=session):
            await _mark_pending_log_failed(alert_id=1)

        assert pending_log.status == NotificationStatus.failed
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_pending_log_is_noop(self) -> None:
        from app.tasks.notify import _mark_pending_log_failed

        exec_result = AsyncMock()
        exec_result.scalar_one_or_none = MagicMock(return_value=None)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=exec_result)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.tasks.notify.AsyncSessionLocal", return_value=session):
            await _mark_pending_log_failed(alert_id=1)

        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_exception_is_silent(self) -> None:
        from app.tasks.notify import _mark_pending_log_failed

        session = AsyncMock()
        session.__aenter__ = AsyncMock(side_effect=Exception("db down"))
        session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.tasks.notify.AsyncSessionLocal", return_value=session):
            # Should not raise
            await _mark_pending_log_failed(alert_id=1)


class TestHandleTaskFailure:
    @pytest.mark.asyncio
    async def test_raises_if_already_max_retries(self) -> None:
        from app.tasks.notify import _handle_task_failure

        class FakeMaxRetries(Exception):
            pass

        task = MagicMock()
        task.MaxRetriesExceededError = FakeMaxRetries
        exc = FakeMaxRetries("max retries")

        with pytest.raises(FakeMaxRetries):
            await _handle_task_failure(task, 1, exc)

    @pytest.mark.asyncio
    async def test_retries_and_raises_on_max_exceeded(self) -> None:
        from app.tasks.notify import _handle_task_failure

        class FakeMaxRetries(Exception):
            pass

        task = MagicMock()
        task.MaxRetriesExceededError = FakeMaxRetries
        max_exc = FakeMaxRetries("max retries")
        task.retry = MagicMock(side_effect=max_exc)

        with (
            patch("app.tasks.notify._mark_pending_log_failed", new=AsyncMock()),
            pytest.raises(FakeMaxRetries),
        ):
            await _handle_task_failure(task, 1, ValueError("original error"))

    @pytest.mark.asyncio
    async def test_retries_and_raises_other_exception(self) -> None:
        from app.tasks.notify import _handle_task_failure

        class FakeMaxRetries(Exception):
            pass

        other_exc = RuntimeError("other error")
        task = MagicMock()
        task.MaxRetriesExceededError = FakeMaxRetries
        task.retry = MagicMock(side_effect=other_exc)

        with pytest.raises(RuntimeError):
            await _handle_task_failure(task, 1, ValueError("original"))


class TestSendNotificationProductNotFound:
    @pytest.mark.asyncio
    async def test_product_not_found_returns_early(self) -> None:
        from app.tasks.notify import send_notification

        alert_mock = MagicMock()
        alert_mock.product_id = 99
        alert_mock.channel = "email"

        alert_exec = AsyncMock()
        alert_exec.scalar_one_or_none = MagicMock(return_value=alert_mock)
        product_exec = AsyncMock()
        product_exec.scalar_one_or_none = MagicMock(return_value=None)

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[alert_exec, product_exec])
        session.add = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.tasks.notify.AsyncSessionLocal", return_value=session):
            await send_notification(alert_id=1)

        session.add.assert_not_called()
