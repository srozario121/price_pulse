"""Pydantic v2 schemas for PriceRecord."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PriceRecordCreate(BaseModel):
    product_id: int
    price: Decimal
    currency: str = "GBP"
    raw_html_hash: str | None = None


class PriceRecordRead(BaseModel):
    """Read schema for PriceRecord.

    ``price`` and ``currency`` are nullable — failed scrape attempts are stored
    with ``price=NULL`` and ``currency=NULL`` (see Item 4 migration).
    ``extraction_status`` reflects the outcome of the scrape attempt.
    """

    id: int
    product_id: int
    price: Decimal | None = None
    currency: str | None = None
    captured_at: datetime
    raw_html_hash: str | None = None
    extraction_status: str = "ok"

    model_config = ConfigDict(from_attributes=True)
