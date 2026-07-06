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
        # Act
        products_api._register_schedule_best_effort(42)
    # Assert
    reg.assert_called_once_with(42, settings.SCRAPE_INTERVAL_MINUTES)


def test_register_best_effort_swallows_errors() -> None:
    # Arrange
    with patch("app.tasks.schedule.register_product_schedule", side_effect=RuntimeError("redis down")):
        # Act / Assert — must not raise
        products_api._register_schedule_best_effort(7)


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
