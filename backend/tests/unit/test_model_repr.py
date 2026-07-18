"""Unit tests for ORM model __repr__ methods — no database required.

All four model modules must be imported before constructing any model instance
so SQLAlchemy can resolve the string-based relationship targets (e.g.
``"PriceRecord"``) that are used in ``back_populates``.  The imports below
satisfy that requirement without touching a database.
"""

# Import every model so SQLAlchemy can wire up all relationship targets.
import app.models.alert  # noqa: F401
import app.models.notification_log  # noqa: F401
import app.models.price_history  # noqa: F401
import app.models.product  # noqa: F401
from app.models.alert import AlertDirection, PriceAlert
from app.models.notification_log import NotificationLog, NotificationStatus
from app.models.price_history import PriceRecord
from app.models.product import Product


class TestModelRepr:
    def test_product_repr_includes_id_and_name(self):
        # Arrange
        p = Product(id=42, name="Test Widget", url="https://example.com", source_type="amazon")
        # Act / Assert
        assert "42" in repr(p)
        assert "Test Widget" in repr(p)

    def test_price_record_repr_includes_product_id_and_price(self):
        # Arrange
        pr = PriceRecord(id=1, product_id=7, price="19.99")
        # Act / Assert
        assert "7" in repr(pr)
        assert "19.99" in repr(pr)

    def test_price_alert_repr_includes_product_id_and_direction(self):
        # Arrange
        alert = PriceAlert(
            id=3, product_id=5, direction=AlertDirection.below, threshold_price="10.00"
        )
        # Act / Assert
        assert "5" in repr(alert)
        assert "below" in repr(alert)

    def test_notification_log_repr_includes_alert_id_and_status(self):
        # Arrange
        log = NotificationLog(id=1, alert_id=9, channel="email", status=NotificationStatus.sent)
        # Act / Assert
        assert "9" in repr(log)
        assert "sent" in repr(log)
