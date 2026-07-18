"""Unit tests for the product create/delete → RedBeat schedule hooks.

Regression guard: newly-created products must register a per-product scrape
schedule (and deleted products must deregister theirs). Registration is
best-effort — a RedBeat/Redis error is logged, never propagated to the request.
"""

from __future__ import annotations

from unittest.mock import patch

from app.api.v1 import products as products_api
from app.core.config import settings


def test_register_best_effort_calls_register_with_configured_interval() -> None:
    # Arrange — the handler imports register_product_schedule lazily from app.tasks.schedule
    with patch("app.tasks.schedule.register_product_schedule") as reg:
        # Act — the caller resolves the queue (queue_for_source_type) and passes it in
        products_api._register_schedule_best_effort(42, "default")
    # Assert
    reg.assert_called_once_with(42, settings.SCRAPE_INTERVAL_MINUTES, queue="default")


def test_register_best_effort_passes_resolved_queue_through() -> None:
    # Regression guard: the browser-required 'playwright' queue (resolved from the
    # source's preset by queue_for_source_type — Item 18) is passed straight to
    # RedBeat so the browser-capable worker runs those scrapes.
    with patch("app.tasks.schedule.register_product_schedule") as reg:
        # Act
        products_api._register_schedule_best_effort(42, "playwright")
    # Assert
    reg.assert_called_once_with(42, settings.SCRAPE_INTERVAL_MINUTES, queue="playwright")


def test_register_best_effort_swallows_errors() -> None:
    # Arrange
    with patch(
        "app.tasks.schedule.register_product_schedule", side_effect=RuntimeError("redis down")
    ):
        # Act / Assert — must not raise
        products_api._register_schedule_best_effort(7, "default")


def test_deregister_best_effort_calls_deregister() -> None:
    # Arrange
    with patch("app.tasks.schedule.deregister_product_schedule") as dereg:
        # Act
        products_api._deregister_schedule_best_effort(99)
    # Assert
    dereg.assert_called_once_with(99)


def test_deregister_best_effort_swallows_errors() -> None:
    # Arrange
    with patch(
        "app.tasks.schedule.deregister_product_schedule", side_effect=RuntimeError("redis down")
    ):
        # Act / Assert — must not raise
        products_api._deregister_schedule_best_effort(7)
