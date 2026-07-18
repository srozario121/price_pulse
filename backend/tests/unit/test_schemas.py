"""Unit tests for Pydantic schemas — no database required (SQLite-compatible)."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.alert import AlertDirection
from app.models.notification_log import NotificationChannel, NotificationStatus
from app.schemas.alert import AlertCreate, AlertRead, AlertUpdate
from app.schemas.notification import NotificationLogRead
from app.schemas.price import PriceRecordCreate, PriceRecordRead
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate

# ── ProductCreate / ProductRead ───────────────────────────────────────────────


class TestProductSchema:
    def test_product_create_round_trip(self):
        # Arrange
        data = {
            "name": "Test Product",
            "url": "https://example.com/product",
            "source_type": "amazon",
            "css_selector": None,
            "is_active": True,
        }
        # Act
        schema = ProductCreate(**data)
        # Assert
        assert schema.name == "Test Product"
        assert schema.source_type == "amazon"
        assert schema.css_selector is None
        assert schema.is_active is True

    def test_product_read_preserves_all_fields(self):
        # Arrange / Act
        schema = ProductRead(
            id=1,
            name="Widget",
            url="https://example.com/widget",
            source_type="generic",
            css_selector=".price",
            is_active=True,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-02T00:00:00Z",
        )
        # Assert
        assert schema.id == 1
        assert schema.css_selector == ".price"

    def test_product_update_all_fields_optional(self):
        # Arrange / Act
        update = ProductUpdate()
        # Assert — all fields should be None when not provided
        assert update.name is None
        assert update.url is None
        assert update.source_type is None
        assert update.css_selector is None
        assert update.is_active is None

    def test_product_update_partial(self):
        # Arrange / Act
        update = ProductUpdate(name="New Name")
        # Assert
        assert update.name == "New Name"
        assert update.url is None

    def test_product_schema_accepts_any_source_type_string(self):
        # source_type is now a plain string at the schema layer (Item 18) —
        # validity is enforced at the API boundary against the enabled preset
        # registry (422), not by Pydantic. So the schema itself accepts any
        # non-empty string; see test_products_api for the 422 enforcement.
        schema = ProductCreate(
            name="Bad",
            url="https://example.com",
            source_type="nonexistent_source",
        )
        assert schema.source_type == "nonexistent_source"


# ── AlertCreate / AlertRead / AlertUpdate ─────────────────────────────────────


class TestAlertSchema:
    def test_alert_create_valid(self):
        # Arrange / Act
        schema = AlertCreate(
            product_id=1,
            threshold_price=Decimal("29.99"),
            direction=AlertDirection.below,
        )
        # Assert
        assert schema.product_id == 1
        assert schema.threshold_price == Decimal("29.99")
        assert schema.direction == AlertDirection.below
        assert schema.is_active is True

    def test_alert_direction_sideways_rejected(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError):
            AlertCreate(
                product_id=1,
                threshold_price=Decimal("10.00"),
                direction="sideways",
            )

    def test_alert_read_includes_id_and_notified_at(self):
        # Arrange / Act
        schema = AlertRead(
            id=5,
            product_id=1,
            threshold_price=Decimal("50.00"),
            direction=AlertDirection.above,
            notified_at=None,
        )
        # Assert
        assert schema.id == 5
        assert schema.notified_at is None

    def test_alert_update_all_fields_optional(self):
        # Arrange / Act
        update = AlertUpdate()
        # Assert — product_id is intentionally absent from AlertUpdate
        assert update.threshold_price is None
        assert update.direction is None
        assert update.is_active is None


# ── PriceRecordCreate / PriceRecordRead ───────────────────────────────────────


class TestPriceRecordSchema:
    def test_price_record_create_valid(self):
        # Arrange / Act
        schema = PriceRecordCreate(product_id=1, price=Decimal("19.99"), currency="GBP")
        # Assert
        assert schema.price == Decimal("19.99")
        assert schema.currency == "GBP"

    def test_price_record_currency_defaults_to_gbp(self):
        # Arrange / Act
        schema = PriceRecordCreate(product_id=1, price=Decimal("9.99"))
        # Assert
        assert schema.currency == "GBP"

    def test_price_record_create_price_none_rejected(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError):
            PriceRecordCreate(product_id=1, price=None)  # type: ignore[arg-type]

    def test_price_record_read_adds_id_and_captured_at(self):
        # Arrange / Act
        schema = PriceRecordRead(
            id=10,
            product_id=2,
            price=Decimal("99.00"),
            currency="USD",
            captured_at="2026-01-01T12:00:00Z",
        )
        # Assert
        assert schema.id == 10
        assert schema.currency == "USD"


# ── NotificationLogRead ───────────────────────────────────────────────────────


class TestNotificationLogSchema:
    def test_notification_log_read_valid(self):
        # Arrange / Act
        schema = NotificationLogRead(
            id=1,
            alert_id=2,
            channel=NotificationChannel.email,
            payload={"to": "user@example.com"},
            sent_at="2026-01-01T10:00:00Z",
            status=NotificationStatus.sent,
        )
        # Assert
        assert schema.channel == NotificationChannel.email
        assert schema.status == NotificationStatus.sent
        assert schema.payload == {"to": "user@example.com"}

    def test_notification_log_read_null_payload(self):
        # Arrange / Act
        schema = NotificationLogRead(
            id=1,
            alert_id=2,
            channel=NotificationChannel.webhook,
            sent_at="2026-01-01T10:00:00Z",
            status=NotificationStatus.pending,
        )
        # Assert
        assert schema.payload is None
