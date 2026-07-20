"""Integration tests for the ScrapeJob signal handlers + prune task (Item 17).

The signal handlers write through a dedicated *synchronous* session (they fire
inside the worker's running event loop), so they are exercised here against a
real sync engine over the Postgres testcontainer. The ``pg_engine`` fixture owns
the schema lifecycle (create/drop); a sibling sync engine on the same database
runs the handlers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.scrape_job import ScrapeJob
from app.workers import scrape_job_signals as sig

_NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
def sync_session_factory(pg_engine, pg_container):
    """Sync session factory on the same DB the async ``pg_engine`` provisioned."""
    sync_url = pg_container.get_connection_url().replace("+psycopg2", "+psycopg")
    engine = create_engine(sync_url, future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield factory
    engine.dispose()


async def _create_product(pg_async_client, url: str = "https://example.com/widget") -> int:
    payload = {
        "name": "Widget",
        "url": url,
        "source_type": "generic",
        "css_selector": ".price",
        "is_active": True,
    }
    resp = await pg_async_client.post("/api/v1/products", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _count(factory: sessionmaker[Session]) -> int:
    with factory() as s:
        return s.scalar(select(func.count(ScrapeJob.id))) or 0


def _get(factory: sessionmaker[Session], task_id: str) -> ScrapeJob | None:
    with factory() as s:
        return s.scalar(select(ScrapeJob).where(ScrapeJob.task_id == task_id))


# ── Full lifecycle ──────────────────────────────────────────────────────────────


class TestSignalLifecycle:
    @pytest.mark.asyncio
    async def test_publish_prerun_postrun_success(self, pg_async_client, sync_session_factory):
        # Arrange
        pid = await _create_product(pg_async_client)

        # Act — publish → queued
        with sync_session_factory() as s:
            sig.handle_publish(
                s,
                task_id="job-1",
                product_id=pid,
                queue="default",
                trigger="on_demand",
                enqueued_at=_NOW,
            )
            s.commit()
        # prerun → started
        with sync_session_factory() as s:
            sig.handle_prerun(s, task_id="job-1", retries=0, started_at=_NOW)
            s.commit()
        # postrun SUCCESS + "ok" → success
        with sync_session_factory() as s:
            sig.handle_postrun(
                s, task_id="job-1", state="SUCCESS", retval="ok", retries=0, finished_at=_NOW
            )
            s.commit()

        # Assert
        job = _get(sync_session_factory, "job-1")
        assert job is not None
        assert job.status == "success"
        assert job.extraction_status == "ok"
        assert job.trigger == "on_demand"
        assert job.started_at is not None
        assert job.finished_at is not None

    @pytest.mark.asyncio
    async def test_postrun_folds_non_ok_to_failure(self, pg_async_client, sync_session_factory):
        pid = await _create_product(pg_async_client, url="https://example.com/x")
        with sync_session_factory() as s:
            sig.handle_publish(
                s,
                task_id="job-2",
                product_id=pid,
                queue="playwright",
                trigger="scheduled",
                enqueued_at=_NOW,
            )
            s.commit()
        with sync_session_factory() as s:
            sig.handle_postrun(
                s, task_id="job-2", state="SUCCESS", retval="blocked", retries=0, finished_at=_NOW
            )
            s.commit()

        job = _get(sync_session_factory, "job-2")
        assert job.status == "failure"
        assert job.extraction_status == "blocked"

    @pytest.mark.asyncio
    async def test_postrun_failure_state_records_detail(
        self, pg_async_client, sync_session_factory
    ):
        pid = await _create_product(pg_async_client, url="https://example.com/y")
        with sync_session_factory() as s:
            sig.handle_publish(
                s,
                task_id="job-3",
                product_id=pid,
                queue="default",
                trigger="scheduled",
                enqueued_at=_NOW,
            )
            s.commit()
        with sync_session_factory() as s:
            sig.handle_postrun(
                s,
                task_id="job-3",
                state="FAILURE",
                retval="timeout exceeded",
                retries=3,
                finished_at=_NOW,
            )
            s.commit()

        job = _get(sync_session_factory, "job-3")
        assert job.status == "failure"
        assert job.extraction_status is None
        assert job.detail == "timeout exceeded"
        assert job.retries == 3


# ── Idempotency ─────────────────────────────────────────────────────────────────


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_republish_same_task_id_yields_one_row(
        self, pg_async_client, sync_session_factory
    ):
        # Arrange
        pid = await _create_product(pg_async_client)

        # Act — publish twice (retry re-publishes the same task_id)
        for _ in range(2):
            with sync_session_factory() as s:
                sig.handle_publish(
                    s,
                    task_id="dup",
                    product_id=pid,
                    queue="default",
                    trigger="scheduled",
                    enqueued_at=_NOW,
                )
                s.commit()
        # prerun on the retry bumps retries
        with sync_session_factory() as s:
            sig.handle_prerun(s, task_id="dup", retries=1, started_at=_NOW)
            s.commit()

        # Assert — exactly one row, retries incremented
        assert _count(sync_session_factory) == 1
        assert _get(sync_session_factory, "dup").retries == 1


# ── Product-already-deleted at publish time ─────────────────────────────────────


class TestGuardedPublish:
    @pytest.mark.asyncio
    async def test_publish_for_missing_product_is_swallowed(self, pg_engine, sync_session_factory):
        # Arrange — the guarded runner uses the injected factory
        sig.set_session_factory(sync_session_factory)
        try:
            # Act — publish for a product_id that does not exist → FK violation,
            # caught by the guard; must not raise and must leak no row.
            sig.on_before_task_publish(
                sender="app.tasks.scrape.scrape_product",
                headers={"id": "orphan"},
                body=((999999,), {}, {}),
                routing_key="default",
            )
        finally:
            sig.set_session_factory(None)

        # Assert
        assert _get(sync_session_factory, "orphan") is None


# ── Prune retention task ────────────────────────────────────────────────────────


class TestPrune:
    @pytest.mark.asyncio
    async def test_prune_deletes_only_old_rows(
        self, pg_async_client, pg_engine, sync_session_factory, monkeypatch
    ):
        # Arrange — one old row (beyond retention), one recent row
        pid = await _create_product(pg_async_client)
        from app.core.config import settings

        old_dt = datetime.now(UTC) - timedelta(days=settings.SCRAPE_JOB_RETENTION_DAYS + 1)
        recent_dt = datetime.now(UTC) - timedelta(hours=1)
        with sync_session_factory() as s:
            s.add(
                ScrapeJob(
                    product_id=pid,
                    task_id="old",
                    status="success",
                    queue="default",
                    trigger="scheduled",
                    enqueued_at=old_dt,
                )
            )
            s.add(
                ScrapeJob(
                    product_id=pid,
                    task_id="recent",
                    status="success",
                    queue="default",
                    trigger="scheduled",
                    enqueued_at=recent_dt,
                )
            )
            s.commit()

        # Point the task's async session at the testcontainer DB.
        from app.tasks import maintenance

        async_url = pg_engine.url.render_as_string(hide_password=False)
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        task_engine = create_async_engine(async_url, poolclass=NullPool)
        task_factory = async_sessionmaker(bind=task_engine, expire_on_commit=False)
        monkeypatch.setattr(maintenance, "AsyncSessionLocal", task_factory)

        # Act
        deleted = await maintenance.prune_scrape_jobs()
        await task_engine.dispose()

        # Assert — only the old row was removed
        assert deleted == 1
        assert _get(sync_session_factory, "old") is None
        assert _get(sync_session_factory, "recent") is not None


def test_retention_cutoff_is_now_minus_retention_days() -> None:
    from app.core.config import settings
    from app.tasks.maintenance import retention_cutoff

    cutoff = retention_cutoff(_NOW)
    assert cutoff == _NOW - timedelta(days=settings.SCRAPE_JOB_RETENTION_DAYS)
