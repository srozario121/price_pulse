"""Price service — deduplication, persistence, and alert evaluation trigger."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ExtractionStatus
from app.models.price_history import PriceRecord
from app.schemas.scraper import ScrapedResult
from app.services import alert_service

logger = structlog.get_logger()


def _is_duplicate(latest: PriceRecord | None, scraped_result: ScrapedResult) -> bool:
    return (
        latest is not None
        and bool(scraped_result.html_hash)
        and latest.raw_html_hash is not None
        and latest.raw_html_hash == scraped_result.html_hash
    )


async def record_price(
    product_id: int,
    scraped_result: ScrapedResult,
    session: AsyncSession,
) -> PriceRecord:
    """Persist a price observation, deduplicate by HTML hash, and evaluate alerts.

    Deduplication: if the most recent PriceRecord for *product_id* has the same
    html_hash as *scraped_result.html_hash* (and the hash is non-empty), the
    existing record is returned without inserting a new row.

    Alert evaluation is called only when extraction_status is OK.
    """
    stmt = (
        select(PriceRecord)
        .where(PriceRecord.product_id == product_id)
        .order_by(PriceRecord.captured_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    latest = result.scalar_one_or_none()

    if _is_duplicate(latest, scraped_result):
        logger.info(
            "price_record_deduplicated",
            product_id=product_id,
            html_hash=scraped_result.html_hash,
        )
        return latest  # type: ignore[return-value]

    new_record = PriceRecord(
        product_id=product_id,
        price=scraped_result.price,
        currency=scraped_result.currency,
        raw_html_hash=scraped_result.html_hash if scraped_result.html_hash else None,
        extraction_status=scraped_result.extraction_status.value,
    )
    session.add(new_record)
    await session.flush()

    logger.info(
        "price_record_created",
        product_id=product_id,
        price=str(scraped_result.price),
        extraction_status=scraped_result.extraction_status.value,
    )

    if scraped_result.extraction_status == ExtractionStatus.OK:
        await alert_service.evaluate_alerts(product_id, session)

    return new_record
