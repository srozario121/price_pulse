"""NotificationLog ORM model — per-delivery audit log for alert notifications."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, BigInteger, DateTime, Enum, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.alert import PriceAlert


class NotificationChannel(enum.StrEnum):
    email = "email"
    webhook = "webhook"
    whatsapp = "whatsapp"


class NotificationStatus(enum.StrEnum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class NotificationLog(Base):
    __tablename__ = "notification_log"
    __table_args__ = (
        Index("ix_notification_log_alert_sent", "alert_id", "sent_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("price_alert.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel_enum", native_enum=True),
        nullable=False,
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status_enum", native_enum=True),
        default=NotificationStatus.pending,
        nullable=False,
    )

    alert: Mapped[PriceAlert] = relationship("PriceAlert", back_populates="notification_logs")

    def __repr__(self) -> str:
        return (
            f"<NotificationLog id={self.id!r} alert_id={self.alert_id!r} "
            f"status={self.status!r}>"
        )
