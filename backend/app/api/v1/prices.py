"""FastAPI route handlers for price history and on-demand scraping.

Routes
------
GET  /products/{id}/prices  → 200 PaginatedResponse[PriceRecordRead]  price history
POST /products/{id}/scrape  → 202 ScrapeJobResponse                   trigger scrape job
"""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.price_history import PriceRecord
from app.models.product import Product
from app.schemas.common import PaginatedResponse, ScrapeJobResponse
from app.schemas.price import PriceRecordRead
from app.schemas.product import ProductRead
from app.scrapers.registry import queue_for_source_type
from app.tasks.scrape import scrape_product

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["prices"])


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_product_or_404(product_id: int, db: AsyncSession) -> Product:
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found",
        )
    return product


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get(
    "/products/{product_id}/prices",
    response_model=PaginatedResponse[PriceRecordRead],
    summary="Paginated price history for a product",
)
async def list_prices(
    product_id: int,
    limit: int = Query(20, ge=1, le=100, description="Max items per page (≤ 100)"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    from_dt: datetime | None = Query(None, description="ISO 8601 lower bound (inclusive)"),
    to_dt: datetime | None = Query(None, description="ISO 8601 upper bound (inclusive)"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[PriceRecordRead]:
    await _get_product_or_404(product_id, db)

    # Build filter list
    filters = [PriceRecord.product_id == product_id]
    if from_dt is not None:
        filters.append(PriceRecord.captured_at >= from_dt)
    if to_dt is not None:
        filters.append(PriceRecord.captured_at <= to_dt)

    total = await db.scalar(select(func.count(PriceRecord.id)).where(*filters)) or 0

    result = await db.execute(
        select(PriceRecord)
        .where(*filters)
        .order_by(PriceRecord.captured_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [PriceRecordRead.model_validate(r) for r in result.scalars().all()]

    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/products/{product_id}/scrape",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ScrapeJobResponse,
    summary="Trigger an on-demand price scrape for a product",
)
async def trigger_scrape(
    product_id: int,
    db: AsyncSession = Depends(get_db),
) -> ScrapeJobResponse:
    product = await _get_product_or_404(product_id, db)

    if not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product is not active",
        )

    # Route to the queue whose worker can run this source type's scraper,
    # resolved from the source's preset (browser sources → the Playwright worker).
    queue = await queue_for_source_type(str(product.source_type), db)
    # The pp_trigger header lets the before_task_publish signal (Item 17) mark
    # this ScrapeJob as on-demand; scheduled RedBeat dispatches carry no header
    # and default to "scheduled".
    task = scrape_product.apply_async(
        (product_id,), queue=queue, headers={"pp_trigger": "on_demand"}
    )
    logger.info("scrape_job_queued", product_id=product_id, task_id=task.id, queue=queue)

    return ScrapeJobResponse(
        task_id=str(task.id),
        status="queued",
        product=ProductRead.model_validate(product),
    )
