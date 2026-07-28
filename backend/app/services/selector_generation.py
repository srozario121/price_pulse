"""LLM selector generation and validation (Item 16).

Three steps, deliberately separate so each is testable on its own:

``trim_html``
    Strip the parts of a page that cannot contain a rendered price (scripts,
    styles, SVG, comments) and cap the payload. Product pages routinely exceed a
    megabyte, almost all of it inline JS — sending it raw would be slow, costly,
    and would push the actual markup out of the model's attention.

``generate_selector``
    One Pydantic AI run with ``output_type=SelectorSuggestion``. Returns ``None``
    when no credential resolves (generation disabled) and raises nothing the
    caller has to handle beyond ``SelectorGenerationError``.

``validate_selector``
    The gate before anything is stored: a suggestion is only promoted if it
    actually extracts a plausible numeric price from the page it was generated
    from. Model confidence alone is never enough.
"""

from __future__ import annotations

import re
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.product import Product
from app.scrapers.playwright_base import _normalize_price_text
from app.services.llm.client import (
    LLMConfig,
    LLMConfigError,
    build_model,
    resolve_llm_config,
    selector_agent,
)
from app.services.llm.schemas import SelectorSuggestion

logger = structlog.get_logger(__name__)

# Elements that can never hold a visible price. Removed whole (tag + content) so
# the model sees markup, not megabytes of bundled JavaScript.
_STRIP_ELEMENTS = ("script", "style", "svg", "noscript", "template")
_STRIP_PATTERNS = tuple(
    re.compile(rf"<{tag}\b[^>]*>.*?</{tag}>", re.IGNORECASE | re.DOTALL) for tag in _STRIP_ELEMENTS
)
_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
_WHITESPACE_PATTERN = re.compile(r"[ \t]*\n[ \t\n]*")

# A promoted selector must extract a price inside this range. Guards against a
# selector that matches a review count, a "0" placeholder, or an order total.
_MIN_PLAUSIBLE_PRICE = Decimal("0.01")
_MAX_PLAUSIBLE_PRICE = Decimal("1000000")


class SelectorGenerationError(RuntimeError):
    """Generation could not produce a usable suggestion (provider or config error)."""


def trim_html(html: str, max_bytes: int | None = None) -> str:
    """Return *html* with non-price elements removed and capped at *max_bytes*.

    The cap counts UTF-8 bytes (what the wire and the tokenizer see) and truncates
    on a character boundary. Defaults to ``settings.SELECTOR_HTML_MAX_BYTES``.
    """
    limit = settings.SELECTOR_HTML_MAX_BYTES if max_bytes is None else max_bytes

    cleaned = html
    for pattern in _STRIP_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = _COMMENT_PATTERN.sub("", cleaned)
    cleaned = _WHITESPACE_PATTERN.sub("\n", cleaned).strip()

    encoded = cleaned.encode("utf-8")
    if len(encoded) <= limit:
        return cleaned
    return encoded[:limit].decode("utf-8", errors="ignore")


def validate_selector(html: str, selector: str) -> Decimal | None:
    """Return the price *selector* extracts from *html*, or ``None`` if it fails.

    Used as the promotion gate. Reuses the shared locale-aware
    ``_normalize_price_text`` so a generated selector is held to exactly the same
    parsing standard as the built-in ones, and rejects values outside a plausible
    retail range.

    This is a *plausibility* gate, not a correctness proof: a selector aimed at,
    say, a review count would still extract a plausible number. Targeting the
    right element is the model's job (steered by the agent instructions); what
    this rules out is the far commoner failure — a hallucinated selector that
    matches nothing, or matches text with no price in it — which is what would
    otherwise silently replace a working selector with a broken one.
    """
    from parsel import Selector

    try:
        matches = Selector(text=html).css(selector)
    except Exception as exc:  # noqa: BLE001 — any malformed selector is a failure
        logger.info("selector_validation_bad_selector", selector=selector, error=str(exc))
        return None

    for match in matches:
        text = "".join(match.css("::text").getall()) or (match.get() or "")
        price = _normalize_price_text(text)
        if price is not None and _MIN_PLAUSIBLE_PRICE <= price <= _MAX_PLAUSIBLE_PRICE:
            return price
    return None


def _build_prompt(url: str, html: str) -> str:
    return (
        f"Product page URL: {url}\n\n"
        "Trimmed HTML of the page follows. Return the CSS selector for its "
        "current purchasable price.\n\n"
        f"{html}"
    )


async def generate_selector(
    session: AsyncSession,
    product: Product,
    html: str,
) -> tuple[SelectorSuggestion, LLMConfig] | None:
    """Generate a price selector for *product*'s page, or ``None`` if disabled.

    Returns the validated-by-schema suggestion together with the config that
    produced it, so the caller can record which provider/model to credit (or
    blame). ``None`` means no credential resolved — the documented "generation
    off" state, not an error.

    Raises ``SelectorGenerationError`` when a credential *did* resolve but the
    provider call failed, so the caller can count it against the attempt budget.
    """
    config = await resolve_llm_config(session, product)
    if config is None:
        logger.info("selector_generation_disabled", product_id=product.id, url=product.url)
        return None

    try:
        model = build_model(config)
    except LLMConfigError as exc:
        raise SelectorGenerationError(f"LLM configuration error: {exc}") from exc

    trimmed = trim_html(html)
    try:
        result = await selector_agent.run(_build_prompt(product.url, trimmed), model=model)
    except Exception as exc:  # noqa: BLE001 — provider/network/timeout/validation
        # Deliberately broad: every provider raises its own error taxonomy, and a
        # failed generation must always be a counted attempt, never a crash that
        # kills the worker or the scrape that triggered it.
        raise SelectorGenerationError(
            f"{config.provider} generation failed: {type(exc).__name__}: {exc}"
        ) from exc

    logger.info(
        "selector_generation_complete",
        product_id=product.id,
        provider=config.provider,
        model=config.model,
        credential_source=config.source,
        confidence=result.output.confidence,
    )
    return result.output, config
