"""The single implementation of "scrape one product and record the result".

Two callers run a scrape: the ``scrape_product`` Celery task (production) and the
gated ``/_test/products/{id}/scrape-sync`` hook (the E2E harness, which needs the
outcome in-request rather than via a queue). They had *copies* of the same body,
and the copies drifted: the hook was written before Item 16 and never learned to
pass the host's healed selector, so the E2E stack could promote a selector and
then keep recording ``selector_miss`` forever — the healed path was untestable
through the very harness built to test it.

Keeping one implementation here means the harness necessarily exercises the same
code production runs, which is the only way an E2E test can be evidence about
production behaviour.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ExtractionStatus
from app.models.price_history import PriceRecord
from app.models.product import Product
from app.scrapers.registry import get_scraper
from app.services import price_service, selector_profile_service

logger = structlog.get_logger(__name__)


async def _handle_selector_miss(
    session: AsyncSession,
    host: str,
    source_type: str,
    product_id: int,
) -> None:
    """Mark *host* stale and enqueue selector regeneration if the guards allow it.

    Fully guarded: self-healing is a background improvement, so a broker hiccup or
    a bookkeeping error must never fail — or retry — the scrape that already
    recorded its result. The cooldown and attempt budget live in
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


async def run_scrape(session: AsyncSession, product: Product) -> PriceRecord:
    """Fetch *product*'s page, persist the outcome, and trigger healing on drift.

    Does **not** commit — the caller owns the transaction boundary (the Celery
    task commits; the API hook flushes and lets the request-scoped session
    commit).
    """
    source_type = str(product.source_type)
    host = selector_profile_service.host_for_url(product.url)

    # The host's healed selector, if one has been generated and validated
    # (Item 16). None ⇒ the scraper uses its built-in selectors only.
    learned = await selector_profile_service.get_stored_selector(session, host)

    # Resolve the scraper from the DB-backed preset registry. The registry only
    # forwards the CSS-selector kwargs to selector-based strategies (generic);
    # other strategies ignore them.
    scraper = await get_scraper(
        source_type,
        session,
        css_selector=product.css_selector,
        css_selector_currency=product.css_selector_currency,
        learned_selector=learned,
    )
    scraped = await scraper.fetch(product.url)

    record = await price_service.record_price(
        product_id=int(product.id),
        scraped_result=scraped,
        session=session,
    )

    # Selector drift: the page loaded, was not blocked, and still yielded no
    # price. Mark the host stale and enqueue regeneration off the scrape path —
    # the existing selectors keep serving meanwhile.
    if scraped.extraction_status == ExtractionStatus.SELECTOR_MISS:
        await _handle_selector_miss(session, host, source_type, int(product.id))

    return record
