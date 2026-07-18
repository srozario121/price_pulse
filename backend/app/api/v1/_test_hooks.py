"""Gated E2E test-control endpoints.

This router is included in the application **only** when
``settings.E2E_TEST_HOOKS`` is true (set exclusively by
``docker-compose.e2e.yml``). It exposes deterministic control hooks the
BDD step definitions use to drive the live stack without wall-clock waits:

- ``POST /_test/products/{id}/scrape-sync`` — run a scrape inline (not via the
  Celery queue) and return only after the ``PriceRecord`` is persisted and
  alerts evaluated, so steps get a definitive result with no polling.
- ``POST /_test/alerts/{id}/reset-cooldown`` — clear an alert's cooldown so a
  subsequent threshold crossing re-notifies immediately.

These endpoints are absent from the route table in every non-e2e environment
because the router is never included there.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert import PriceAlert
from app.models.product import Product
from app.scrapers.registry import get_scraper
from app.services import price_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/_test", tags=["_test-hooks"])


@router.post(
    "/products/{product_id}/scrape-sync",
    summary="[E2E] Run a scrape synchronously (inline, no Celery)",
)
async def scrape_sync(
    product_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Fetch + extract + persist for *product_id* inline, returning the result.

    Mirrors ``tasks.scrape.scrape_product`` but runs in-request so the caller
    receives the extraction outcome once the ``PriceRecord`` exists and alerts
    have been evaluated — no queue, no polling.
    """
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found",
        )

    source_type = str(product.source_type)
    scraper = await get_scraper(
        source_type,
        db,
        css_selector=product.css_selector,
        css_selector_currency=product.css_selector_currency,
    )
    scraped = await scraper.fetch(product.url)

    record = await price_service.record_price(
        product_id=product_id,
        scraped_result=scraped,
        session=db,
    )
    await db.flush()

    logger.info(
        "test_hook_scrape_sync",
        product_id=product_id,
        extraction_status=str(record.extraction_status),
    )
    return {
        "product_id": product_id,
        "price_record_id": record.id,
        "extraction_status": str(record.extraction_status),
        "price": str(record.price) if record.price is not None else None,
    }


@router.post(
    "/alerts/{alert_id}/reset-cooldown",
    summary="[E2E] Clear an alert's notification cooldown",
)
async def reset_cooldown(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Set ``notified_at`` to NULL so the alert can re-notify immediately."""
    alert = await db.scalar(select(PriceAlert).where(PriceAlert.id == alert_id))
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )

    alert.notified_at = None
    await db.flush()

    logger.info("test_hook_reset_cooldown", alert_id=alert_id)
    return {"alert_id": alert_id, "notified_at": None}
