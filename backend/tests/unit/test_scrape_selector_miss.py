"""Unit tests for the scrape task's drift handling (Item 16).

Arrange-Act-Assert throughout; isolated — the profile service and the Celery
dispatch are patched, so nothing touches a DB or a broker.

The contract: a ``selector_miss`` marks the host stale and enqueues regeneration
*subject to the guards*, and every failure in that bookkeeping is swallowed —
the scrape has already recorded its result, so self-healing must never turn a
completed scrape into a retried or failed one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.scrape import _handle_selector_miss


@pytest.fixture()
def session() -> MagicMock:
    return MagicMock()


class TestHandleSelectorMiss:
    async def test_enqueues_regeneration_when_the_guards_allow(self, session):
        # Arrange
        dispatch = MagicMock()

        # Act
        with patch(
            "app.services.selector_profile_service.mark_stale",
            new=AsyncMock(return_value=(MagicMock(), True)),
        ):
            with patch("app.tasks.selector.regenerate_selector.apply_async", dispatch):
                await _handle_selector_miss(session, "amazon.co.uk", "amazon", 7)

        # Assert — routed to the browser-capable worker that holds the credentials
        dispatch.assert_called_once_with(args=[7], queue="playwright")

    async def test_does_not_enqueue_when_the_guards_refuse(self, session):
        # Arrange — cooldown active or attempt budget spent
        dispatch = MagicMock()

        # Act
        with patch(
            "app.services.selector_profile_service.mark_stale",
            new=AsyncMock(return_value=(MagicMock(), False)),
        ):
            with patch("app.tasks.selector.regenerate_selector.apply_async", dispatch):
                await _handle_selector_miss(session, "amazon.co.uk", "amazon", 7)

        # Assert
        dispatch.assert_not_called()

    async def test_a_broker_failure_does_not_propagate(self, session):
        # Arrange — the scrape already persisted its PriceRecord; raising here
        # would retry the whole scrape for a background concern
        # Act / Assert — no exception escapes
        with patch(
            "app.services.selector_profile_service.mark_stale",
            new=AsyncMock(return_value=(MagicMock(), True)),
        ):
            with patch(
                "app.tasks.selector.regenerate_selector.apply_async",
                MagicMock(side_effect=RuntimeError("broker down")),
            ):
                await _handle_selector_miss(session, "amazon.co.uk", "amazon", 7)

    async def test_a_profile_bookkeeping_failure_does_not_propagate(self, session):
        # Arrange — e.g. the profile write hits a DB error
        # Act / Assert — no exception escapes
        with patch(
            "app.services.selector_profile_service.mark_stale",
            new=AsyncMock(side_effect=RuntimeError("db error")),
        ):
            await _handle_selector_miss(session, "amazon.co.uk", "amazon", 7)
