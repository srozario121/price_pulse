"""Abstract base class for all scraper adapters."""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from app.schemas.scraper import ScrapedResult


class BaseScraper(ABC):
    """Every scraper adapter must subclass this and implement fetch()."""

    @abstractmethod
    async def fetch(self, url: str) -> ScrapedResult:
        """Fetch the page at *url* and return a ScrapedResult."""

    @staticmethod
    def _compute_hash(html: str) -> str:
        """Return the SHA-256 hex digest of *html*."""
        return hashlib.sha256(html.encode()).hexdigest()
