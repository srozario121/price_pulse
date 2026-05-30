"""Celery task: scrape_product — fetch price for a single product.

Design decisions:
- bind=True: gives the task access to self.retry() and self.request.retries.
- Retry policy: max_retries=3, exponential countdown (2**retries seconds).
- Amazon routing: dispatched to 'playwright' queue when source_type=amazon.
- Session: each invocation opens its own AsyncSessionLocal context; no shared
  session across tasks.
- ScraperError and any unexpected exception both trigger a retry; after
  max_retries, a structlog ERROR is emitted with full exception info.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.product import Product
from app.scrapers.registry import SourceType, get_scraper
from app.services import price_service
from app.workers.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="app.tasks.scrape.scrape_product",
    max_retries=3,
    acks_late=True,
)
async def scrape_product(self: object, product_id: int) -> str:
    """Fetch and store the current price for *product_id*.

    Returns the extraction_status string of the resulting PriceRecord.
    Retries up to 3 times on any exception with exponential back-off.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Fetch product
            stmt = select(Product).where(Product.id == product_id)
            result = await session.execute(stmt)
            product = result.scalar_one_or_none()

            if product is None:
                logger.warning("scrape_product_not_found", product_id=product_id)
                return "not_found"

            source_type = str(product.source_type)

            # Build scraper kwargs
            kwargs: dict[str, object] = {}
            if source_type == SourceType.GENERIC:
                kwargs["css_selector"] = product.css_selector
                kwargs["css_selector_currency"] = product.css_selector_currency

            scraper = get_scraper(source_type, **kwargs)
            scraped = await scraper.fetch(product.url)

            # Persist result
            record = await price_service.record_price(
                product_id=product_id,
                scraped_result=scraped,
                session=session,
            )
            await session.commit()

            logger.info(
                "scrape_product_complete",
                product_id=product_id,
                extraction_status=record.extraction_status,
            )
            return str(record.extraction_status)

    except Exception as exc:
        retry_request = getattr(self, "request", None)
        retries = getattr(retry_request, "retries", 0) if retry_request else 0
        countdown = 2**retries

        logger.warning(
            "scrape_product_retry",
            product_id=product_id,
            retries=retries,
            countdown=countdown,
            exc=str(exc),
        )

        try:
            raise self.retry(exc=exc, countdown=countdown)  # type: ignore[attr-defined]
        except self.MaxRetriesExceededError:  # type: ignore[attr-defined]
            logger.error(
                "scrape_product_max_retries_exceeded",
                product_id=product_id,
                exc=str(exc),
                exc_info=True,
            )
            raise
