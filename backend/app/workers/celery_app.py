"""Celery application factory for Price Pulse.

All Celery workers (default pool, playwright pool) import the `celery_app`
object from this module via `-A app.workers.celery_app`.

Design decisions:
- worker_pool: asyncio (celery.concurrency.aio:TaskPool) — all tasks are
  native `async def`; no asyncio.run() wrappers needed inside tasks.
- redbeat_redis_url: Redis-backed dynamic scheduler; per-product scrape
  intervals are stored as RedBeatSchedulerEntry objects in Redis.
- task_routes: static route table maps all default tasks to 'default' queue;
  Amazon scrape tasks are dispatched to 'playwright' queue at call-site
  (inside scrape_product), not via static routes.
- task_soft_time_limit / task_time_limit: prevents zombie scrape tasks from
  holding workers indefinitely (120 s soft, 150 s hard kill).
"""

from __future__ import annotations

from celery import Celery  # type: ignore[import-untyped]

from app.core.config import settings

celery_app = Celery(
    "price_pulse",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.scrape", "app.tasks.notify", "app.tasks.schedule"],
)

celery_app.conf.update(
    # ── Worker pool ───────────────────────────────────────────────────────────
    # "solo" pool runs tasks in the main thread using asyncio.get_event_loop(),
    # which is the correct approach for async def tasks in Celery 5.x.
    # celery.concurrency.aio was planned but never shipped in mainline Celery;
    # "solo" is the idiomatic replacement for async-first task workloads.
    worker_pool="solo",
    # ── Time limits ───────────────────────────────────────────────────────────
    task_soft_time_limit=120,
    task_time_limit=150,
    # ── Serialisation ─────────────────────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # ── Timezone ──────────────────────────────────────────────────────────────
    timezone="UTC",
    enable_utc=True,
    # ── Queue routing ─────────────────────────────────────────────────────────
    # Amazon tasks are dispatched to 'playwright' queue at call-site.
    # All other tasks use 'default'.
    task_routes={
        "app.tasks.scrape.scrape_product": {"queue": "default"},
        "app.tasks.notify.send_notification": {"queue": "default"},
    },
    # ── RedBeat scheduler ─────────────────────────────────────────────────────
    redbeat_redis_url=settings.REDIS_URL,
)
