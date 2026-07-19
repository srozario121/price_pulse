"""Celery-signal-driven lifecycle tracking for ``scrape_product`` (Item 17).

Every ``scrape_product`` dispatch — on-demand (API) *and* scheduled (RedBeat) —
is recorded as a durable :class:`~app.models.scrape_job.ScrapeJob` row so queue
depth and failures are observable via the public API, not just worker logs.

Producer/consumer signal split
------------------------------
* ``before_task_publish`` (producer side — fires in the API process for
  on-demand and in the beat process for scheduled dispatch) → **create** the
  ``queued`` row. This is the only signal that fires for *both* dispatch paths at
  enqueue time.
* ``task_prerun`` (worker side) → ``started``.
* ``task_postrun`` (worker side) → finalise off the ``state`` arg. The extraction
  outcome is folded into the status: ``SUCCESS`` + retval ``"ok"`` → ``success``;
  any other retval or a raised task → ``failure`` (with the retval / exception
  text preserved in ``extraction_status`` / ``detail``); ``RETRY`` leaves the row
  ``started`` (not finalised).

Robustness
----------
* Every handler ignores non-``scrape_product`` senders (``send_notification`` /
  schedule tasks create no rows).
* All DB work is wrapped so a ``ScrapeJob`` write can **never** break scraping or
  notification delivery — a failure is logged and swallowed.
* Writes use a dedicated **synchronous** SQLAlchemy session, not
  ``AsyncSessionLocal`` + ``asyncio.run()``: the worker runs the celery-aio-pool
  ``AsyncIOPool``, so ``task_prerun`` / ``task_postrun`` fire while an event loop
  is already running and ``asyncio.run()`` would raise ``RuntimeError``.
* All writes upsert by the unique ``task_id`` so a retried / redelivered task
  (``acks_late=True``, ``max_retries=3``) yields exactly one row.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from celery.signals import before_task_publish, task_postrun, task_prerun
from sqlalchemy import create_engine, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.enums import ExtractionStatus, ScrapeJobStatus
from app.models.scrape_job import ScrapeJob

logger = structlog.get_logger(__name__)

_SCRAPE_TASK_NAME = "app.tasks.scrape.scrape_product"
# Custom apply_async header carrying the trigger origin (on-demand vs scheduled).
_TRIGGER_HEADER = "pp_trigger"
_TRIGGER_ON_DEMAND = "on_demand"
_TRIGGER_SCHEDULED = "scheduled"

# Lazy singletons — created on first signal, never at import time (importing this
# module must not open a DB connection). Tests inject their own factory via
# ``set_session_factory``.
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _sync_database_url(url: str) -> str:
    """Return a *synchronous* driver URL for *url* (an async app DB URL).

    Signal handlers run inside the worker's already-running event loop, so they
    cannot use the async engine; a small sync engine over the same Postgres is
    used instead. asyncpg → psycopg (v3, sync); aiosqlite → stdlib sqlite.
    """
    if url.startswith("sqlite"):
        return url.replace("+aiosqlite", "")
    url = url.replace("+asyncpg", "+psycopg")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_session_factory() -> sessionmaker[Session]:
    """Return (lazily building) the dedicated sync ``ScrapeJob`` session factory."""
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_engine(
            _sync_database_url(settings.DATABASE_URL),
            pool_pre_ping=True,
            future=True,
        )
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _session_factory


def set_session_factory(factory: sessionmaker[Session] | None) -> None:
    """Override the session factory (tests bind it to the Postgres testcontainer)."""
    global _session_factory
    _session_factory = factory


def _now() -> datetime:
    return datetime.now(UTC)


# ── Core handlers (session-injected; unit/integration tested directly) ──────────


def handle_publish(
    session: Session,
    *,
    task_id: str,
    product_id: int,
    queue: str,
    trigger: str,
    enqueued_at: datetime,
) -> None:
    """Insert a ``queued`` row for *task_id*; ignore if one already exists.

    Idempotent via ``ON CONFLICT (task_id) DO NOTHING`` so a retried / redelivered
    task never duplicates the row. An insert for an already-deleted ``product_id``
    raises an FK ``IntegrityError`` here, which the guarded wrapper swallows.
    """
    stmt = (
        pg_insert(ScrapeJob)
        .values(
            product_id=product_id,
            task_id=task_id,
            queue=queue,
            trigger=trigger,
            status=ScrapeJobStatus.QUEUED.value,
            enqueued_at=enqueued_at,
        )
        .on_conflict_do_nothing(index_elements=["task_id"])
    )
    session.execute(stmt)


def handle_prerun(
    session: Session,
    *,
    task_id: str,
    retries: int,
    started_at: datetime,
) -> None:
    """Transition the row for *task_id* to ``started`` and record the attempt."""
    session.execute(
        update(ScrapeJob)
        .where(ScrapeJob.task_id == task_id)
        .values(
            status=ScrapeJobStatus.STARTED.value,
            started_at=started_at,
            retries=retries,
        )
    )


def _fold_outcome(state: str, retval: Any) -> tuple[str, str | None, str | None]:  # noqa: ANN401
    """Map a Celery task ``state`` + ``retval`` to (status, extraction_status, detail).

    ``SUCCESS`` + retval ``"ok"`` → ``success``; any other retval → ``failure``
    (folded) with the retval preserved. ``FAILURE`` → ``failure`` + exception text
    in ``detail``. The raw retval / error text keeps "errored" distinguishable
    from "ran but found no price" even though both read as ``failure``.
    """
    if state == "SUCCESS":
        extraction_status = str(retval) if retval is not None else None
        if extraction_status == ExtractionStatus.OK.value:
            return ScrapeJobStatus.SUCCESS.value, extraction_status, None
        return ScrapeJobStatus.FAILURE.value, extraction_status, None
    # FAILURE (and any other terminal, non-retry state): task raised / timed out.
    detail = str(retval) if retval is not None else None
    return ScrapeJobStatus.FAILURE.value, None, detail


def handle_postrun(
    session: Session,
    *,
    task_id: str,
    state: str,
    retval: Any,  # noqa: ANN401
    retries: int,
    finished_at: datetime,
) -> None:
    """Finalise the row for *task_id* off the terminal *state*.

    ``RETRY`` is not terminal — the task will run again — so the row is left
    ``started`` and untouched here; the next ``task_prerun`` bumps ``retries``.
    """
    if state == "RETRY":
        return

    status, extraction_status, detail = _fold_outcome(state, retval)
    session.execute(
        update(ScrapeJob)
        .where(ScrapeJob.task_id == task_id)
        .values(
            status=status,
            extraction_status=extraction_status,
            detail=detail,
            retries=retries,
            finished_at=finished_at,
        )
    )


# ── Guarded runner ──────────────────────────────────────────────────────────────


def _run_guarded(event: str, work: Any) -> None:  # noqa: ANN401 — work is a callable(Session)
    """Run *work(session)* in a committed sync session; never raise.

    A ``ScrapeJob`` write must not break the scrape / notification pipeline, so
    every DB error is logged and swallowed (mirrors the existing best-effort
    schedule-registration and ``on_worker_ready`` guards).
    """
    try:
        factory = get_session_factory()
        with factory() as session:
            try:
                work(session)
                session.commit()
            except Exception:
                session.rollback()
                raise
    except Exception as exc:  # noqa: BLE001 — observability must never break scraping
        logger.warning("scrape_job_signal_failed", signal=event, error=str(exc))


# ── Celery-connected wrappers ───────────────────────────────────────────────────


@before_task_publish.connect  # type: ignore[untyped-decorator]
def on_before_task_publish(
    sender: str | None = None,
    headers: dict[str, Any] | None = None,
    body: Any = None,  # noqa: ANN401
    routing_key: str | None = None,
    **_kwargs: Any,  # noqa: ANN401
) -> None:
    """Create the ``queued`` row for a ``scrape_product`` dispatch (both paths)."""
    if sender != _SCRAPE_TASK_NAME:
        return
    headers = headers or {}
    task_id = headers.get("id")
    product_id = _extract_product_id(body)
    if task_id is None or product_id is None:
        logger.warning("scrape_job_publish_missing_ids", task_id=task_id, product_id=product_id)
        return
    trigger = headers.get(_TRIGGER_HEADER) or _TRIGGER_SCHEDULED
    queue = routing_key or "default"

    _run_guarded(
        "before_task_publish",
        lambda s: handle_publish(
            s,
            task_id=str(task_id),
            product_id=int(product_id),
            queue=str(queue),
            trigger=str(trigger),
            enqueued_at=_now(),
        ),
    )


@task_prerun.connect  # type: ignore[untyped-decorator]
def on_task_prerun(
    sender: Any = None,  # noqa: ANN401 — the task instance
    task_id: str | None = None,
    **_kwargs: Any,  # noqa: ANN401
) -> None:
    """Transition the row to ``started`` when the worker picks up the task."""
    if getattr(sender, "name", None) != _SCRAPE_TASK_NAME or task_id is None:
        return
    retries = _request_retries(sender)
    _run_guarded(
        "task_prerun",
        lambda s: handle_prerun(s, task_id=str(task_id), retries=retries, started_at=_now()),
    )


@task_postrun.connect  # type: ignore[untyped-decorator]
def on_task_postrun(
    sender: Any = None,  # noqa: ANN401 — the task instance
    task_id: str | None = None,
    retval: Any = None,  # noqa: ANN401
    state: str | None = None,
    **_kwargs: Any,  # noqa: ANN401
) -> None:
    """Finalise the row off the terminal state (or leave it ``started`` on RETRY)."""
    if getattr(sender, "name", None) != _SCRAPE_TASK_NAME or task_id is None:
        return
    retries = _request_retries(sender)
    _run_guarded(
        "task_postrun",
        lambda s: handle_postrun(
            s,
            task_id=str(task_id),
            state=str(state),
            retval=retval,
            retries=retries,
            finished_at=_now(),
        ),
    )


# ── Small extraction helpers ────────────────────────────────────────────────────


def _extract_product_id(body: Any) -> int | None:  # noqa: ANN401
    """Pull ``product_id`` (the first positional arg) from a protocol-2 message body.

    Protocol 2 body is ``(args, kwargs, embed)``; ``scrape_product(product_id)``
    puts ``product_id`` at ``args[0]``. Falls back to ``kwargs["product_id"]``.
    """
    try:
        args, kwargs = body[0], body[1]
        if args:
            return int(args[0])
        if kwargs and "product_id" in kwargs:
            return int(kwargs["product_id"])
    except (TypeError, IndexError, KeyError, ValueError):
        return None
    return None


def _request_retries(task: Any) -> int:  # noqa: ANN401
    """Best-effort read of ``task.request.retries`` (0 when unavailable)."""
    request = getattr(task, "request", None)
    return int(getattr(request, "retries", 0) or 0) if request is not None else 0
