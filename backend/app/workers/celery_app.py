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

import celery_aio_pool
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

# Full dotted path to celery-aio-pool's AsyncIOPool; Celery resolves this via
# symbol_by_name when it builds the worker pool. (The "custom" alias +
# CELERY_CUSTOM_WORKER_POOL indirection does not resolve when set via config.)
_AIO_POOL = "celery_aio_pool.pool:AsyncIOPool"

# Patch Celery's task tracer so it awaits coroutines returned by async def tasks.
celery_aio_pool.patch_celery_tracer()

celery_app = Celery(
    "price_pulse",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.scrape",
        "app.tasks.notify",
        "app.tasks.schedule",
        "app.tasks.maintenance",
    ],
)

celery_app.conf.update(
    # ── Worker pool ───────────────────────────────────────────────────────────
    # celery-aio-pool's AsyncIOPool awaits the coroutines returned by the
    # project's native `async def` tasks. The stock "solo"/prefork pools do NOT
    # await coroutines — tasks would fail with "coroutine is not JSON
    # serializable" and never run (scrape, notifications).
    worker_pool=_AIO_POOL,
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
    # Schedules are added to Redis dynamically (per-product, at create time), so
    # beat must re-read Redis frequently to pick up an entry created after it
    # started. Without this, an idle beat with no entries sleeps for the default
    # loop interval (~300s) and a product created seconds later would not scrape
    # until minutes later — long past any reasonable wait. Cap the loop at 5s so
    # newly-registered schedules fire promptly (negligible overhead at 30-min
    # production intervals).
    beat_max_loop_interval=5,
    # ── Static beat schedule ──────────────────────────────────────────────────
    # Per-product scrape schedules are dynamic RedBeat entries; this static entry
    # is the one recurring maintenance job. RedBeat merges conf.beat_schedule into
    # Redis on startup, so it runs alongside the dynamic entries.
    beat_schedule={
        "prune-scrape-jobs-daily": {
            "task": "app.tasks.maintenance.prune_scrape_jobs",
            "schedule": crontab(hour=3, minute=0),  # daily at 03:00 UTC
        },
    },
)

# Register the ScrapeJob lifecycle signal handlers (Item 17). Imported for the
# side effect of connecting before_task_publish / task_prerun / task_postrun in
# every process that imports celery_app — the API (on-demand publish), beat
# (scheduled publish), and the worker (prerun/postrun). Kept last so celery_app
# is fully configured first; the module does not import celery_app (no cycle).
import app.workers.scrape_job_signals  # noqa: E402,F401
