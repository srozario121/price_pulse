"""Abstract base class for all scraper adapters."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from app.schemas.scraper import LearnedSelector, ScrapedResult


class BaseScraper(ABC):
    """Every scraper adapter must subclass this and implement fetch()."""

    # The host's stored, LLM-generated selector for this fetch (Item 16), or None
    # when the host has none. Set post-construction by the registry rather than
    # threaded through every ``__init__`` — the adapters have deliberately
    # different constructor signatures, and only the paths that support learned
    # selectors (amazon, generic) read it. A class-level default keeps every
    # scraper — including ones built directly in tests — safe to attribute-access.
    learned_selector: LearnedSelector | None = None

    @abstractmethod
    async def fetch(self, url: str) -> ScrapedResult:
        """Fetch the page at *url* and return a ScrapedResult."""

    @staticmethod
    def _compute_hash(html: str) -> str:
        """Return the SHA-256 hex digest of *html*."""
        return hashlib.sha256(html.encode()).hexdigest()
