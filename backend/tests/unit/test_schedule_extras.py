"""Extra unit tests to cover schedule.py branches missed by existing tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_sync_schedules_async_queries_active_products() -> None:
    """_sync_schedules_async calls register_product_schedule for each active product."""
    from app.tasks.schedule import _sync_schedules_async

    p1 = MagicMock()
    p1.id = 1
    p2 = MagicMock()
    p2.id = 2

    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=[p1, p2])
    exec_result = AsyncMock()
    exec_result.scalars = MagicMock(return_value=scalars_result)

    session = AsyncMock()
    session.execute = AsyncMock(return_value=exec_result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    # _sync_schedules_async imports AsyncSessionLocal lazily — patch at source
    with (
        patch("app.core.database.AsyncSessionLocal", return_value=session),
        patch("app.tasks.schedule.register_product_schedule") as reg_mock,
    ):
        await _sync_schedules_async()

    assert reg_mock.call_count == 2
    call_ids = {c.args[0] for c in reg_mock.call_args_list}
    assert call_ids == {1, 2}


def test_startup_sync_schedules_runs_async() -> None:
    """startup_sync_schedules wraps _sync_schedules_async in asyncio.run."""
    from app.tasks.schedule import startup_sync_schedules

    with patch("app.tasks.schedule.asyncio.run") as run_mock:
        startup_sync_schedules()
    run_mock.assert_called_once()


def test_on_worker_ready_calls_startup_sync() -> None:
    """on_worker_ready signal handler calls startup_sync_schedules."""
    from app.tasks.schedule import on_worker_ready

    with patch("app.tasks.schedule.startup_sync_schedules") as sync_mock:
        on_worker_ready()
    sync_mock.assert_called_once()
