"""Pydantic v2 schemas for ScrapeJob (Item 17 — queued-scrape visibility)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScrapeJobRead(BaseModel):
    """Read schema for a ``ScrapeJob`` lifecycle row.

    ``status`` is the folded lifecycle status (``queued``/``started``/``success``/
    ``failure``); ``extraction_status`` preserves the raw scrape retval and
    ``detail`` any error text, so "task errored" stays distinguishable from "ran
    but found no price".
    """

    id: int
    product_id: int
    task_id: str
    queue: str
    trigger: str
    status: str
    extraction_status: str | None = None
    detail: str | None = None
    retries: int
    enqueued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class QueueDepth(BaseModel):
    """Best-effort broker depth for a single Celery queue.

    ``messages`` is the number of waiting messages in the broker queue, or
    ``None`` when the broker could not be introspected.
    """

    queue: str
    messages: int | None = None


class QueueDepthResponse(BaseModel):
    """``GET /scrape-jobs/queue-depth`` payload — best-effort, degrades gracefully.

    ``workers_online`` is the count of workers that answered a ``ping`` (``None``
    when the control channel could not be reached). Everything degrades to
    ``None`` rather than erroring when no worker/broker responds.
    """

    queues: list[QueueDepth]
    workers_online: int | None = None
