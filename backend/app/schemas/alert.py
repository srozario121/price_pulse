"""Pydantic v2 schemas for PriceAlert."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.alert import AlertDirection
from app.models.notification_log import NotificationChannel


class AlertBase(BaseModel):
    product_id: int
    threshold_price: Decimal
    direction: AlertDirection
    is_active: bool = True
    channel: NotificationChannel = NotificationChannel.email
    webhook_url: str | None = None
    whatsapp_number: str | None = None


class AlertCreate(AlertBase):
    pass


class AlertRead(AlertBase):
    id: int
    notified_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AlertUpdate(BaseModel):
    product_id: int | None = None
    threshold_price: Decimal | None = None
    direction: AlertDirection | None = None
    is_active: bool | None = None
    channel: NotificationChannel | None = None
    webhook_url: str | None = None
    whatsapp_number: str | None = None
