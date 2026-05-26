"""Pydantic schema for the result returned by all scraper adapters."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import ExtractionStatus


class ScrapedResult(BaseModel):
    """Immutable value object produced by every BaseScraper.fetch() call."""

    url: str
    html: str
    html_hash: str
    price: Decimal | None
    currency: str | None
    scraped_at: datetime
    extraction_status: ExtractionStatus
