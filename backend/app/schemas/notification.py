"""Pydantic v2 schemas for NotificationLog."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.notification_log import NotificationChannel, NotificationStatus


class NotificationLogRead(BaseModel):
    id: int
    alert_id: int
    channel: NotificationChannel
    payload: dict[str, Any] | None = None
    sent_at: datetime
    status: NotificationStatus

    model_config = ConfigDict(from_attributes=True)
