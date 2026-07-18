"""Celery schedule management — per-product RedBeat entries.

Functions:
  register_product_schedule(product_id, interval_minutes)
      Creates or updates the RedBeatSchedulerEntry for scrape_product.
  deregister_product_schedule(product_id)
      Removes the RedBeat entry; idempotent (no-op for missing keys).
  startup_sync_schedules()
      Bootstrap: called via the Celery worker_ready signal on first start.
      Queries all is_active=True products and registers a schedule for each.

Design decisions:
- RedBeatSchedulerEntry key pattern: "scrape:{product_id}".
- startup_sync_schedules uses asyncio.run() because Celery signals fire in a
  sync context.  The function itself opens its own event loop and session.
- interval_minutes=0 raises ValueError before touching Redis.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import structlog
from celery.signals import worker_ready
from redbeat import RedBeatSchedulerEntry

from app.scrapers.registry import DEFAULT_QUEUE, queue_for_source_type
from app.workers.celery_app import celery_app

logger = structlog.get_logger()

_SCHEDULE_KEY_PREFIX = "scrape"


def _schedule_key(product_id: int) -> str:
    return f"{_SCHEDULE_KEY_PREFIX}:{product_id}"


def register_product_schedule(
    product_id: int,
    interval_minutes: int,
    queue: str = DEFAULT_QUEUE,
) -> None:
    """Create or replace the RedBeat entry for *product_id*.

    *queue* is the Celery queue the scheduled scrape is dispatched to when the
    beat fires — Amazon products must use the ``playwright`` queue (see
    ``queue_for_source_type``) so the browser-capable worker runs them.

    Raises ValueError if interval_minutes < 1.
    """
    if interval_minutes < 1:
        raise ValueError(f"interval_minutes must be >= 1, got {interval_minutes}")

    key = _schedule_key(product_id)
    interval = timedelta(minutes=interval_minutes)

    entry = RedBeatSchedulerEntry(
        name=key,
        task="app.tasks.scrape.scrape_product",
        schedule=interval,
        args=[product_id],
        options={"queue": queue},
        app=celery_app,
    )
    entry.save()

    logger.info(
        "product_schedule_registered",
        product_id=product_id,
        interval_minutes=interval_minutes,
        key=key,
        queue=queue,
    )


def deregister_product_schedule(product_id: int) -> None:
    """Remove the RedBeat schedule entry for *product_id* (idempotent).

    No exception is raised if the key does not exist.
    """
    key = _schedule_key(product_id)
    try:
        entry = RedBeatSchedulerEntry.from_key(f"redbeat:{key}", app=celery_app)
        entry.delete()
        logger.info("product_schedule_deregistered", product_id=product_id, key=key)
    except KeyError:
        logger.debug(
            "product_schedule_deregister_noop",
            product_id=product_id,
            key=key,
        )


async def _sync_schedules_async() -> None:
    """Async inner: query active products and register all their schedules."""
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.models.product import Product

    async with AsyncSessionLocal() as session:
        stmt = select(Product).where(Product.is_active.is_(True))
        result = await session.execute(stmt)
        products = result.scalars().all()

        # Resolve each product's queue from the DB-backed preset registry while the
        # session is open (queue_for_source_type is async and DB-backed).
        schedule_specs = [
            (product.id, await queue_for_source_type(str(product.source_type), session))
            for product in products
        ]

    for product_id, queue in schedule_specs:
        register_product_schedule(
            product_id,
            settings.SCRAPE_INTERVAL_MINUTES,
            queue=queue,
        )

    logger.info("startup_schedules_synced", product_count=len(schedule_specs))


def startup_sync_schedules() -> None:
    """Bootstrap RedBeat entries for all active products.

    Called at worker startup via the worker_ready Celery signal.
    Runs the async DB query in a new event loop.
    """
    asyncio.run(_sync_schedules_async())


@worker_ready.connect  # type: ignore[untyped-decorator]
def on_worker_ready(**_kwargs: object) -> None:  # noqa: ANN003
    """Signal handler: sync schedules when any worker comes online.

    Schedule bootstrap is best-effort: if the DB is briefly unavailable or the
    schema is not yet present at worker start, log and continue rather than let
    the exception escape the signal handler — an escaping error corrupts the
    async worker's event loop and stops it processing tasks (e.g. notifications).
    """
    logger.info("worker_ready_signal_received")
    try:
        startup_sync_schedules()
    except Exception as exc:
        logger.warning("startup_sync_schedules_failed", error=str(exc))
