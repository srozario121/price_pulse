"""Scraper-layer exception hierarchy."""

from __future__ import annotations


class ScraperError(Exception):
    """Base exception for all scraper failures."""


class UnknownSourceError(ScraperError):
    """Raised when no scraper is registered for a given source_type."""
