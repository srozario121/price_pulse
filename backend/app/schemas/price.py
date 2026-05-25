"""Pydantic v2 schemas for PriceRecord."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PriceRecordCreate(BaseModel):
    product_id: int
    price: Decimal
    currency: str = "GBP"
    raw_html_hash: str | None = None


class PriceRecordRead(PriceRecordCreate):
    id: int
    captured_at: datetime

    model_config = ConfigDict(from_attributes=True)
