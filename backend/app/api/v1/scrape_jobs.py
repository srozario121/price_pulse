"""FastAPI route handlers for scrape-job visibility (Item 17).

Routes
------
GET /scrape-jobs                         → 200 PaginatedResponse[ScrapeJobRead]
GET /scrape-jobs/queue-depth             → 200 QueueDepthResponse (best-effort)
GET /products/{id}/scrape-jobs           → 200 PaginatedResponse[ScrapeJobRead] (404 if product absent)

A ``ScrapeJob`` row is created for every ``scrape_product`` dispatch (on-demand +
scheduled) by the Celery signal handlers, so these read-only endpoints surface
queue depth and failures directly rather than via worker logs / ``/prices``.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from starlette.concurrency import run_in_threadpool

from app.core.database import get_db
from app.models.enums import ScrapeJobStatus
from app.models.product import Product
from app.models.scrape_job import ScrapeJob
from app.schemas.common import PaginatedResponse
from app.schemas.scrape_job import QueueDepth, QueueDepthResponse, ScrapeJobRead
from app.scrapers.registry import DEFAULT_QUEUE, PLAYWRIGHT_QUEUE

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["scrape-jobs"])

# Valid ScrapeJobStatus values, for the ?status= filter (422 otherwise).
_STATUS_VALUES = {s.value for s in ScrapeJobStatus}
# Queues surfaced by /scrape-jobs/queue-depth.
_KNOWN_QUEUES = (DEFAULT_QUEUE, PLAYWRIGHT_QUEUE)


async def _paginated_jobs(
    db: AsyncSession,
    *,
    filters: list[ColumnElement[bool]],
    limit: int,
    offset: int,
) -> PaginatedResponse[ScrapeJobRead]:
    """Shared query: total count + newest-first page of ScrapeJob rows."""
    total = await db.scalar(select(func.count(ScrapeJob.id)).where(*filters)) or 0
    result = await db.execute(
        select(ScrapeJob)
        .where(*filters)
        .order_by(ScrapeJob.enqueued_at.desc(), ScrapeJob.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [ScrapeJobRead.model_validate(j) for j in result.scalars().all()]
    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/scrape-jobs",
    response_model=PaginatedResponse[ScrapeJobRead],
    summary="List scrape jobs (filterable, newest first)",
)
async def list_scrape_jobs(
    product_id: int | None = Query(None, description="Filter by product"),
    job_status: str | None = Query(None, alias="status", description="Filter by lifecycle status"),
    queue: str | None = Query(None, description="Filter by Celery queue"),
    task_id: str | None = Query(None, description="Filter by Celery task id"),
    limit: int = Query(20, ge=1, le=100, description="Max items per page (≤ 100)"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ScrapeJobRead]:
    if job_status is not None and job_status not in _STATUS_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown status {job_status!r}; expected one of {sorted(_STATUS_VALUES)}",
        )

    filters: list[ColumnElement[bool]] = []
    if product_id is not None:
        filters.append(ScrapeJob.product_id == product_id)
    if job_status is not None:
        filters.append(ScrapeJob.status == job_status)
    if queue is not None:
        filters.append(ScrapeJob.queue == queue)
    if task_id is not None:
        filters.append(ScrapeJob.task_id == task_id)

    return await _paginated_jobs(db, filters=filters, limit=limit, offset=offset)


@router.get(
    "/scrape-jobs/queue-depth",
    response_model=QueueDepthResponse,
    summary="Best-effort broker queue depth (degrades gracefully)",
)
async def queue_depth() -> QueueDepthResponse:
    """Best-effort per-queue broker depth + responsive-worker count.

    Broker/control introspection is synchronous, so it runs in a threadpool to
    avoid blocking the event loop. Any failure degrades to ``None`` values rather
    than a 500 or a hang — this endpoint is additive visibility, not a gate.
    """
    return await run_in_threadpool(_gather_queue_depth)


@router.get(
    "/products/{product_id}/scrape-jobs",
    response_model=PaginatedResponse[ScrapeJobRead],
    summary="List scrape jobs for one product (404 if absent)",
)
async def list_product_scrape_jobs(
    product_id: int,
    limit: int = Query(20, ge=1, le=100, description="Max items per page (≤ 100)"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ScrapeJobRead]:
    exists = await db.scalar(select(Product.id).where(Product.id == product_id))
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found",
        )
    return await _paginated_jobs(
        db, filters=[ScrapeJob.product_id == product_id], limit=limit, offset=offset
    )


# ── Best-effort broker introspection (sync; run in a threadpool) ────────────────


def _gather_queue_depth() -> QueueDepthResponse:
    """Query broker depth per known queue + count responsive workers.

    Fully guarded: a broker/worker that does not answer yields ``None`` for that
    signal instead of raising. Imported lazily so the module has no import-time
    dependency on a live broker connection.
    """
    from app.workers.celery_app import celery_app

    queues = [QueueDepth(queue=q, messages=_queue_len(celery_app, q)) for q in _KNOWN_QUEUES]
    return QueueDepthResponse(queues=queues, workers_online=_count_workers(celery_app))


def _queue_len(celery_app: object, queue: str) -> int | None:
    """Redis-broker list length for *queue* (``None`` if unavailable)."""
    try:
        with celery_app.connection_for_read() as conn:  # type: ignore[attr-defined]
            client = conn.channel().client
            return int(client.llen(queue))
    except Exception as exc:  # noqa: BLE001 — best-effort; unknown on failure
        logger.debug("queue_depth_broker_unavailable", queue=queue, error=str(exc))
        return None


def _count_workers(celery_app: object) -> int | None:
    """Number of workers answering a ping within a short timeout (``None`` if none)."""
    try:
        replies = celery_app.control.inspect(timeout=1.0).ping()  # type: ignore[attr-defined]
        return len(replies) if replies else 0
    except Exception as exc:  # noqa: BLE001 — best-effort; unknown on failure
        logger.debug("queue_depth_inspect_unavailable", error=str(exc))
        return None
