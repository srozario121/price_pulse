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

import os

# Select the asyncio worker pool BEFORE Celery resolves the pool implementation.
# Celery maps the "custom" pool alias to the class named here; the aio pool
# awaits coroutine results so native `async def` tasks actually execute.
os.environ.setdefault("CELERY_CUSTOM_WORKER_POOL", "celery_aio_pool.pool:AsyncIOPool")

import celery_aio_pool  # noqa: E402
from celery import Celery  # noqa: E402

from app.core.config import settings  # noqa: E402

# Patch Celery's task tracer so it awaits coroutines returned by async def tasks.
celery_aio_pool.patch_celery_tracer()

celery_app = Celery(
    "price_pulse",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.scrape", "app.tasks.notify", "app.tasks.schedule"],
)

celery_app.conf.update(
    # ── Worker pool ───────────────────────────────────────────────────────────
    # "custom" resolves (via CELERY_CUSTOM_WORKER_POOL, set above) to
    # celery-aio-pool's AsyncIOPool, which awaits the coroutines returned by the
    # project's native `async def` tasks. The stock "solo"/prefork pools do NOT
    # await coroutines — tasks would fail with "coroutine is not JSON
    # serializable" and never run (scrape, notifications).
    worker_pool="custom",
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
    # All other tasks use 'default'. task_default_queue MUST be 'default' so the
    # main worker (started with no -Q) consumes the same queue the routes target
    # — otherwise routed tasks (scrape, notify) sit unconsumed in 'default' while
    # the worker listens on Celery's built-in 'celery' queue.
    task_default_queue="default",
    task_routes={
        "app.tasks.scrape.scrape_product": {"queue": "default"},
        "app.tasks.notify.send_notification": {"queue": "default"},
    },
    # ── RedBeat scheduler ─────────────────────────────────────────────────────
    redbeat_redis_url=settings.REDIS_URL,
)
