"""Per-host selector-profile store and regeneration gating (Item 16).

The read side is what every scrape touches: ``get_active_selector`` returns the
validated, LLM-generated selector for a host, or ``None`` so extraction falls
back to its built-in selectors.

The write side is the self-healing loop: a ``selector_miss`` marks the host
``stale`` and — subject to a per-host cooldown and a bounded attempt budget —
signals that regeneration should be enqueued. Those two guards are the reason a
page that can never be healed does not turn into an unbounded stream of LLM calls.

Module-level async functions taking an explicit ``AsyncSession``, matching the
repo's service convention (no service classes).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import SelectorProfileStatus
from app.models.selector_profile import SelectorProfile
from app.schemas.scraper import LearnedSelector
from app.services.llm.schemas import SelectorSuggestion

logger = structlog.get_logger(__name__)


def host_for_url(url: str) -> str:
    """Return the normalised host key for *url* — lower-case, no leading ``www.``.

    Normalisation matters because the host is the profile's unique key: without
    it ``www.currys.co.uk`` and ``currys.co.uk`` would heal independently and each
    pay for its own generation. Regional storefronts stay distinct on purpose —
    ``amazon.co.uk`` and ``amazon.com`` ship different markup.
    """
    hostname = urlparse(url).hostname or ""
    return hostname.lower().removeprefix("www.")


async def get_profile(session: AsyncSession, host: str) -> SelectorProfile | None:
    """Return the profile row for *host*, or ``None`` if the host has none."""
    return await session.scalar(select(SelectorProfile).where(SelectorProfile.host == host))


async def get_active_selector(session: AsyncSession, host: str) -> LearnedSelector | None:
    """Return the promoted selector for *host*, or ``None``.

    ``None`` covers every "nothing usable stored" case — no row, a row awaiting
    its first successful generation, or one whose status is ``stale``/``failed``
    — so callers need only the single fallback path.
    """
    profile = await get_profile(session, host)
    if profile is None or profile.status != SelectorProfileStatus.ACTIVE:
        return None
    if not profile.price_selector:
        return None
    return LearnedSelector(
        price_selector=profile.price_selector,
        currency_selector=profile.currency_selector,
    )


async def get_or_create_profile(
    session: AsyncSession, host: str, source_type: str
) -> SelectorProfile:
    """Return the profile for *host*, creating a ``stale`` placeholder if absent.

    The row exists before any successful generation so the cooldown and attempt
    counters have somewhere to live for a host that has never healed.
    """
    profile = await get_profile(session, host)
    if profile is not None:
        return profile
    profile = SelectorProfile(
        host=host,
        source_type=source_type,
        status=SelectorProfileStatus.STALE,
        version=0,
        failed_attempts=0,
    )
    session.add(profile)
    await session.flush()
    return profile


def regeneration_allowed(profile: SelectorProfile, now: datetime) -> bool:
    """True when *profile* may attempt regeneration at *now*.

    Blocked by either guard: an exhausted attempt budget (status ``failed``, or
    ``failed_attempts`` at ``SELECTOR_MAX_REGEN_ATTEMPTS``), or an attempt made
    less than ``SELECTOR_REGEN_COOLDOWN_HOURS`` ago. A pure function so both
    boundaries are unit-testable without a database.
    """
    if profile.status == SelectorProfileStatus.FAILED:
        return False
    if profile.failed_attempts >= settings.SELECTOR_MAX_REGEN_ATTEMPTS:
        return False
    if profile.last_attempt_at is None:
        return True
    last_attempt = profile.last_attempt_at
    if last_attempt.tzinfo is None:
        # SQLite round-trips DateTime(timezone=True) as naive; treat it as UTC so
        # the comparison below cannot raise on the test/dev engine.
        last_attempt = last_attempt.replace(tzinfo=UTC)
    return now - last_attempt >= timedelta(hours=settings.SELECTOR_REGEN_COOLDOWN_HOURS)


async def mark_stale(
    session: AsyncSession,
    host: str,
    source_type: str,
    *,
    now: datetime | None = None,
) -> tuple[SelectorProfile, bool]:
    """Mark *host*'s profile stale; return it and whether regeneration may run.

    Called on a ``selector_miss`` and by the report-issue endpoint. An already
    ``failed`` host is left alone — re-marking it stale would hand it a fresh
    cooldown window and let it drift back into spending attempts.
    """
    moment = now or datetime.now(UTC)
    profile = await get_or_create_profile(session, host, source_type)
    allowed = regeneration_allowed(profile, moment)
    if profile.status == SelectorProfileStatus.ACTIVE:
        profile.status = SelectorProfileStatus.STALE
    logger.info(
        "selector_profile_marked_stale",
        host=host,
        source_type=source_type,
        status=profile.status,
        failed_attempts=profile.failed_attempts,
        regeneration_allowed=allowed,
    )
    return profile, allowed


async def record_attempt_failure(
    session: AsyncSession,
    profile: SelectorProfile,
    detail: str,
    *,
    now: datetime | None = None,
) -> SelectorProfile:
    """Count a failed generate-and-validate attempt against *profile*'s budget.

    Once the budget is spent the profile is parked as ``failed`` so the host stops
    costing LLM calls; a user report is then the only way to revive it.
    """
    profile.failed_attempts += 1
    profile.last_attempt_at = now or datetime.now(UTC)
    profile.detail = detail
    if profile.failed_attempts >= settings.SELECTOR_MAX_REGEN_ATTEMPTS:
        profile.status = SelectorProfileStatus.FAILED
    await session.flush()
    logger.warning(
        "selector_regeneration_attempt_failed",
        host=profile.host,
        failed_attempts=profile.failed_attempts,
        status=profile.status,
        detail=detail,
    )
    return profile


async def promote(
    session: AsyncSession,
    profile: SelectorProfile,
    suggestion: SelectorSuggestion,
    *,
    provider: str,
    model: str,
    now: datetime | None = None,
) -> SelectorProfile:
    """Store a *validated* suggestion as the host's new active selector.

    Only ever called after the selector has actually extracted a plausible price
    from the live page, so an ``active`` profile is always a proven one. Bumps the
    version and clears the failure budget — the host is healed.
    """
    moment = now or datetime.now(UTC)
    profile.price_selector = suggestion.price_selector
    profile.currency_selector = suggestion.currency_selector
    profile.confidence = suggestion.confidence
    profile.status = SelectorProfileStatus.ACTIVE
    profile.version += 1
    profile.generated_by_provider = provider
    profile.generated_by_model = model
    profile.generated_at = moment
    profile.last_validated_at = moment
    profile.last_attempt_at = moment
    profile.failed_attempts = 0
    profile.detail = None
    await session.flush()
    logger.info(
        "selector_profile_promoted",
        host=profile.host,
        version=profile.version,
        confidence=suggestion.confidence,
        provider=provider,
        model=model,
    )
    return profile


async def revive_for_report(
    session: AsyncSession, host: str, source_type: str
) -> tuple[SelectorProfile, bool]:
    """Handle a user report of a bad price for *host*.

    A report is a human asserting the stored selector is wrong, so it clears a
    spent attempt budget — otherwise a host parked as ``failed`` could never be
    healed again. The cooldown still applies, so repeated reports inside the
    window do not enqueue duplicate work.
    """
    profile = await get_or_create_profile(session, host, source_type)
    if profile.status == SelectorProfileStatus.FAILED:
        profile.failed_attempts = 0
        profile.status = SelectorProfileStatus.STALE
        await session.flush()
    return await mark_stale(session, host, source_type)
