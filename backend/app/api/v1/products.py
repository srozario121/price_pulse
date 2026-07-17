"""FastAPI route handlers for /products.

Routes
------
POST   /products              → 201 ProductRead          create product
GET    /products              → 200 PaginatedResponse     list (optional ?is_active)
GET    /products/failing      → 200 PaginatedResponse     products with all-failing latest scrapes
GET    /products/{id}         → 200 ProductRead           retrieve
PATCH  /products/{id}         → 200 ProductRead           partial update
DELETE /products/{id}         → 204 No Content            delete + cascade
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.product import Product
from app.schemas.common import FailingProductsResponse, PaginatedResponse
from app.schemas.product import (
    FailingProductRead,
    ProductCreate,
    ProductRead,
    ProductUpdate,
)
from app.services import monitoring_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/products", tags=["products"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _register_schedule_best_effort(product_id: int, source_type: str) -> None:
    """Register the per-product scrape schedule; never fail the request on error.

    Scheduling is a background concern — a transient Redis/RedBeat issue must not
    500 the user-facing create. On failure the worker's ``startup_sync_schedules``
    reconciles all active products at its next start, so this is a best-effort
    fast path, not the sole guarantee.
    """
    from app.scrapers.registry import queue_for_source_type
    from app.tasks.schedule import register_product_schedule

    try:
        register_product_schedule(
            product_id,
            settings.SCRAPE_INTERVAL_MINUTES,
            queue=queue_for_source_type(source_type),
        )
    except Exception as exc:  # noqa: BLE001 — best-effort; log and continue
        logger.warning(
            "product_schedule_registration_failed", product_id=product_id, error=str(exc)
        )


def _deregister_schedule_best_effort(product_id: int) -> None:
    """Remove the per-product scrape schedule; never fail the request on error."""
    from app.tasks.schedule import deregister_product_schedule

    try:
        deregister_product_schedule(product_id)
    except Exception as exc:  # noqa: BLE001 — best-effort; log and continue
        logger.warning(
            "product_schedule_deregistration_failed", product_id=product_id, error=str(exc)
        )


async def _get_product_or_404(product_id: int, db: AsyncSession) -> Product:
    """Return the product or raise HTTP 404."""
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found",
        )
    return product


async def _assert_url_unique(url: str, db: AsyncSession, exclude_id: int | None = None) -> None:
    """Raise HTTP 409 if *url* already belongs to a different product."""
    stmt = select(Product.id).where(Product.url == url)
    if exclude_id is not None:
        stmt = stmt.where(Product.id != exclude_id)
    conflict_id = await db.scalar(stmt)
    if conflict_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product with this URL already exists",
        )


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ProductRead,
    summary="Create a new tracked product",
)
async def create_product(
    body: ProductCreate,
    db: AsyncSession = Depends(get_db),
) -> Product:
    await _assert_url_unique(body.url, db)

    product = Product(**body.model_dump())
    db.add(product)
    await db.flush()
    await db.refresh(product)

    _register_schedule_best_effort(product.id, str(product.source_type))

    logger.info("product_created", product_id=product.id, url=product.url)
    return product


@router.get(
    "",
    response_model=PaginatedResponse[ProductRead],
    summary="List tracked products",
)
async def list_products(
    is_active: bool | None = Query(None, description="Filter by active status"),
    limit: int = Query(20, ge=1, le=100, description="Max items per page (≤ 100)"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ProductRead]:
    filters = []
    if is_active is not None:
        filters.append(Product.is_active == is_active)

    total = await db.scalar(select(func.count(Product.id)).where(*filters)) or 0

    result = await db.execute(
        select(Product)
        .where(*filters)
        .order_by(Product.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [ProductRead.model_validate(p) for p in result.scalars().all()]

    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/failing",
    response_model=FailingProductsResponse,
    summary="List products whose latest scrapes have all failed",
)
async def list_failing_products(
    min_failures: int = Query(
        3,
        ge=1,
        le=50,
        description="Flag a product only if its latest N records are all non-'ok'",
    ),
    limit: int = Query(50, ge=1, le=100, description="Max items per page (≤ 100)"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_db),
) -> FailingProductsResponse:
    """Surface active products whose crawls are quietly failing.

    A crawl that returns `extraction_failed`/`http_error`/`blocked`/`captcha` is
    recorded as a successful task, so a persistently-broken scraper never raises.
    This lists active products whose most recent `min_failures` records are all
    non-`ok`.

    Paginated: `total` is the full count of flagging products; `items` is the
    requested `limit`/`offset` slice. `limit` is bounded to ≤ 100 so the response
    envelope stays valid however many products are failing at once. `blocked_count`
    / `captcha_count` are anti-blocking aggregates across all flagged products.
    """
    failing = await monitoring_service.find_failing_products(db, min_failures=min_failures)
    page = failing[offset : offset + limit]
    items = [
        FailingProductRead(
            product=ProductRead.model_validate(f.product),
            latest_status=f.latest_status,
            latest_captured_at=f.latest_captured_at,
            last_success_at=f.last_success_at,
            failure_category=f.failure_category,
        )
        for f in page
    ]
    blocked_count = sum(1 for f in failing if f.failure_category == "blocked")
    captcha_count = sum(1 for f in failing if f.failure_category == "captcha")
    return FailingProductsResponse(
        items=items,
        total=len(failing),
        limit=limit,
        offset=offset,
        blocked_count=blocked_count,
        captcha_count=captcha_count,
    )


@router.get(
    "/{product_id}",
    response_model=ProductRead,
    summary="Retrieve a single product",
)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
) -> Product:
    return await _get_product_or_404(product_id, db)


@router.patch(
    "/{product_id}",
    response_model=ProductRead,
    summary="Partially update a product",
)
async def update_product(
    product_id: int,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
) -> Product:
    product = await _get_product_or_404(product_id, db)

    update_data = body.model_dump(exclude_unset=True)

    # Enforce URL uniqueness when changing the URL
    new_url = update_data.get("url")
    if new_url is not None and new_url != product.url:
        await _assert_url_unique(new_url, db, exclude_id=product_id)

    for field, value in update_data.items():
        setattr(product, field, value)

    await db.flush()
    await db.refresh(product)

    logger.info("product_updated", product_id=product_id, fields=list(update_data))
    return product


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product and all related records",
)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    # Verify existence (returns 404 if absent)
    await _get_product_or_404(product_id, db)

    # SQL DELETE lets the DB cascade handle child records (price_record, price_alert, …)
    await db.execute(delete(Product).where(Product.id == product_id))
    _deregister_schedule_best_effort(product_id)
    logger.info("product_deleted", product_id=product_id)
