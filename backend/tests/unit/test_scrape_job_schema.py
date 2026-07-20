"""Unit tests for ScrapeJob Pydantic schemas (Item 17)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.scrape_job import QueueDepth, QueueDepthResponse, ScrapeJobRead

_NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


def test_scrape_job_read_from_attributes() -> None:
    # Arrange — an object mirroring the ORM row's read fields
    class _Row:
        id = 1
        product_id = 5
        task_id = "abc-123"
        queue = "playwright"
        trigger = "scheduled"
        status = "success"
        extraction_status = "ok"
        detail = None
        retries = 0
        enqueued_at = _NOW
        started_at = _NOW
        finished_at = _NOW

    # Act
    read = ScrapeJobRead.model_validate(_Row())

    # Assert
    assert read.task_id == "abc-123"
    assert read.status == "success"
    assert read.extraction_status == "ok"


def test_scrape_job_read_nullable_fields_default_none() -> None:
    class _Row:
        id = 2
        product_id = 5
        task_id = "def-456"
        queue = "default"
        trigger = "on_demand"
        status = "queued"
        extraction_status = None
        detail = None
        retries = 0
        enqueued_at = _NOW
        started_at = None
        finished_at = None

    read = ScrapeJobRead.model_validate(_Row())
    assert read.extraction_status is None
    assert read.started_at is None
    assert read.finished_at is None


def test_queue_depth_response_allows_unknown_values() -> None:
    # Best-effort payload degrades to None rather than erroring.
    resp = QueueDepthResponse(
        queues=[QueueDepth(queue="default", messages=None)],
        workers_online=None,
    )
    assert resp.queues[0].messages is None
    assert resp.workers_online is None
