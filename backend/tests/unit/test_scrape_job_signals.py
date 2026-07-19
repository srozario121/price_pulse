"""Unit tests for the ScrapeJob Celery-signal handlers (Item 17).

The core handlers are session-injected so they can be exercised with a fake
session that records the SQLAlchemy statements passed to ``execute``; the
outcome-folding and id-extraction helpers are pure. Arrange-Act-Assert.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.models.enums import ExtractionStatus, ScrapeJobStatus
from app.workers import scrape_job_signals as sig

_NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


class _FakeSession:
    """Records statements passed to execute()/commit()/rollback()."""

    def __init__(self) -> None:
        self.executed: list[object] = []
        self.committed = False
        self.rolled_back = False

    def execute(self, stmt: object) -> None:
        self.executed.append(stmt)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


# ── _sync_database_url ──────────────────────────────────────────────────────────


def test_sync_database_url_asyncpg_to_psycopg() -> None:
    # Arrange / Act
    out = sig._sync_database_url("postgresql+asyncpg://u:p@h:5432/db")
    # Assert
    assert out == "postgresql+psycopg://u:p@h:5432/db"


def test_sync_database_url_bare_postgres_gets_driver() -> None:
    assert sig._sync_database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


def test_sync_database_url_sqlite_drops_aiosqlite() -> None:
    assert sig._sync_database_url("sqlite+aiosqlite:///:memory:") == "sqlite:///:memory:"


# ── _extract_product_id ─────────────────────────────────────────────────────────


def test_extract_product_id_from_positional_args() -> None:
    assert sig._extract_product_id(((42,), {}, {})) == 42


def test_extract_product_id_from_kwargs() -> None:
    assert sig._extract_product_id(((), {"product_id": 7}, {})) == 7


def test_extract_product_id_missing_returns_none() -> None:
    assert sig._extract_product_id(((), {}, {})) is None
    assert sig._extract_product_id(None) is None


# ── _fold_outcome ───────────────────────────────────────────────────────────────


def test_fold_outcome_success_ok_is_success() -> None:
    status, extraction, detail = sig._fold_outcome("SUCCESS", "ok")
    assert status == ScrapeJobStatus.SUCCESS.value
    assert extraction == "ok"
    assert detail is None


def test_fold_outcome_success_non_ok_folds_to_failure() -> None:
    for retval in ("http_error", "extraction_failed", "blocked", "captcha", "not_found"):
        status, extraction, detail = sig._fold_outcome("SUCCESS", retval)
        assert status == ScrapeJobStatus.FAILURE.value
        assert extraction == retval
        assert detail is None


def test_fold_outcome_failure_state_captures_detail() -> None:
    status, extraction, detail = sig._fold_outcome("FAILURE", ValueError("boom"))
    assert status == ScrapeJobStatus.FAILURE.value
    assert extraction is None
    assert detail == "boom"


# ── Core handlers ────────────────────────────────────────────────────────────────


def test_handle_publish_executes_insert() -> None:
    # Arrange
    session = _FakeSession()
    # Act
    sig.handle_publish(
        session,
        task_id="abc",
        product_id=1,
        queue="default",
        trigger="on_demand",
        enqueued_at=_NOW,
    )
    # Assert — one insert statement was issued
    assert len(session.executed) == 1


def test_handle_prerun_sets_started() -> None:
    session = _FakeSession()
    sig.handle_prerun(session, task_id="abc", retries=0, started_at=_NOW)
    assert len(session.executed) == 1


def test_handle_postrun_retry_does_not_execute() -> None:
    # Arrange
    session = _FakeSession()
    # Act — RETRY is not terminal; the row stays 'started'
    sig.handle_postrun(
        session, task_id="abc", state="RETRY", retval=None, retries=1, finished_at=_NOW
    )
    # Assert — no update issued
    assert session.executed == []


def test_handle_postrun_success_executes_update() -> None:
    session = _FakeSession()
    sig.handle_postrun(
        session, task_id="abc", state="SUCCESS", retval="ok", retries=0, finished_at=_NOW
    )
    assert len(session.executed) == 1


# ── Guard: never raises; swallows DB errors ─────────────────────────────────────


def test_run_guarded_swallows_work_exception() -> None:
    # Arrange — a session whose work raises
    session = _FakeSession()
    factory = MagicMock(return_value=session)
    sig.set_session_factory(factory)

    def _boom(_s: object) -> None:
        raise RuntimeError("db down")

    try:
        # Act — must NOT raise
        sig._run_guarded("test", _boom)
    finally:
        sig.set_session_factory(None)

    # Assert — the work was rolled back and the error swallowed
    assert session.rolled_back is True
    assert session.committed is False


def test_run_guarded_commits_on_success() -> None:
    session = _FakeSession()
    sig.set_session_factory(MagicMock(return_value=session))
    try:
        sig._run_guarded("test", lambda s: s.execute("noop"))
    finally:
        sig.set_session_factory(None)
    assert session.committed is True
    assert session.rolled_back is False


# ── Wrappers filter to scrape_product ───────────────────────────────────────────


def test_on_before_task_publish_ignores_other_senders() -> None:
    # Arrange — factory must never be touched for a non-scrape sender
    factory = MagicMock()
    sig.set_session_factory(factory)
    try:
        # Act
        sig.on_before_task_publish(
            sender="app.tasks.notify.send_notification",
            headers={"id": "x"},
            body=((1,), {}, {}),
            routing_key="default",
        )
    finally:
        sig.set_session_factory(None)
    # Assert
    factory.assert_not_called()


def test_on_task_prerun_ignores_other_senders() -> None:
    factory = MagicMock()
    sig.set_session_factory(factory)
    other = MagicMock()
    other.name = "app.tasks.notify.send_notification"
    try:
        sig.on_task_prerun(sender=other, task_id="x")
    finally:
        sig.set_session_factory(None)
    factory.assert_not_called()


def test_on_before_task_publish_missing_ids_is_noop() -> None:
    factory = MagicMock()
    sig.set_session_factory(factory)
    try:
        # scrape sender but no task id / product id → logged and skipped
        sig.on_before_task_publish(
            sender="app.tasks.scrape.scrape_product",
            headers={},
            body=((), {}, {}),
            routing_key="default",
        )
    finally:
        sig.set_session_factory(None)
    factory.assert_not_called()


def test_extraction_status_ok_constant_matches() -> None:
    # Guards against drift between the enum and the fold logic.
    assert ExtractionStatus.OK.value == "ok"
