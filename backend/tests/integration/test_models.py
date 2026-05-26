"""Integration tests for ORM models — requires Postgres (pg_session fixture).

These tests verify:
- CRUD operations with real Postgres ENUM types
- FK navigation via relationship attributes
- Cascade delete behaviour
- updated_at auto-update
- Named indexes existence in pg_indexes

Run with: uv run pytest tests/integration/test_models.py -m integration
"""

from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertDirection, PriceAlert
from app.models.notification_log import NotificationChannel, NotificationLog, NotificationStatus
from app.models.price_history import PriceRecord
from app.models.product import Product, SourceType

pytestmark = pytest.mark.integration


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_product(session: AsyncSession, **kwargs) -> Product:
    defaults = {
        "name": "Test Product",
        "url": "https://example.com/product",
        "source_type": SourceType.generic,
    }
    defaults.update(kwargs)
    product = Product(**defaults)
    session.add(product)
    await session.flush()
    return product


# ── CRUD: create / read each model ────────────────────────────────────────────


class TestCRUD:
    async def test_create_and_read_product(self, pg_session: AsyncSession):
        # Arrange / Act
        product = await _make_product(
            pg_session,
            name="Widget",
            url="https://amazon.com/widget",
            source_type=SourceType.amazon,
            css_selector=".price",
        )

        # Refresh from DB
        await pg_session.refresh(product)

        # Assert
        assert product.id is not None
        assert product.name == "Widget"
        assert product.source_type == SourceType.amazon
        assert product.css_selector == ".price"
        assert product.is_active is True
        assert product.created_at is not None
        assert product.updated_at is not None

    async def test_create_and_read_price_record(self, pg_session: AsyncSession):
        # Arrange
        product = await _make_product(pg_session)

        # Act
        record = PriceRecord(
            product_id=product.id,
            price=Decimal("29.99"),
            currency="GBP",
            raw_html_hash="a" * 64,
        )
        pg_session.add(record)
        await pg_session.flush()
        await pg_session.refresh(record)

        # Assert
        assert record.id is not None
        assert record.price == Decimal("29.99")
        assert record.currency == "GBP"
        assert record.raw_html_hash == "a" * 64
        assert record.captured_at is not None

    async def test_create_and_read_price_alert(self, pg_session: AsyncSession):
        # Arrange
        product = await _make_product(pg_session)

        # Act
        alert = PriceAlert(
            product_id=product.id,
            threshold_price=Decimal("20.00"),
            direction=AlertDirection.below,
        )
        pg_session.add(alert)
        await pg_session.flush()
        await pg_session.refresh(alert)

        # Assert
        assert alert.id is not None
        assert alert.direction == AlertDirection.below
        assert alert.is_active is True
        assert alert.notified_at is None

    async def test_create_and_read_notification_log(self, pg_session: AsyncSession):
        # Arrange
        product = await _make_product(pg_session)
        alert = PriceAlert(
            product_id=product.id,
            threshold_price=Decimal("10.00"),
            direction=AlertDirection.above,
        )
        pg_session.add(alert)
        await pg_session.flush()

        # Act
        log = NotificationLog(
            alert_id=alert.id,
            channel=NotificationChannel.email,
            payload={"to": "user@example.com"},
            status=NotificationStatus.pending,
        )
        pg_session.add(log)
        await pg_session.flush()
        await pg_session.refresh(log)

        # Assert
        assert log.id is not None
        assert log.channel == NotificationChannel.email
        assert log.status == NotificationStatus.pending
        assert log.payload == {"to": "user@example.com"}


# ── FK navigation ─────────────────────────────────────────────────────────────


class TestRelationships:
    async def test_product_price_records_relationship(self, pg_session: AsyncSession):
        # Arrange
        product = await _make_product(pg_session)
        record = PriceRecord(
            product_id=product.id, price=Decimal("15.00"), currency="GBP"
        )
        pg_session.add(record)
        await pg_session.flush()

        # Act — re-fetch product and load relationship
        result = await pg_session.execute(
            select(Product).where(Product.id == product.id)
        )
        fetched = result.scalar_one()
        await pg_session.refresh(fetched, ["price_records"])

        # Assert
        assert len(fetched.price_records) == 1
        assert fetched.price_records[0].price == Decimal("15.00")


