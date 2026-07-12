"""Monitoring queries over scrape outcomes.

A crawl that keeps returning ``extraction_failed`` / ``http_error`` is recorded
as a *successful Celery task* (the status is persisted, not raised), so a
product whose scraper is quietly broken — e.g. permanently CAPTCHA-walled —
never surfaces as an error. ``find_failing_products`` detects that: an active
product whose most recent ``min_failures`` price records are all non-``ok``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ExtractionStatus
from app.models.price_history import PriceRecord
from app.models.product import Product

_OK = ExtractionStatus.OK.value


@dataclass(frozen=True)
class FailingProduct:
    """An active product whose latest scrapes have all failed extraction."""

    product: Product
    latest_status: str
    latest_captured_at: datetime
    last_success_at: datetime | None


async def find_failing_products(
    session: AsyncSession,
    *,
    min_failures: int = 3,
) -> list[FailingProduct]:
    """Return active products whose latest *min_failures* records are all non-``ok``.

    A product is flagged only once it has at least *min_failures* records and the
    most recent *min_failures* of them are all failures — so a single transient
    failure (or a brand-new product) is not reported.
    """
    if min_failures < 1:
        raise ValueError(f"min_failures must be >= 1, got {min_failures}")

    # Rank each product's records newest-first (id breaks captured_at ties).
    rn = func.row_number().over(
        partition_by=PriceRecord.product_id,
        order_by=(PriceRecord.captured_at.desc(), PriceRecord.id.desc()),
    ).label("rn")
    ranked = select(
        PriceRecord.product_id.label("product_id"),
        PriceRecord.extraction_status.label("status"),
        PriceRecord.captured_at.label("captured_at"),
        rn,
    ).subquery()

    # product_ids whose latest `min_failures` records exist and are all non-ok.
    failing_ids = (
        select(ranked.c.product_id)
        .where(ranked.c.rn <= min_failures)
        .group_by(ranked.c.product_id)
        .having(func.count() == min_failures)
        .having(func.sum(case((ranked.c.status == _OK, 1), else_=0)) == 0)
        .scalar_subquery()
    )

    # Active products in that set.
    products = (
        (
            await session.execute(
                select(Product)
                .where(Product.id.in_(failing_ids), Product.is_active.is_(True))
                .order_by(Product.id)
            )
        )
        .scalars()
        .all()
    )
    if not products:
        return []

    ids = [p.id for p in products]

    # Latest record (status + time) per flagged product.
    latest_rows = (
        await session.execute(
            select(ranked.c.product_id, ranked.c.status, ranked.c.captured_at).where(
                ranked.c.rn == 1, ranked.c.product_id.in_(ids)
            )
        )
    ).all()
    latest = {pid: (status, captured_at) for pid, status, captured_at in latest_rows}

    # Most recent successful scrape per flagged product (may be absent).
    success_rows = (
        await session.execute(
            select(PriceRecord.product_id, func.max(PriceRecord.captured_at))
            .where(PriceRecord.product_id.in_(ids), PriceRecord.extraction_status == _OK)
            .group_by(PriceRecord.product_id)
        )
    ).all()
    last_success = {pid: ts for pid, ts in success_rows}

    return [
        FailingProduct(
            product=p,
            latest_status=latest[p.id][0],
            latest_captured_at=latest[p.id][1],
            last_success_at=last_success.get(p.id),
        )
        for p in products
    ]
