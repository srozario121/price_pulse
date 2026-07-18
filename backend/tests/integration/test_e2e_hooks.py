"""Integration tests for the E2E harness backend surface (Item 13/14).

Covers:
- the gated test-control hooks (`/_test/products/{id}/scrape-sync`,
  `/_test/alerts/{id}/reset-cooldown`) against a real Postgres testcontainer;
- the public notification-history endpoint
  (`GET /alerts/{id}/notifications`) added so E2E scenarios can assert
  notification delivery through the public API.

The scraper and the Celery notification dispatch are stubbed so the tests are
hermetic (no network, no broker) while still exercising the real
record_price → evaluate_alerts path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import ExtractionStatus
from app.schemas.scraper import ScrapedResult

pytestmark = pytest.mark.integration


class _FakeScraper:
    """Returns a canned ScrapedResult without touching the network."""

    def __init__(self, result: ScrapedResult) -> None:
        self._result = result

    async def fetch(self, url: str) -> ScrapedResult:
        return self._result


def _stub_get_scraper(result: ScrapedResult):
    """Build an async ``get_scraper`` replacement returning a canned fake scraper.

    ``get_scraper`` is now an async, DB-backed coroutine (Item 18), so the hook's
    ``await get_scraper(...)`` needs an awaitable stub.
    """

    async def _get(*_args: object, **_kwargs: object) -> _FakeScraper:
        return _FakeScraper(result)

    return _get


def _ok_result(url: str, price: str) -> ScrapedResult:
    return ScrapedResult(
        url=url,
        html=f"<html><span class='price'>{price}</span></html>",
        html_hash="hash-" + price,
        price=Decimal(price),
        currency="USD",
        scraped_at=datetime.now(UTC),
        extraction_status=ExtractionStatus.OK,
    )


@pytest_asyncio.fixture()
async def hooks_client(pg_engine, monkeypatch) -> AsyncClient:
    """AsyncClient bound to Postgres with E2E_TEST_HOOKS enabled."""
    from app.core.config import settings
    from app.core.database import get_db
    from app.main import create_app

    monkeypatch.setattr(settings, "E2E_TEST_HOOKS", True)

    factory = async_sessionmaker(
        bind=pg_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )

    async def override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _create_product(client: AsyncClient, url: str = "http://fixture/p1") -> int:
    resp = await client.post(
        "/api/v1/products",
        json={
            "name": "Widget",
            "url": url,
            "source_type": "generic",
            "css_selector": ".price",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_alert(client: AsyncClient, product_id: int, threshold: str = "100.00") -> int:
    resp = await client.post(
        "/api/v1/alerts",
        json={
            "product_id": product_id,
            "threshold_price": threshold,
            "direction": "below",
            "channel": "email",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── scrape-sync ────────────────────────────────────────────────────────────────


async def test_scrape_sync_records_price_and_triggers_alert(hooks_client, monkeypatch) -> None:
    # Arrange
    product_id = await _create_product(hooks_client)
    alert_id = await _create_alert(hooks_client, product_id, threshold="100.00")

    monkeypatch.setattr(
        "app.api.v1._test_hooks.get_scraper",
        _stub_get_scraper(_ok_result("http://fixture/p1", "50.00")),
    )
    dispatched: list[int] = []
    monkeypatch.setattr(
        "app.services.notifications.notify_alert",
        lambda aid: dispatched.append(aid),
    )

    # Act
    resp = await hooks_client.post(f"/api/v1/_test/products/{product_id}/scrape-sync")

    # Assert
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["extraction_status"] == "ok"
    assert body["price"] == "50.00"
    assert dispatched == [alert_id]  # threshold crossed → notification dispatched


async def test_scrape_sync_unknown_product_404(hooks_client) -> None:
    # Arrange / Act
    resp = await hooks_client.post("/api/v1/_test/products/999999/scrape-sync")
    # Assert
    assert resp.status_code == 404


# ── reset-cooldown ──────────────────────────────────────────────────────────────


async def test_reset_cooldown_clears_notified_at(hooks_client, monkeypatch) -> None:
    # Arrange — trigger the alert so notified_at is set
    product_id = await _create_product(hooks_client, url="http://fixture/p2")
    alert_id = await _create_alert(hooks_client, product_id, threshold="100.00")
    monkeypatch.setattr(
        "app.api.v1._test_hooks.get_scraper",
        _stub_get_scraper(_ok_result("http://fixture/p2", "50.00")),
    )
    monkeypatch.setattr("app.services.notifications.notify_alert", lambda aid: None)
    await hooks_client.post(f"/api/v1/_test/products/{product_id}/scrape-sync")

    before = await hooks_client.get(f"/api/v1/alerts/{alert_id}")
    assert before.json()["notified_at"] is not None

    # Act
    resp = await hooks_client.post(f"/api/v1/_test/alerts/{alert_id}/reset-cooldown")

    # Assert
    assert resp.status_code == 200, resp.text
    after = await hooks_client.get(f"/api/v1/alerts/{alert_id}")
    assert after.json()["notified_at"] is None


async def test_reset_cooldown_unknown_alert_404(hooks_client) -> None:
    # Arrange / Act
    resp = await hooks_client.post("/api/v1/_test/alerts/999999/reset-cooldown")
    # Assert
    assert resp.status_code == 404


# ── notification history endpoint ───────────────────────────────────────────────


async def test_list_alert_notifications_paginates(pg_engine, pg_async_client) -> None:
    # Arrange — insert a product, alert, and two notification logs directly
    from app.models.alert import PriceAlert
    from app.models.notification_log import NotificationLog
    from app.models.product import Product

    factory = async_sessionmaker(
        bind=pg_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    async with factory() as session:
        product = Product(name="W", url="http://fixture/n1", source_type="generic")
        session.add(product)
        await session.flush()
        alert = PriceAlert(
            product_id=product.id,
            threshold_price=Decimal("100.00"),
            direction="below",
            channel="email",
        )
        session.add(alert)
        await session.flush()
        session.add_all(
            [
                NotificationLog(alert_id=alert.id, channel="email", status="sent"),
                NotificationLog(alert_id=alert.id, channel="email", status="sent"),
            ]
        )
        await session.commit()
        alert_id = alert.id

    # Act
    resp = await pg_async_client.get(f"/api/v1/alerts/{alert_id}/notifications")

    # Assert
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["items"][0]["status"] == "sent"


async def test_list_alert_notifications_unknown_alert_404(pg_async_client) -> None:
    # Arrange / Act
    resp = await pg_async_client.get("/api/v1/alerts/999999/notifications")
    # Assert
    assert resp.status_code == 404