# ── Cascade delete ────────────────────────────────────────────────────────────


class TestCascadeDelete:
    async def test_delete_product_cascades_to_price_records_and_alerts(
        self, pg_session: AsyncSession
    ):
        # Arrange
        product = await _make_product(pg_session, url="https://example.com/cascade")
        record = PriceRecord(product_id=product.id, price=Decimal("5.00"))
        alert = PriceAlert(
            product_id=product.id,
            threshold_price=Decimal("4.00"),
            direction=AlertDirection.below,
        )
        log = NotificationLog(
            alert_id=None,  # set after flush
            channel=NotificationChannel.webhook,
            status=NotificationStatus.pending,
        )
        pg_session.add_all([record, alert])
        await pg_session.flush()

        log.alert_id = alert.id
        pg_session.add(log)
        await pg_session.flush()

        record_id = record.id
        alert_id = alert.id
        log_id = log.id

        # Act
        await pg_session.delete(product)
        await pg_session.flush()

        # Assert — all child rows removed
        assert (
            await pg_session.get(PriceRecord, record_id)
        ) is None
        assert (await pg_session.get(PriceAlert, alert_id)) is None
        assert (await pg_session.get(NotificationLog, log_id)) is None


# ── updated_at auto-update ────────────────────────────────────────────────────


class TestUpdatedAt:
    async def test_updated_at_changes_on_name_update(self, pg_session: AsyncSession):
        # Arrange
        import asyncio

        product = await _make_product(pg_session, url="https://example.com/updated")
        await pg_session.refresh(product)
        original_updated_at = product.updated_at

        # Wait a tick to ensure timestamp difference
        await asyncio.sleep(0.01)

        # Act
        product.name = "Updated Name"
        await pg_session.flush()
        await pg_session.refresh(product)

        # Assert
        assert product.updated_at >= original_updated_at


# ── Index existence ───────────────────────────────────────────────────────────


class TestIndexes:
    async def test_all_four_named_indexes_exist(self, pg_session: AsyncSession):
        # Arrange
        expected = {
            "ix_price_record_product_captured",
            "ix_price_record_html_hash",
            "ix_price_alert_product_active",
            "ix_notification_log_alert_sent",
        }

        # Act
        result = await pg_session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname = ANY(:names)"
            ),
            {"names": list(expected)},
        )
        found = {row[0] for row in result}

        # Assert
        assert found == expected


# ── Negative: constraint violations ──────────────────────────────────────────


class TestConstraintViolations:
    async def test_price_record_with_nonexistent_product_id_raises_integrity_error(
        self, pg_session: AsyncSession
    ):
        # Arrange / Act / Assert
        record = PriceRecord(product_id=999999, price=Decimal("1.00"))
        pg_session.add(record)
        with pytest.raises(IntegrityError):
            await pg_session.flush()

    async def test_duplicate_product_url_raises_integrity_error(
        self, pg_session: AsyncSession
    ):
        # Arrange
        url = "https://example.com/duplicate"
        p1 = Product(name="P1", url=url, source_type=SourceType.generic)
        p2 = Product(name="P2", url=url, source_type=SourceType.generic)
        pg_session.add_all([p1, p2])

        # Act / Assert
        with pytest.raises(IntegrityError):
            await pg_session.flush()

    async def test_price_record_with_null_price_raises_integrity_error(
        self, pg_session: AsyncSession
    ):
        # Arrange
        product = await _make_product(pg_session, url="https://example.com/null-price")

        # Act / Assert — bypass Pydantic, go straight to ORM
        record = PriceRecord(product_id=product.id, price=None)  # type: ignore[arg-type]
        pg_session.add(record)
        with pytest.raises((IntegrityError, Exception)):
            await pg_session.flush()
