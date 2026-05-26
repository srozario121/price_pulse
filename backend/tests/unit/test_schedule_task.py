"""Unit tests for app.tasks.schedule (register/deregister/startup_sync)."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest


def test_register_product_schedule_invalid_interval() -> None:
    """interval_minutes=0 must raise ValueError before touching Redis."""
    from app.tasks.schedule import register_product_schedule

    with pytest.raises(ValueError, match="interval_minutes"):
        register_product_schedule(product_id=42, interval_minutes=0)


def test_register_product_schedule_saves_entry() -> None:
    """register_product_schedule creates a RedBeatSchedulerEntry and saves it."""
    entry_mock = MagicMock()
    entry_cls_mock = MagicMock(return_value=entry_mock)

    with patch("app.tasks.schedule.RedBeatSchedulerEntry", entry_cls_mock):
        from app.tasks.schedule import register_product_schedule

        register_product_schedule(product_id=42, interval_minutes=30)

    entry_cls_mock.assert_called_once()
    call_kwargs = entry_cls_mock.call_args[1]
    assert call_kwargs["name"] == "scrape:42"
    assert call_kwargs["task"] == "app.tasks.scrape.scrape_product"
    assert call_kwargs["schedule"] == timedelta(minutes=30)
    assert call_kwargs["args"] == [42]
    entry_mock.save.assert_called_once()


def test_register_product_schedule_negative_interval_raises() -> None:
    """interval_minutes < 0 must raise ValueError."""
    from app.tasks.schedule import register_product_schedule

    with pytest.raises(ValueError, match="interval_minutes"):
        register_product_schedule(product_id=1, interval_minutes=-5)


def test_deregister_product_schedule_calls_delete() -> None:
    """deregister_product_schedule fetches entry by key and deletes it."""
    entry_mock = MagicMock()
    from_key_mock = MagicMock(return_value=entry_mock)

    entry_cls_mock = MagicMock()
    entry_cls_mock.from_key = from_key_mock

    with patch("app.tasks.schedule.RedBeatSchedulerEntry", entry_cls_mock):
        from app.tasks.schedule import deregister_product_schedule

        deregister_product_schedule(product_id=42)

    from_key_mock.assert_called_once()
    args, kwargs = from_key_mock.call_args
    assert args[0] == "redbeat:scrape:42"
    entry_mock.delete.assert_called_once()


def test_deregister_product_schedule_missing_key_is_noop() -> None:
    """deregister_product_schedule does not raise for non-existent product."""
    from_key_mock = MagicMock(side_effect=KeyError("not found"))

    entry_cls_mock = MagicMock()
    entry_cls_mock.from_key = from_key_mock

    with patch("app.tasks.schedule.RedBeatSchedulerEntry", entry_cls_mock):
        from app.tasks.schedule import deregister_product_schedule

        # Should not raise
        deregister_product_schedule(product_id=9999)
