"""FastAPI route handlers for /products.

Routes
------
POST   /products              → 201 ProductRead          create product
GET    /products              → 200 PaginatedResponse     list (optional ?is_active)
GET    /products/{id}         → 200 ProductRead           retrieve
PATCH  /products/{id}         → 200 ProductRead           partial update
DELETE /products/{id}         → 204 No Content            delete + cascade
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.product import Product
from app.schemas.common import PaginatedResponse
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/products", tags=["products"])


# ── Helpers ───────────────────────────────────────────────────────────────────


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
    logger.info("product_deleted", product_id=product_id)
