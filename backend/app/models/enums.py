"""Shared enumerations for ORM models and scraper layer."""
from __future__ import annotations

import enum


class ExtractionStatus(enum.StrEnum):
    OK = "ok"
    EXTRACTION_FAILED = "extraction_failed"
    HTTP_ERROR = "http_error"
