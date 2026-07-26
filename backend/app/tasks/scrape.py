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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.enums import ExtractionStatus
from app.models.product import Product
from app.scrapers.registry import get_scraper
from app.services import price_service, selector_profile_service
from app.workers.celery_app import celery_app

logger = structlog.get_logger()


async def _handle_selector_miss(
    session: AsyncSession,
    host: str,
    source_type: str,
    product_id: int,
) -> None:
    """Mark *host* stale and enqueue selector regeneration if the guards allow it.

    Fully guarded: self-healing is a background improvement, so a Redis hiccup or
    a regeneration bookkeeping error must never fail — or retry — the scrape that
    already recorded its result. The cooldown and attempt budget live in
    ``selector_profile_service``; this only dispatches when they say to.
    """
    try:
        _, allowed = await selector_profile_service.mark_stale(session, host, source_type)
        if not allowed:
            return
        from app.tasks.selector import regenerate_selector

        regenerate_selector.apply_async(args=[product_id], queue="playwright")
        logger.info("selector_regeneration_enqueued", host=host, product_id=product_id)
    except Exception as exc:  # noqa: BLE001 — never fail a completed scrape
        logger.warning(
            "selector_regeneration_enqueue_failed",
            host=host,
            product_id=product_id,
            error=str(exc),
        )


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
            host = selector_profile_service.host_for_url(product.url)

            # The host's healed selector, if one has been generated and validated
            # (Item 16). None ⇒ the scraper uses its built-in selectors only.
            learned = await selector_profile_service.get_active_selector(session, host)

            # Resolve the scraper from the DB-backed preset registry. The registry
            # only forwards the CSS-selector kwargs to selector-based strategies
            # (generic); other strategies ignore them.
            scraper = await get_scraper(
                source_type,
                session,
                css_selector=product.css_selector,
                css_selector_currency=product.css_selector_currency,
                learned_selector=learned,
            )
            scraped = await scraper.fetch(product.url)

            # Persist result
            record = await price_service.record_price(
                product_id=product_id,
                scraped_result=scraped,
                session=session,
            )

            # Selector drift: the page loaded, was not blocked, and still yielded
            # no price. Mark the host stale and enqueue regeneration off the
            # scrape path — the existing selectors keep serving meanwhile.
            if scraped.extraction_status == ExtractionStatus.SELECTOR_MISS:
                await _handle_selector_miss(session, host, source_type, product_id)

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
