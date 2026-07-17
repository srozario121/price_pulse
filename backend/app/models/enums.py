"""Shared enumerations for ORM models and scraper layer."""

from __future__ import annotations

import enum


class ExtractionStatus(enum.StrEnum):
    OK = "ok"
    EXTRACTION_FAILED = "extraction_failed"
    HTTP_ERROR = "http_error"
    # Anti-blocking (Item 15): a source actively refusing the crawl. Distinct
    # from EXTRACTION_FAILED (selector drift) and HTTP_ERROR (transient). The
    # DB column is an open String(20) — no CHECK constraint — so adding values
    # here needs no migration (see migration 0006).
    BLOCKED = "blocked"  # 429/503 or IP-ban markers after proxy rotations are exhausted
    CAPTCHA = "captcha"  # a robot-check interstitial (often served with HTTP 200)
