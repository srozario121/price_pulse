"""Celery task: regenerate_selector — heal a host's price selector (Item 16).

Runs **off the scrape path**, on the ``playwright`` worker (where the LLM
credentials are injected and a browser is available to re-render the page). The
old selectors keep serving while this runs, so a drift event degrades one scrape
cycle rather than blocking on provider availability.

The task never raises and never retries. Every failure mode — generation
disabled, provider error, a suggestion that will not validate — is recorded as a
counted attempt against the host's budget and returns a status string. Retrying
would double-charge the provider for a page that is, by construction, currently
unparseable; the per-host cooldown is the retry mechanism.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.enums import ExtractionStatus
from app.models.product import Product
from app.models.selector_profile import SelectorProfile
from app.schemas.scraper import LearnedSelector, ScrapedResult
from app.scrapers.registry import get_scraper
from app.services import selector_generation, selector_profile_service
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

# Statuses that mean "this page cannot teach us anything". Generating a selector
# from a CAPTCHA interstitial or an error page would poison the profile with a
# selector matching the block page, so those outcomes abort before the LLM call.
_UNUSABLE_FOR_GENERATION = frozenset(
    {
        ExtractionStatus.BLOCKED,
        ExtractionStatus.CAPTCHA,
        ExtractionStatus.HTTP_ERROR,
    }
)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.tasks.selector.regenerate_selector",
    max_retries=0,
)
async def regenerate_selector(product_id: int) -> str:
    """Generate, validate and promote a new price selector for *product_id*'s host.

    Returns a short status string describing the outcome: ``promoted``,
    ``not_found``, ``cooldown``, ``disabled``, ``unusable_page``,
    ``generation_failed`` or ``validation_failed``.
    """
    async with AsyncSessionLocal() as session:
        product = await session.scalar(select(Product).where(Product.id == product_id))
        if product is None:
            logger.warning("regenerate_selector_product_not_found", product_id=product_id)
            return "not_found"

        host = selector_profile_service.host_for_url(product.url)
        source_type = str(product.source_type)
        profile = await selector_profile_service.get_or_create_profile(session, host, source_type)

        # Re-check the guards here, not only at enqueue time: several products on
        # the same host can miss in the same cycle and each enqueue a job, and the
        # first one to run consumes the window for the rest.
        if not selector_profile_service.regeneration_allowed(profile, datetime.now(UTC)):
            await session.commit()
            logger.info("regenerate_selector_skipped", host=host, status=profile.status)
            return "cooldown"

        outcome = await _attempt_regeneration(session, product, profile, host, source_type)
        await session.commit()
        return outcome


async def _attempt_regeneration(
    session: AsyncSession,
    product: Product,
    profile: SelectorProfile,
    host: str,
    source_type: str,
) -> str:
    """Fetch the page, generate a selector, validate it, and promote on success."""
    scraped = await _refetch(session, product, profile, source_type)
    if scraped is None or scraped.extraction_status in _UNUSABLE_FOR_GENERATION:
        status = scraped.extraction_status.value if scraped is not None else "fetch_error"
        await selector_profile_service.record_attempt_failure(
            session, profile, f"page unusable for generation: {status}"
        )
        return "unusable_page"

    try:
        generated = await selector_generation.generate_selector(session, product, scraped.html)
    except selector_generation.SelectorGenerationError as exc:
        await selector_profile_service.record_attempt_failure(session, profile, str(exc))
        return "generation_failed"

    if generated is None:
        # No credential resolved. Not a failure of *this* host — counting it would
        # burn every host's budget while the deployment simply has no key — so the
        # attempt is not recorded and nothing is parked as failed.
        logger.info("regenerate_selector_disabled", host=host, product_id=product.id)
        return "disabled"

    suggestion, config = generated
    price = selector_generation.validate_selector(scraped.html, suggestion.price_selector)
    if price is None:
        await selector_profile_service.record_attempt_failure(
            session,
            profile,
            f"selector {suggestion.price_selector!r} extracted no plausible price",
        )
        return "validation_failed"

    await selector_profile_service.promote(
        session, profile, suggestion, provider=config.provider, model=config.model
    )
    logger.info(
        "selector_regeneration_promoted",
        host=host,
        product_id=product.id,
        validated_price=str(price),
        selector=suggestion.price_selector,
    )
    return "promoted"


async def _refetch(
    session: AsyncSession,
    product: Product,
    profile: SelectorProfile,
    source_type: str,
) -> ScrapedResult | None:
    """Re-fetch *product*'s page for generation, or ``None`` if the fetch errored.

    The profile's *previous* selector is passed through even though it is stale:
    the fetch only needs to reach the page, and ``GenericScraper`` refuses to run
    with no selector at all. The returned status is used solely to reject block /
    error pages — a stale selector missing again is exactly the expected outcome.
    """
    previous = (
        LearnedSelector(
            price_selector=profile.price_selector,
            currency_selector=profile.currency_selector,
        )
        if profile.price_selector
        else None
    )
    try:
        scraper = await get_scraper(
            source_type,
            session,
            css_selector=product.css_selector,
            css_selector_currency=product.css_selector_currency,
            learned_selector=previous,
        )
        return await scraper.fetch(product.url)
    except Exception as exc:  # noqa: BLE001 — a fetch failure is a counted attempt
        logger.warning(
            "regenerate_selector_fetch_failed",
            product_id=product.id,
            url=product.url,
            error=str(exc),
        )
        return None
