"""Unit tests for common API schemas and Item 6 schema changes.

No database required — pure Pydantic validation tests.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.alert import AlertDirection
from app.schemas.alert import AlertUpdate
from app.schemas.common import PaginatedResponse, ScrapeJobResponse
from app.schemas.price import PriceRecordRead
from app.schemas.product import ProductRead

# ── PaginatedResponse ─────────────────────────────────────────────────────────


class TestPaginatedResponse:
    def test_serialises_correctly(self):
        # Arrange / Act
        page: PaginatedResponse[int] = PaginatedResponse(
            items=[1, 2, 3], total=100, limit=3, offset=10
        )
        # Assert
        assert page.items == [1, 2, 3]
        assert page.total == 100
        assert page.limit == 3
        assert page.offset == 10

    def test_limit_at_100_is_valid(self):
        page: PaginatedResponse[int] = PaginatedResponse(items=[], total=0, limit=100, offset=0)
        assert page.limit == 100

    def test_limit_above_100_rejected(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError) as exc_info:
            PaginatedResponse(items=[], total=0, limit=101, offset=0)
        assert "limit" in str(exc_info.value).lower()

    def test_pagination_arithmetic(self):
        """Seeding 25 items with limit=10 and offset=20 should yield 5 items."""
        items = list(range(5))  # 5 items in the last page
        page: PaginatedResponse[int] = PaginatedResponse(items=items, total=25, limit=10, offset=20)
        assert page.total == 25
        assert len(page.items) == 5


# ── ScrapeJobResponse ─────────────────────────────────────────────────────────


class TestScrapeJobResponse:
    def _make_product_read(self) -> ProductRead:
        return ProductRead(
            id=1,
            name="Test Product",
            url="https://example.com/product",
            source_type="generic",
            css_selector=None,
            is_active=True,
            created_at=datetime(2026, 1, 1, 12, 0, 0),
            updated_at=datetime(2026, 1, 1, 12, 0, 0),
        )

    def test_round_trip_preserves_all_fields(self):
        # Arrange / Act
        product = self._make_product_read()
        response = ScrapeJobResponse(
            task_id="abc-123",
            status="queued",
            product=product,
        )
        # Assert
        assert response.task_id == "abc-123"
        assert response.status == "queued"
        assert response.product.id == 1
        assert response.product.name == "Test Product"

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            ScrapeJobResponse(
                task_id="abc",
                status="running",  # only "queued" is valid
                product=self._make_product_read(),
            )


# ── AlertUpdate guards ────────────────────────────────────────────────────────


class TestAlertUpdateGuards:
    def test_alert_update_product_id_rejected(self):
        """product_id must not be accepted — alert ownership is immutable."""
        with pytest.raises(ValidationError) as exc_info:
            AlertUpdate(product_id=1)  # type: ignore[call-arg]
        assert "product_id" in str(exc_info.value)

    def test_alert_update_empty_is_valid(self):
        update = AlertUpdate()
        assert update.threshold_price is None
        assert update.is_active is None

    def test_alert_update_valid_fields_accepted(self):
        update = AlertUpdate(
            threshold_price=Decimal("50.00"),
            direction=AlertDirection.above,
            is_active=False,
        )
        assert update.threshold_price == Decimal("50.00")
        assert update.direction == AlertDirection.above
        assert update.is_active is False

    def test_alert_update_unknown_field_rejected(self):
        """extra='forbid' on AlertUpdate rejects all unknown fields."""
        with pytest.raises(ValidationError):
            AlertUpdate(unknown_field="x")  # type: ignore[call-arg]


# ── PriceRecordRead nullable fields ──────────────────────────────────────────


class TestPriceRecordReadSchema:
    def test_read_with_nullable_price(self):
        record = PriceRecordRead(
            id=1,
            product_id=2,
            price=None,
            currency=None,
            captured_at=datetime(2026, 1, 1, 12, 0, 0),
            extraction_status="http_error",
        )
        assert record.price is None
        assert record.currency is None
        assert record.extraction_status == "http_error"

    def test_read_defaults_extraction_status_to_ok(self):
        record = PriceRecordRead(
            id=1,
            product_id=2,
            price=Decimal("9.99"),
            currency="GBP",
            captured_at=datetime(2026, 1, 1, 12, 0, 0),
        )
        assert record.extraction_status == "ok"

    def test_read_existing_test_compat(self):
        """Existing test_schemas.py call site still works after adding extraction_status."""
        record = PriceRecordRead(
            id=10,
            product_id=2,
            price=Decimal("99.00"),
            currency="USD",
            captured_at="2026-01-01T12:00:00Z",
        )
        assert record.id == 10
        assert record.currency == "USD"
