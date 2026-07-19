"""Direct-call unit tests for route handler functions.

Uses pg_session (Postgres testcontainer) so native ENUMs work.
Calls route functions directly — bypassing ASGITransport — so that
pytest-cov captures the coroutine bodies on Python 3.13.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _create_product(session) -> object:
    from app.models.product import Product

    p = Product(
        name="Widget",
        url="https://example.com/widget",
        source_type="generic",
        css_selector=".price",
    )
    session.add(p)
    await session.flush()
    return p


# ── app/api/v1/alerts.py ──────────────────────────────────────────────────────


class TestAlertHelperDirect:
    @pytest.mark.asyncio
    async def test_get_alert_or_404_returns_alert(self, pg_session) -> None:
        from app.api.v1.alerts import _get_alert_or_404
        from app.models.alert import PriceAlert

        product = await _create_product(pg_session)
        alert = PriceAlert(
            product_id=product.id,
            threshold_price=Decimal("10.00"),
            direction="below",
        )
        pg_session.add(alert)
        await pg_session.flush()

        result = await _get_alert_or_404(alert.id, pg_session)
        assert result.id == alert.id

    @pytest.mark.asyncio
    async def test_get_alert_or_404_raises_404(self, pg_session) -> None:
        from app.api.v1.alerts import _get_alert_or_404

        with pytest.raises(HTTPException) as exc_info:
            await _get_alert_or_404(99999, pg_session)
        assert exc_info.value.status_code == 404


class TestAlertRouteDirect:
    @pytest.mark.asyncio
    async def test_create_alert_returns_alert(self, pg_session) -> None:
        from app.api.v1.alerts import create_alert
        from app.schemas.alert import AlertCreate

        product = await _create_product(pg_session)
        body = AlertCreate(
            product_id=product.id,
            threshold_price=Decimal("25.00"),
            direction="below",
        )
        result = await create_alert(body=body, db=pg_session)
        assert result.id is not None
        assert result.product_id == product.id

    @pytest.mark.asyncio
    async def test_create_alert_missing_product_raises_404(self, pg_session) -> None:
        from app.api.v1.alerts import create_alert
        from app.schemas.alert import AlertCreate

        body = AlertCreate(
            product_id=99999,
            threshold_price=Decimal("10.00"),
            direction="below",
        )
        with pytest.raises(HTTPException) as exc_info:
            await create_alert(body=body, db=pg_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_alerts_returns_paginated(self, pg_session) -> None:
        from app.api.v1.alerts import list_alerts

        product = await _create_product(pg_session)
        from app.models.alert import PriceAlert

        for i in range(3):
            pg_session.add(
                PriceAlert(
                    product_id=product.id,
                    threshold_price=Decimal(f"{10 + i}.00"),
                    direction="below",
                )
            )
        await pg_session.flush()

        result = await list_alerts(
            product_id=product.id, is_active=None, limit=10, offset=0, db=pg_session
        )
        assert result.total == 3
        assert len(result.items) == 3

    @pytest.mark.asyncio
    async def test_update_alert_changes_threshold(self, pg_session) -> None:
        from app.api.v1.alerts import update_alert
        from app.models.alert import PriceAlert
        from app.schemas.alert import AlertUpdate

        product = await _create_product(pg_session)
        alert = PriceAlert(
            product_id=product.id,
            threshold_price=Decimal("10.00"),
            direction="below",
        )
        pg_session.add(alert)
        await pg_session.flush()

        updated = await update_alert(
            alert_id=alert.id,
            body=AlertUpdate(threshold_price=Decimal("99.99")),
            db=pg_session,
        )
        assert updated.threshold_price == Decimal("99.99")

    @pytest.mark.asyncio
    async def test_delete_alert(self, pg_session) -> None:
        from app.api.v1.alerts import delete_alert
        from app.models.alert import PriceAlert

        product = await _create_product(pg_session)
        alert = PriceAlert(
            product_id=product.id,
            threshold_price=Decimal("10.00"),
            direction="below",
        )
        pg_session.add(alert)
        await pg_session.flush()

        # Should not raise
        await delete_alert(alert_id=alert.id, db=pg_session)


# ── app/api/v1/products.py ────────────────────────────────────────────────────


class TestProductHelperDirect:
    @pytest.mark.asyncio
    async def test_get_product_or_404_returns_product(self, pg_session) -> None:
        from app.api.v1.products import _get_product_or_404

        product = await _create_product(pg_session)
        result = await _get_product_or_404(product.id, pg_session)
        assert result.id == product.id

    @pytest.mark.asyncio
    async def test_get_product_or_404_raises_404(self, pg_session) -> None:
        from app.api.v1.products import _get_product_or_404

        with pytest.raises(HTTPException) as exc_info:
            await _get_product_or_404(99999, pg_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_assert_url_unique_raises_409_on_conflict(self, pg_session) -> None:
        from app.api.v1.products import _assert_url_unique

        await _create_product(pg_session)
        with pytest.raises(HTTPException) as exc_info:
            await _assert_url_unique("https://example.com/widget", pg_session)
        assert exc_info.value.status_code == 409


class TestProductRouteDirect:
    @pytest.mark.asyncio
    async def test_create_product_returns_product(self, pg_session) -> None:
        from app.api.v1.products import create_product
        from app.schemas.product import ProductCreate

        body = ProductCreate(
            name="Test Widget",
            url="https://example.com/test",
            source_type="generic",
            css_selector=".price",
        )
        result = await create_product(body=body, db=pg_session)
        assert result.id is not None
        assert result.name == "Test Widget"

    @pytest.mark.asyncio
    async def test_list_products_with_active_filter(self, pg_session) -> None:
        from app.api.v1.products import list_products
        from app.models.product import Product

        p1 = Product(
            name="Active",
            url="https://example.com/active",
            source_type="generic",
            css_selector=".p",
            is_active=True,
        )
        p2 = Product(
            name="Inactive",
            url="https://example.com/inactive",
            source_type="generic",
            css_selector=".p",
            is_active=False,
        )
        pg_session.add(p1)
        pg_session.add(p2)
        await pg_session.flush()

        result = await list_products(is_active=True, limit=10, offset=0, db=pg_session)
        names = [p.name for p in result.items]
        assert "Active" in names
        assert "Inactive" not in names

    @pytest.mark.asyncio
    async def test_update_product_name(self, pg_session) -> None:
        from app.api.v1.products import update_product
        from app.schemas.product import ProductUpdate

        product = await _create_product(pg_session)
        updated = await update_product(
            product_id=product.id,
            body=ProductUpdate(name="Updated"),
            db=pg_session,
        )
        assert updated.name == "Updated"

    @pytest.mark.asyncio
    async def test_update_product_url_conflict_raises_409(self, pg_session) -> None:
        from app.api.v1.products import update_product
        from app.models.product import Product
        from app.schemas.product import ProductUpdate

        p2 = Product(
            name="Other",
            url="https://example.com/other",
            source_type="generic",
            css_selector=".p",
        )
        pg_session.add(p2)
        product = await _create_product(pg_session)
        await pg_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await update_product(
                product_id=product.id,
                body=ProductUpdate(url="https://example.com/other"),
                db=pg_session,
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_product(self, pg_session) -> None:
        from app.api.v1.products import delete_product

        product = await _create_product(pg_session)
        await delete_product(product_id=product.id, db=pg_session)


# ── app/api/v1/prices.py ─────────────────────────────────────────────────────


class TestPricesRouteDirect:
    @pytest.mark.asyncio
    async def test_get_product_or_404_raises_for_missing(self, pg_session) -> None:
        from app.api.v1.prices import _get_product_or_404

        with pytest.raises(HTTPException) as exc_info:
            await _get_product_or_404(99999, pg_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_prices_empty(self, pg_session) -> None:
        from app.api.v1.prices import list_prices

        product = await _create_product(pg_session)
        result = await list_prices(
            product_id=product.id,
            limit=10,
            offset=0,
            from_dt=None,
            to_dt=None,
            db=pg_session,
        )
        assert result.total == 0
        assert result.items == []

    @pytest.mark.asyncio
    async def test_list_prices_with_records(self, pg_session) -> None:
        from datetime import UTC, datetime

        from app.api.v1.prices import list_prices
        from app.models.price_history import PriceRecord

        product = await _create_product(pg_session)
        for i in range(3):
            pg_session.add(
                PriceRecord(
                    product_id=product.id,
                    price=Decimal(f"{10 + i}.00"),
                    currency="GBP",
                    extraction_status="ok",
                    captured_at=datetime.now(UTC),
                )
            )
        await pg_session.flush()

        result = await list_prices(
            product_id=product.id,
            limit=10,
            offset=0,
            from_dt=None,
            to_dt=None,
            db=pg_session,
        )
        assert result.total == 3

    @pytest.mark.asyncio
    async def test_list_prices_with_date_filters(self, pg_session) -> None:
        from datetime import UTC, datetime

        from app.api.v1.prices import list_prices
        from app.models.price_history import PriceRecord

        product = await _create_product(pg_session)
        old_dt = datetime(2024, 1, 1, tzinfo=UTC)
        new_dt = datetime(2026, 1, 1, tzinfo=UTC)
        pg_session.add(
            PriceRecord(
                product_id=product.id,
                price=Decimal("5.00"),
                currency="GBP",
                extraction_status="ok",
                captured_at=old_dt,
            )
        )
        pg_session.add(
            PriceRecord(
                product_id=product.id,
                price=Decimal("9.99"),
                currency="GBP",
                extraction_status="ok",
                captured_at=new_dt,
            )
        )
        await pg_session.flush()

        result = await list_prices(
            product_id=product.id,
            limit=10,
            offset=0,
            from_dt=datetime(2025, 1, 1, tzinfo=UTC),
            to_dt=None,
            db=pg_session,
        )
        assert result.total == 1
        assert result.items[0].price == Decimal("9.99")

    @pytest.mark.asyncio
    async def test_trigger_scrape_inactive_product_raises_400(self, pg_session) -> None:
        from app.api.v1.prices import trigger_scrape
        from app.models.product import Product

        inactive = Product(
            name="Inactive",
            url="https://example.com/inactive",
            source_type="generic",
            css_selector=".p",
            is_active=False,
        )
        pg_session.add(inactive)
        await pg_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await trigger_scrape(product_id=inactive.id, db=pg_session)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_trigger_scrape_queues_task(self, pg_session) -> None:
        from unittest.mock import MagicMock, patch

        from app.api.v1.prices import trigger_scrape

        product = await _create_product(pg_session)  # source_type="generic"

        mock_task = MagicMock()
        mock_task.id = "test-task-id"

        with patch("app.api.v1.prices.scrape_product") as mock_scrape:
            mock_scrape.apply_async = MagicMock(return_value=mock_task)
            result = await trigger_scrape(product_id=product.id, db=pg_session)

        # Generic products route to the default queue; the on-demand dispatch
        # carries the pp_trigger header for ScrapeJob tracking (Item 17).
        mock_scrape.apply_async.assert_called_once_with(
            (product.id,), queue="default", headers={"pp_trigger": "on_demand"}
        )
        assert result.task_id == "test-task-id"
        assert result.status == "queued"
