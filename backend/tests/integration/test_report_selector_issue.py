"""Integration tests for POST /products/{id}/report-selector-issue (Item 16).

Arrange-Act-Assert throughout; real Postgres via the testcontainer. The Celery
dispatch is patched, so these assert *what would be enqueued*, not broker
behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.enums import SelectorProfileStatus
from app.models.selector_profile import SelectorProfile
from app.services import selector_profile_service

pytestmark = pytest.mark.integration

_HOST = "shop.example.com"


async def _create_product(client, url: str = f"https://www.{_HOST}/p/1") -> dict:
    resp = await client.post(
        "/api/v1/products",
        json={
            "name": "Widget",
            "url": url,
            "source_type": "generic",
            "css_selector": ".price",
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def _profile(session) -> SelectorProfile | None:
    return await session.scalar(select(SelectorProfile).where(SelectorProfile.host == _HOST))


class TestReportSelectorIssue:
    async def test_marks_the_host_stale_and_enqueues_regeneration(
        self, pg_async_client, pg_session
    ):
        # Arrange
        product = await _create_product(pg_async_client)

        # Act
        with patch("app.tasks.selector.regenerate_selector.apply_async") as dispatch:
            resp = await pg_async_client.post(
                f"/api/v1/products/{product['id']}/report-selector-issue"
            )

        # Assert
        assert resp.status_code == 202
        body = resp.json()
        assert body["host"] == _HOST  # the "www." prefix is normalised away
        assert body["regeneration_enqueued"] is True
        assert body["status"] == SelectorProfileStatus.STALE
        dispatch.assert_called_once_with(args=[product["id"]], queue="playwright")
        assert await _profile(pg_session) is not None

    async def test_an_active_profile_is_demoted_to_stale(self, pg_async_client, pg_session):
        # Arrange — a healed host that a user says is now wrong
        product = await _create_product(pg_async_client)
        pg_session.add(
            SelectorProfile(
                host=_HOST,
                source_type="generic",
                status=SelectorProfileStatus.ACTIVE,
                price_selector=".old",
                version=2,
            )
        )
        await pg_session.commit()

        # Act
        with patch("app.tasks.selector.regenerate_selector.apply_async"):
            resp = await pg_async_client.post(
                f"/api/v1/products/{product['id']}/report-selector-issue"
            )

        # Assert
        assert resp.status_code == 202
        assert resp.json()["status"] == SelectorProfileStatus.STALE

    async def test_report_inside_the_cooldown_does_not_enqueue_a_duplicate(
        self, pg_async_client, pg_session, monkeypatch
    ):
        # Arrange — an attempt was made moments ago
        monkeypatch.setattr(selector_profile_service.settings, "SELECTOR_REGEN_COOLDOWN_HOURS", 6)
        product = await _create_product(pg_async_client)
        pg_session.add(
            SelectorProfile(
                host=_HOST,
                source_type="generic",
                status=SelectorProfileStatus.STALE,
                failed_attempts=1,
                last_attempt_at=datetime.now(UTC),
            )
        )
        await pg_session.commit()

        # Act
        with patch("app.tasks.selector.regenerate_selector.apply_async") as dispatch:
            resp = await pg_async_client.post(
                f"/api/v1/products/{product['id']}/report-selector-issue"
            )

        # Assert — still accepted, but no duplicate work queued
        assert resp.status_code == 202
        assert resp.json()["regeneration_enqueued"] is False
        dispatch.assert_not_called()

    async def test_a_report_revives_a_host_parked_as_failed(
        self, pg_async_client, pg_session, monkeypatch
    ):
        # Arrange — budget spent; without revival the host could never heal again
        monkeypatch.setattr(selector_profile_service.settings, "SELECTOR_MAX_REGEN_ATTEMPTS", 3)
        product = await _create_product(pg_async_client)
        pg_session.add(
            SelectorProfile(
                host=_HOST,
                source_type="generic",
                status=SelectorProfileStatus.FAILED,
                failed_attempts=3,
            )
        )
        await pg_session.commit()

        # Act
        with patch("app.tasks.selector.regenerate_selector.apply_async") as dispatch:
            resp = await pg_async_client.post(
                f"/api/v1/products/{product['id']}/report-selector-issue"
            )

        # Assert — a human asserting the price is wrong clears the budget
        assert resp.status_code == 202
        assert resp.json()["regeneration_enqueued"] is True
        dispatch.assert_called_once()
        await pg_session.refresh(await _profile(pg_session))
        profile = await _profile(pg_session)
        assert profile.status == SelectorProfileStatus.STALE
        assert profile.failed_attempts == 0

    async def test_unknown_product_returns_404(self, pg_async_client):
        # Act
        resp = await pg_async_client.post("/api/v1/products/999999/report-selector-issue")

        # Assert
        assert resp.status_code == 404

    async def test_a_broker_failure_still_returns_202(self, pg_async_client):
        # Arrange — the profile is already marked stale in the DB, so a broker
        # hiccup costs a delayed heal, not a failed user request
        product = await _create_product(pg_async_client)

        # Act
        with patch(
            "app.tasks.selector.regenerate_selector.apply_async",
            side_effect=RuntimeError("broker down"),
        ):
            resp = await pg_async_client.post(
                f"/api/v1/products/{product['id']}/report-selector-issue"
            )

        # Assert
        assert resp.status_code == 202
        assert resp.json()["regeneration_enqueued"] is False

    async def test_two_products_on_one_host_share_a_single_profile(
        self, pg_async_client, pg_session
    ):
        # Arrange — the whole point of keying by host: one heal fixes both
        first = await _create_product(pg_async_client, url=f"https://{_HOST}/p/1")
        second = await _create_product(pg_async_client, url=f"https://www.{_HOST}/p/2")

        # Act
        with patch("app.tasks.selector.regenerate_selector.apply_async"):
            await pg_async_client.post(f"/api/v1/products/{first['id']}/report-selector-issue")
            await pg_async_client.post(f"/api/v1/products/{second['id']}/report-selector-issue")

        # Assert
        rows = (
            (await pg_session.execute(select(SelectorProfile).where(SelectorProfile.host == _HOST)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
