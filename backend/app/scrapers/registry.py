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


def get_scraper(source_type: str, **kwargs: object) -> BaseScraper:
    """Return a configured BaseScraper for the given source_type.

    kwargs are passed to the scraper constructor (e.g. css_selector for GenericScraper).
    Raises UnknownSourceError for 'ebay', 'currys', or unrecognised strings.
    """
    try:
        st = SourceType(source_type)
    except ValueError as exc:
        raise UnknownSourceError(
            f"No scraper registered for source_type={source_type!r}"
        ) from exc

    scraper_cls = _REGISTRY.get(st)
    if scraper_cls is None:
        raise UnknownSourceError(
            f"No scraper registered for source_type={source_type!r}"
        )

    return scraper_cls(**kwargs)
