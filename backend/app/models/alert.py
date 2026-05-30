"""PriceAlert ORM model — user-defined threshold alert for a product."""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.notification_log import NotificationLog
    from app.models.product import Product


class AlertDirection(enum.StrEnum):
    above = "above"
    below = "below"


class PriceAlert(Base):
    __tablename__ = "price_alert"
    __table_args__ = (Index("ix_price_alert_product_active", "product_id", "is_active"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    threshold_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    direction: Mapped[AlertDirection] = mapped_column(
        Enum(AlertDirection, name="alert_direction_enum", native_enum=True),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Notification delivery fields (added in Item 5)
    channel: Mapped[str] = mapped_column(
        Enum("email", "webhook", "whatsapp", name="notification_channel_enum", native_enum=True),
        nullable=False,
        server_default="email",
    )
    webhook_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(20), nullable=True)

    product: Mapped[Product] = relationship("Product", back_populates="price_alerts")
    notification_logs: Mapped[list[NotificationLog]] = relationship(
        "NotificationLog", back_populates="alert", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<PriceAlert id={self.id!r} product_id={self.product_id!r} "
            f"direction={self.direction!r}>"
        )
