"""Value objects exchanged with the scraper adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import ExtractionStatus


@dataclass(frozen=True)
class LearnedSelector:
    """A host's stored, LLM-generated price selector, handed to a scraper (Item 16).

    Deliberately a plain value object rather than the ``SelectorProfile`` ORM row:
    scrapers run far from the session — some inside a Playwright context — and
    must never trigger a lazy load. It lives in the scraper-schema module so
    ``scrapers/`` can consume it without importing from ``services/``.
    """

    price_selector: str
    currency_selector: str | None = None


class ScrapedResult(BaseModel):
    """Immutable value object produced by every BaseScraper.fetch() call."""

    url: str
    html: str
    html_hash: str
    price: Decimal | None
    currency: str | None
    scraped_at: datetime
    extraction_status: ExtractionStatus
