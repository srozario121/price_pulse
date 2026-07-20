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


class ScrapeJobStatus(enum.StrEnum):
    """Lifecycle status of a single ``scrape_product`` Celery job (Item 17).

    The extraction outcome is *folded* into this status: a job that runs to
    completion is ``SUCCESS`` only when the scrape produced a usable price
    (``extraction_status == "ok"``); any non-``ok`` outcome (``http_error``,
    ``extraction_failed``, ``blocked``, ``captcha``, …) and a raised/timed-out
    task both resolve to ``FAILURE``. The raw retval is preserved separately in
    ``ScrapeJob.extraction_status`` so "task errored" stays distinguishable from
    "ran but found no price". Stored as a plain ``String(20)`` column (no native
    DB enum), matching the ``extraction_status`` convention.
    """

    QUEUED = "queued"
    STARTED = "started"
    SUCCESS = "success"
    FAILURE = "failure"
