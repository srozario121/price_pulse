"""Unit tests for the Celery application factory (celery_app.py)."""

from __future__ import annotations


def test_broker_url_matches_settings() -> None:
    from app.core.config import settings
    from app.workers.celery_app import celery_app

    assert celery_app.conf.broker_url == settings.CELERY_BROKER_URL


def test_result_backend_matches_settings() -> None:
    from app.core.config import settings
    from app.workers.celery_app import celery_app

    assert celery_app.conf.result_backend == settings.CELERY_RESULT_BACKEND


def test_soft_time_limit() -> None:
    from app.workers.celery_app import celery_app

    assert celery_app.conf.task_soft_time_limit == 120


def test_hard_time_limit() -> None:
    from app.workers.celery_app import celery_app

    assert celery_app.conf.task_time_limit == 150


def test_worker_pool_is_async_aio_pool() -> None:
    from app.workers.celery_app import celery_app

    # celery-aio-pool's AsyncIOPool awaits async def tasks (stock pools do not).
    assert celery_app.conf.worker_pool == "celery_aio_pool.pool:AsyncIOPool"


def test_redbeat_redis_url() -> None:
    from app.core.config import settings
    from app.workers.celery_app import celery_app

    assert celery_app.conf.redbeat_redis_url == settings.REDIS_URL
