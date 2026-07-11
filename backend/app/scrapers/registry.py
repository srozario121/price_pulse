"""Registry mapping source_type strings to scraper classes."""

from __future__ import annotations

import enum

from app.scrapers.amazon import AmazonScraper
from app.scrapers.base import BaseScraper
from app.scrapers.exceptions import UnknownSourceError
from app.scrapers.generic import GenericScraper


class SourceType(enum.StrEnum):
    GENERIC = "generic"
    AMAZON = "amazon"
    EBAY = "ebay"
    CURRYS = "currys"


_REGISTRY: dict[SourceType, type[BaseScraper]] = {
    SourceType.GENERIC: GenericScraper,
    SourceType.AMAZON: AmazonScraper,
}

# ── Celery queue routing ────────────────────────────────────────────────────────
# The Amazon scraper drives a real headless browser (Playwright/Chromium), which
# is installed ONLY on the dedicated ``celery-playwright`` worker (queue
# "playwright"). Every other source type runs on the default worker. Callers that
# dispatch ``scrape_product`` must route by source_type using this helper —
# otherwise Amazon tasks land on the browserless default worker and fail with
# "BrowserType.launch: Executable doesn't exist".
DEFAULT_QUEUE = "default"
PLAYWRIGHT_QUEUE = "playwright"

# Source types whose scraper needs a browser and must run on the playwright queue.
_PLAYWRIGHT_SOURCE_TYPES = frozenset({SourceType.AMAZON})


def queue_for_source_type(source_type: str) -> str:
    """Return the Celery queue that can execute *source_type*'s scraper.

    Unknown source types fall back to the default queue; the scraper lookup will
    surface any real ``UnknownSourceError`` when the task actually runs.
    """
    try:
        st = SourceType(source_type)
    except ValueError:
        return DEFAULT_QUEUE
    return PLAYWRIGHT_QUEUE if st in _PLAYWRIGHT_SOURCE_TYPES else DEFAULT_QUEUE


def get_scraper(source_type: str, **kwargs: object) -> BaseScraper:
    """Return a configured BaseScraper for the given source_type.

    kwargs are passed to the scraper constructor (e.g. css_selector for GenericScraper).
    Raises UnknownSourceError for 'ebay', 'currys', or unrecognised strings.
    """
    try:
        st = SourceType(source_type)
    except ValueError as exc:
        raise UnknownSourceError(f"No scraper registered for source_type={source_type!r}") from exc

    scraper_cls = _REGISTRY.get(st)
    if scraper_cls is None:
        raise UnknownSourceError(f"No scraper registered for source_type={source_type!r}")

    return scraper_cls(**kwargs)
