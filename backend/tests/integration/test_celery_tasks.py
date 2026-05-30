"""Integration tests for Celery tasks (scrape_product, send_notification).

Uses the Postgres testcontainer via pg_session fixture.
Celery tasks are executed *eagerly* (CELERY_TASK_ALWAYS_EAGER=True equivalent)
by calling the underlying async functions directly, bypassing broker/worker.

This avoids spinning up a Redis broker in CI while still exercising the full
DB path: task → service layer → ORM → Postgres testcontainer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.alert import AlertDirection, PriceAlert
from app.models.enums import ExtractionStatus
from app.models.notification_log import NotificationChannel, NotificationLog, NotificationStatus
from app.models.price_history import PriceRecord
from app.models.product import Product


@pytest_asyncio.fixture()
async def pg_session_factory(pg_engine) -> async_sessionmaker:  # type: ignore[type-arg]
    """Return a session factory backed by the Postgres testcontainer."""
    return async_sessionmaker(
        bind=pg_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def _create_product(session: AsyncSession, source_type: str = "generic") -> Product:
    product = Product(
        name="Test Widget",
        url="https://example.com/widget",
        source_type=source_type,
        css_selector=".price",
        is_active=True,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def _create_alert(
    session: AsyncSession,
    product_id: int,
    channel: str = "email",
    webhook_url: str | None = None,
    whatsapp_number: str | None = None,
    threshold_price: Decimal = Decimal("10.00"),
    direction: str = "below",
) -> PriceAlert:
    alert = PriceAlert(
        product_id=product_id,
        threshold_price=threshold_price,
        direction=AlertDirection(direction),
        is_active=True,
        channel=channel,
        webhook_url=webhook_url,
        whatsapp_number=whatsapp_number,
    )
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    return alert


async def _create_price_record(
    session: AsyncSession,
    product_id: int,
    price: Decimal | None = Decimal("7.99"),
    extraction_status: str = "ok",
) -> PriceRecord:
    record = PriceRecord(
        product_id=product_id,
        price=price,
        currency="GBP",
        raw_html_hash="hash_" + str(price),
        extraction_status=extraction_status,
        captured_at=datetime.now(tz=UTC),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


# ─────────────────────────────────────────────────────────────────────────────
# scrape_product integration
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scrape_product_creates_price_record(pg_engine, pg_session_factory) -> None:
    """scrape_product call creates PriceRecord row in Postgres."""
    from app.schemas.scraper import ScrapedResult

    factory = pg_session_factory

    # Arrange
    async with factory() as session:
        product = await _create_product(session)
        product_id = product.id

    # Build a deterministic ScrapedResult
    scraped = ScrapedResult(
        url=product.url,
        html="<html><span class='price'>£9.99</span></html>",
        html_hash="deadbeef" * 8,  # 64 chars
        price=Decimal("9.99"),
        currency="GBP",
        scraped_at=datetime.now(tz=UTC),
        extraction_status=ExtractionStatus.OK,
    )

    scraper_mock = AsyncMock()
    scraper_mock.fetch = AsyncMock(return_value=scraped)

    # Patch AsyncSessionLocal to use the testcontainer session factory
    session_ctx = factory()

    with (
        patch("app.tasks.scrape.AsyncSessionLocal", return_value=session_ctx),
        patch("app.tasks.scrape.get_scraper", return_value=scraper_mock),
    ):
        from app.tasks.scrape import scrape_product

        result = await scrape_product(product_id=product_id)

    assert result == "ok"

    # Verify row in DB
    async with factory() as session:
        stmt = select(PriceRecord).where(PriceRecord.product_id == product_id)
        rows = (await session.execute(stmt)).scalars().all()

    assert len(rows) == 1
    assert rows[0].price == Decimal("9.99")
    assert rows[0].extraction_status == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# send_notification integration
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.integration
async def test_send_notification_email_creates_log(pg_engine, pg_session_factory) -> None:
    """Email channel: NotificationLog row created with status='sent'."""
    factory = pg_session_factory

    async with factory() as session:
        product = await _create_product(session)
        await _create_price_record(session, product.id)
        alert = await _create_alert(session, product.id, channel="email")
        alert_id = alert.id

    session_ctx = factory()

    with patch("app.tasks.notify.AsyncSessionLocal", return_value=session_ctx):
        from app.tasks.notify import send_notification

        await send_notification(alert_id=alert_id)

    async with factory() as session:
        result = await session.execute(
            select(NotificationLog).where(NotificationLog.alert_id == alert_id)
        )
        logs = result.scalars().all()

    assert len(logs) == 1
    assert logs[0].status == NotificationStatus.sent
    assert logs[0].channel == NotificationChannel.email


@pytest.mark.asyncio
@pytest.mark.integration
async def test_send_notification_webhook_unreachable_creates_failed_log(
    pg_engine, pg_session_factory
) -> None:
    """Webhook pointing at unreachable URL: NotificationLog status='failed'."""
    import httpx

    factory = pg_session_factory

    async with factory() as session:
        product = await _create_product(session)
        await _create_price_record(session, product.id)
        alert = await _create_alert(
            session,
            product.id,
            channel="webhook",
            webhook_url="https://webhook.unreachable.invalid/hook",
        )
        alert_id = alert.id

    session_ctx = factory()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("unreachable"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.tasks.notify.AsyncSessionLocal", return_value=session_ctx),
        patch("app.tasks.notify.httpx.AsyncClient", return_value=mock_client),
    ):
        from app.tasks.notify import send_notification

        # Webhook error → sets status='failed' without re-raising
        await send_notification(alert_id=alert_id)

    async with factory() as session:
        result = await session.execute(
            select(NotificationLog).where(NotificationLog.alert_id == alert_id)
        )
        logs = result.scalars().all()

    assert len(logs) == 1
    assert logs[0].status == NotificationStatus.failed


@pytest.mark.asyncio
@pytest.mark.integration
async def test_send_notification_whatsapp_creates_sent_log(
    pg_engine, pg_session_factory
) -> None:
    """WhatsApp stub: NotificationLog status='sent', no external HTTP call."""

    factory = pg_session_factory

    async with factory() as session:
        product = await _create_product(session)
        await _create_price_record(session, product.id)
        alert = await _create_alert(
            session,
            product.id,
            channel="whatsapp",
            whatsapp_number="+447911123456",
        )
        alert_id = alert.id

    session_ctx = factory()

    with (
        patch("app.tasks.notify.AsyncSessionLocal", return_value=session_ctx),
        patch("app.tasks.notify.httpx") as httpx_mock,
    ):
        from app.tasks.notify import send_notification

        await send_notification(alert_id=alert_id)

    httpx_mock.AsyncClient.assert_not_called()

    async with factory() as session:
        result = await session.execute(
            select(NotificationLog).where(NotificationLog.alert_id == alert_id)
        )
        logs = result.scalars().all()

    assert len(logs) == 1
    assert logs[0].status == NotificationStatus.sent
    assert logs[0].channel == NotificationChannel.whatsapp
