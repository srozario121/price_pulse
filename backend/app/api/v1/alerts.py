"""FastAPI route handlers for /alerts.

Routes
------
POST   /alerts                    → 201 AlertRead            create alert
GET    /alerts                    → 200 PaginatedResponse     list (optional ?product_id, ?is_active)
GET    /alerts/{id}               → 200 AlertRead             retrieve
PATCH  /alerts/{id}               → 200 AlertRead             partial update (product_id forbidden)
DELETE /alerts/{id}               → 204 No Content            delete
GET    /alerts/{id}/notifications → 200 PaginatedResponse     notification delivery history

Design notes
------------
- ``product_id`` is read-only after creation; ``AlertUpdate`` has ``extra="forbid"``
  so passing it in a PATCH body returns 422.
- Ordered by ``id ASC`` (insertion order) — alerts have no natural recency ordering.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert import PriceAlert
from app.models.notification_log import NotificationLog
from app.models.product import Product
from app.schemas.alert import AlertCreate, AlertRead, AlertUpdate
from app.schemas.common import PaginatedResponse
from app.schemas.notification import NotificationLogRead

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_alert_or_404(alert_id: int, db: AsyncSession) -> PriceAlert:
    alert = await db.scalar(select(PriceAlert).where(PriceAlert.id == alert_id))
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found",
        )
    return alert


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AlertRead,
    summary="Create a price alert for a product",
)
async def create_alert(
    body: AlertCreate,
    db: AsyncSession = Depends(get_db),
) -> PriceAlert:
    # Verify the referenced product exists
    product_exists = await db.scalar(select(Product.id).where(Product.id == body.product_id))
    if product_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {body.product_id} not found",
        )

    alert = PriceAlert(**body.model_dump())
    db.add(alert)
    await db.flush()
    await db.refresh(alert)

    logger.info("alert_created", alert_id=alert.id, product_id=alert.product_id)
    return alert


@router.get(
    "",
    response_model=PaginatedResponse[AlertRead],
    summary="List price alerts",
)
async def list_alerts(
    product_id: int | None = Query(None, description="Filter alerts by product"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    limit: int = Query(20, ge=1, le=100, description="Max items per page (≤ 100)"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[AlertRead]:
    filters = []
    if product_id is not None:
        filters.append(PriceAlert.product_id == product_id)
    if is_active is not None:
        filters.append(PriceAlert.is_active == is_active)

    total = await db.scalar(select(func.count(PriceAlert.id)).where(*filters)) or 0

    result = await db.execute(
        select(PriceAlert).where(*filters).order_by(PriceAlert.id.asc()).limit(limit).offset(offset)
    )
    items = [AlertRead.model_validate(a) for a in result.scalars().all()]

    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{alert_id}",
    response_model=AlertRead,
    summary="Retrieve a single alert",
)
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
) -> PriceAlert:
    return await _get_alert_or_404(alert_id, db)


@router.patch(
    "/{alert_id}",
    response_model=AlertRead,
    summary="Partially update an alert (product_id is immutable)",
)
async def update_alert(
    alert_id: int,
    body: AlertUpdate,
    db: AsyncSession = Depends(get_db),
) -> PriceAlert:
    alert = await _get_alert_or_404(alert_id, db)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(alert, field, value)

    await db.flush()
    await db.refresh(alert)

    logger.info("alert_updated", alert_id=alert_id, fields=list(update_data))
    return alert


@router.delete(
    "/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a price alert",
)
async def delete_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_alert_or_404(alert_id, db)
    await db.execute(delete(PriceAlert).where(PriceAlert.id == alert_id))
    logger.info("alert_deleted", alert_id=alert_id)


@router.get(
    "/{alert_id}/notifications",
    response_model=PaginatedResponse[NotificationLogRead],
    summary="List notification delivery history for an alert",
)
async def list_alert_notifications(
    alert_id: int,
    limit: int = Query(20, ge=1, le=100, description="Max items per page (≤ 100)"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[NotificationLogRead]:
    """Return this alert's ``NotificationLog`` rows, most-recent first.

    Exposes notification deliveries (email/webhook/whatsapp) through the public
    API so E2E behaviour scenarios can assert delivery without touching the DB.
    """
    await _get_alert_or_404(alert_id, db)

    total = (
        await db.scalar(
            select(func.count(NotificationLog.id)).where(NotificationLog.alert_id == alert_id)
        )
        or 0
    )

    result = await db.execute(
        select(NotificationLog)
        .where(NotificationLog.alert_id == alert_id)
        .order_by(NotificationLog.sent_at.desc(), NotificationLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [NotificationLogRead.model_validate(n) for n in result.scalars().all()]

    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)
