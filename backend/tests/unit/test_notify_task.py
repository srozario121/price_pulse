"""Unit tests for app.tasks.notify.send_notification."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_alert(
    alert_id: int = 1,
    product_id: int = 10,
    channel: str = "email",
    webhook_url: str | None = None,
    whatsapp_number: str | None = None,
    threshold_price: Decimal = Decimal("9.99"),
    direction: str = "below",
) -> MagicMock:
    a = MagicMock()
    a.id = alert_id
    a.product_id = product_id
    a.channel = channel
    a.webhook_url = webhook_url
    a.whatsapp_number = whatsapp_number
    a.threshold_price = threshold_price
    a.direction = direction
    return a


def _make_product(product_id: int = 10) -> MagicMock:
    p = MagicMock()
    p.id = product_id
    p.name = "Cool Widget"
    p.url = "https://example.com/product"
    return p


def _make_price_record(price: Decimal | None = Decimal("7.99")) -> MagicMock:
    r = MagicMock()
    r.price = price
    return r


def _make_session(alert: object, product: object, price_record: object) -> AsyncMock:
    session = AsyncMock()

    alert_exec = AsyncMock()
    alert_exec.scalar_one_or_none = MagicMock(return_value=alert)

    product_exec = AsyncMock()
    product_exec.scalar_one_or_none = MagicMock(return_value=product)

    price_exec = AsyncMock()
    price_exec.scalar_one_or_none = MagicMock(return_value=price_record)

    session.execute = AsyncMock(side_effect=[alert_exec, product_exec, price_exec])
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_send_notification_email_stub() -> None:
    """Email channel: structlog INFO emitted, NotificationLog status='sent'."""
    from app.tasks.notify import send_notification

    alert = _make_alert(channel="email")
    product = _make_product()
    price = _make_price_record()
    session = _make_session(alert, product, price)

    captured_logs: list[dict] = []

    def fake_log(**kwargs: object) -> None:
        captured_logs.append(kwargs)

    with patch("app.tasks.notify.AsyncSessionLocal", return_value=session):
        with patch("app.tasks.notify.logger") as log_mock:
            log_mock.info = MagicMock(side_effect=lambda event, **kw: captured_logs.append({"event": event, **kw}))
            log_mock.warning = MagicMock()
            log_mock.error = MagicMock()
            await send_notification(alert_id=1)

    # Check that NotificationLog was added to session
    assert session.add.called
    log_instance = session.add.call_args[0][0]
    # The status should have been set to 'sent'
    from app.models.notification_log import NotificationStatus
    assert log_instance.status == NotificationStatus.sent

    # Check that an email_stub event was logged
    email_events = [e for e in captured_logs if e.get("event") == "email_stub"]
    assert len(email_events) == 1


@pytest.mark.asyncio
async def test_send_notification_webhook_success() -> None:
    """Webhook channel: httpx.post called, status='sent' on 2xx."""

    from app.tasks.notify import send_notification

    alert = _make_alert(channel="webhook", webhook_url="https://hooks.example.com/price")
    product = _make_product()
    price = _make_price_record()
    session = _make_session(alert, product, price)

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.tasks.notify.AsyncSessionLocal", return_value=session),
        patch("app.tasks.notify.httpx.AsyncClient", return_value=mock_client),
    ):
        await send_notification(alert_id=1)

    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "https://hooks.example.com/price"

    from app.models.notification_log import NotificationStatus
    log_instance = session.add.call_args[0][0]
    assert log_instance.status == NotificationStatus.sent


@pytest.mark.asyncio
async def test_send_notification_webhook_missing_url() -> None:
    """Webhook channel with no webhook_url: status='failed', no HTTP call."""
    from app.tasks.notify import send_notification

    alert = _make_alert(channel="webhook", webhook_url=None)
    product = _make_product()
    price = _make_price_record()
    session = _make_session(alert, product, price)

    with (
        patch("app.tasks.notify.AsyncSessionLocal", return_value=session),
        patch("app.tasks.notify.httpx") as httpx_mock,
    ):
        await send_notification(alert_id=1)

    # No HTTP call should be made
    httpx_mock.AsyncClient.assert_not_called()

    from app.models.notification_log import NotificationStatus
    log_instance = session.add.call_args[0][0]
    assert log_instance.status == NotificationStatus.failed


@pytest.mark.asyncio
async def test_send_notification_whatsapp_stub() -> None:
    """WhatsApp channel: WARNING logged, status='sent', no external HTTP call."""
    from app.tasks.notify import send_notification

    alert = _make_alert(channel="whatsapp", whatsapp_number="+447911123456")
    product = _make_product()
    price = _make_price_record()
    session = _make_session(alert, product, price)

    warning_events: list[dict] = []

    with (
        patch("app.tasks.notify.AsyncSessionLocal", return_value=session),
        patch("app.tasks.notify.httpx") as httpx_mock,
        patch("app.tasks.notify.logger") as log_mock,
    ):
        log_mock.info = MagicMock()
        log_mock.warning = MagicMock(
            side_effect=lambda event, **kw: warning_events.append({"event": event, **kw})
        )
        log_mock.error = MagicMock()
        await send_notification(alert_id=1)

    httpx_mock.AsyncClient.assert_not_called()

    from app.models.notification_log import NotificationStatus
    log_instance = session.add.call_args[0][0]
    assert log_instance.status == NotificationStatus.sent

    wa_events = [e for e in warning_events if e.get("event") == "whatsapp_stub"]
    assert len(wa_events) == 1
    assert wa_events[0]["whatsapp_number"] == "+447911123456"


@pytest.mark.asyncio
async def test_send_notification_whatsapp_missing_number() -> None:
    """WhatsApp with no whatsapp_number: status='failed'."""
    from app.tasks.notify import send_notification

    alert = _make_alert(channel="whatsapp", whatsapp_number=None)
    product = _make_product()
    price = _make_price_record()
    session = _make_session(alert, product, price)

    with patch("app.tasks.notify.AsyncSessionLocal", return_value=session):
        await send_notification(alert_id=1)

    from app.models.notification_log import NotificationStatus
    log_instance = session.add.call_args[0][0]
    assert log_instance.status == NotificationStatus.failed


@pytest.mark.asyncio
async def test_send_notification_alert_not_found() -> None:
    """Non-existent alert_id: returns None, no log created."""
    from app.tasks.notify import send_notification

    session = AsyncMock()
    not_found_exec = AsyncMock()
    not_found_exec.scalar_one_or_none = MagicMock(return_value=None)
    session.execute = AsyncMock(return_value=not_found_exec)
    session.add = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.tasks.notify.AsyncSessionLocal", return_value=session):
        await send_notification(alert_id=9999)

    session.add.assert_not_called()


def test_alert_cooldown_reads_from_settings() -> None:
    """alert_service.py uses settings.ALERT_COOLDOWN_HOURS, not a hardcoded constant."""
    import ast
    import pathlib

    # Resolve path relative to this test file (tests/unit/ → app/services/)
    service_path = (
        pathlib.Path(__file__).parent.parent.parent
        / "app"
        / "services"
        / "alert_service.py"
    )
    src = service_path.read_text()
    tree = ast.parse(src)

    # Verify no hardcoded _ALERT_COOLDOWN_HOURS constant in the module
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_ALERT_COOLDOWN_HOURS":
                    pytest.fail(
                        "_ALERT_COOLDOWN_HOURS constant still present; should use settings.ALERT_COOLDOWN_HOURS"
                    )
