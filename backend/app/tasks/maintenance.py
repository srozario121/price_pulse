"""Periodic maintenance Celery tasks.

``prune_scrape_jobs`` bounds the ``scrape_job`` table (Item 17): at a 30-minute
scrape cadence × every active product the table grows without limit, so a daily
beat task deletes rows older than ``SCRAPE_JOB_RETENTION_DAYS``.

Unlike the ScrapeJob *signal* handlers (which must use a sync session because they
fire inside the worker's running event loop), this is an ordinary ``async def``
Celery task run by the aio pool, so it uses the normal ``AsyncSessionLocal``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.scrape_job import ScrapeJob
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def retention_cutoff(now: datetime) -> datetime:
    """Return the prune cut-off: ``now - SCRAPE_JOB_RETENTION_DAYS``.

    Rows with ``enqueued_at`` strictly before this are deleted; rows on or after
    it are kept. Extracted as a pure function so the boundary is unit-testable.
    """
    return now - timedelta(days=settings.SCRAPE_JOB_RETENTION_DAYS)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.tasks.maintenance.prune_scrape_jobs",
)
async def prune_scrape_jobs() -> int:
    """Delete ``ScrapeJob`` rows enqueued before the retention cut-off.

    Returns the number of rows deleted. The cut-off is
    ``now - SCRAPE_JOB_RETENTION_DAYS``; rows on or after it are kept.
    """
    cutoff = retention_cutoff(datetime.now(UTC))

    async with AsyncSessionLocal() as session:
        to_delete = (
            await session.scalar(
                select(func.count(ScrapeJob.id)).where(ScrapeJob.enqueued_at < cutoff)
            )
        ) or 0
        if to_delete:
            await session.execute(delete(ScrapeJob).where(ScrapeJob.enqueued_at < cutoff))
            await session.commit()

    logger.info(
        "prune_scrape_jobs_complete",
        deleted=to_delete,
        cutoff=cutoff.isoformat(),
        retention_days=settings.SCRAPE_JOB_RETENTION_DAYS,
    )
    return int(to_delete)
