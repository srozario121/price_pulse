"""Shared async HTTP client with retry, rate-limiting, and robots.txt support."""

from __future__ import annotations

import asyncio
import hashlib
import urllib.robotparser
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
import structlog

from app.core.config import settings
from app.models.enums import ExtractionStatus
from app.schemas.scraper import ScrapedResult
from app.scrapers.anti_blocking import (
    ProxyRotator,
    build_headers,
    choose_user_agent,
    classify_block,
    normalise_proxy,
)

logger = structlog.get_logger()

_RETRY_BACK_OFF: list[float] = [1.0, 2.0, 4.0]
_MAX_RETRIES = 3
_DEFAULT_RETRY_AFTER = 60

# Outcomes of a single-proxy fetch attempt, interpreted by fetch_page's rotation
# loop. ROTATE_* are only ever returned when a proxy is actually in use.
_ACTION_RETURN = "return"  # terminal result (ok / http_error / blocked-no-proxy)
_ACTION_ROTATE_BLOCK = "rotate_block"  # block detected — rotate proxy, consume block budget
_ACTION_ROTATE_DEAD = "rotate_dead"  # proxy unreachable — rotate proxy, do not consume budget


def _extract_domain(url: str) -> str:
    return urlparse(url).netloc


def _compute_hash(html: str) -> str:
    return hashlib.sha256(html.encode()).hexdigest()


def _error_result(url: str) -> ScrapedResult:
    return ScrapedResult(
        url=url,
        html="",
        html_hash="",
        price=None,
        currency=None,
        scraped_at=datetime.now(UTC),
        extraction_status=ExtractionStatus.HTTP_ERROR,
    )


async def _fetch_robots_text(
    domain: str,
    robots_url: str,
    redis_client: object | None,
) -> str:
    cache_key = f"robots:{domain}"

    if redis_client is not None:
        try:
            cached = await redis_client.get(cache_key)  # type: ignore[attr-defined]
            if cached is not None:
                return cached if isinstance(cached, str) else cached.decode()
        except Exception:
            pass  # Redis failure is non-fatal

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(robots_url)
            robots_text = response.text if response.status_code == 200 else ""
    except Exception:
        robots_text = ""

    if redis_client is not None:
        try:
            await redis_client.set(cache_key, robots_text, ex=3600)  # type: ignore[attr-defined]
        except Exception:
            pass

    return robots_text


def _log_if_disallowed(url: str, robots_url: str, robots_text: str) -> None:
    if not robots_text:
        return
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots_text.splitlines())
    parsed = urlparse(url)
    path = parsed.path or "/"
    if not rp.can_fetch("*", url):
        logger.warning("robots_txt_disallowed", url=url, path=path, robots_url=robots_url)


async def _check_robots(url: str, redis_client: object | None) -> None:
    """Fetch and parse robots.txt; log WARNING if path is disallowed (log-and-proceed)."""
    parsed = urlparse(url)
    domain = parsed.netloc
    robots_url = f"{parsed.scheme}://{domain}/robots.txt"
    robots_text = await _fetch_robots_text(domain, robots_url, redis_client)
    _log_if_disallowed(url, robots_url, robots_text)


async def _apply_rate_limit(domain: str, redis_client: object | None) -> None:
    """Sleep if a rate-limit key for *domain* exists in Redis; then set the key."""
    if redis_client is None:
        return
    cache_key = f"rate_limit:{domain}"
    try:
        exists = await redis_client.get(cache_key)  # type: ignore[attr-defined]
        if exists is not None:
            await asyncio.sleep(settings.SCRAPE_MIN_DELAY_SECONDS)
        await redis_client.set(  # type: ignore[attr-defined]
            cache_key, "1", ex=settings.SCRAPE_MIN_DELAY_SECONDS
        )
    except Exception:
        pass  # Redis failure is non-fatal


def _result_for_status(
    url: str,
    response: httpx.Response,
    attempt: int,
) -> ScrapedResult | None:
    """Return a final ScrapedResult for non-retryable statuses, None to continue."""
    status = response.status_code
    if status == 200:
        html = response.text
        return ScrapedResult(
            url=url,
            html=html,
            html_hash=_compute_hash(html),
            price=None,
            currency=None,
            scraped_at=datetime.now(UTC),
            extraction_status=ExtractionStatus.OK,
        )
    if status not in (429, 403, 500, 502, 503, 504) and status < 500:
        logger.error("http_error_non_retryable", url=url, status=status)
        return _error_result(url)
    return None  # retryable — caller handles back-off


def _redact_proxy(proxy_url: str) -> str:
    """Drop any credentials from a proxy URL so it is safe to log."""
    parsed = urlparse(proxy_url)
    host = parsed.hostname or "?"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}"


def _block_result(url: str, response: httpx.Response, status: ExtractionStatus) -> ScrapedResult:
    """Build a BLOCKED/CAPTCHA ScrapedResult from a challenge/ban response."""
    html = response.text or ""
    return ScrapedResult(
        url=url,
        html=html,
        html_hash=_compute_hash(html) if html else "",
        price=None,
        currency=None,
        scraped_at=datetime.now(UTC),
        extraction_status=status,
    )


async def _fetch_via_proxy(
    url: str,
    proxy_url: str | None,
) -> tuple[ScrapedResult, str]:
    """Fetch *url* once via *proxy_url* (or direct if None), with the existing back-off.

    Returns ``(result, action)`` where *action* tells :func:`fetch_page`'s rotation
    loop what to do: ``_ACTION_RETURN`` for a terminal result, ``_ACTION_ROTATE_BLOCK``
    when a block/CAPTCHA is seen through a proxy, or ``_ACTION_ROTATE_DEAD`` when the
    proxy itself is unreachable. The transient 5xx/``Retry-After`` back-off and UA
    rotation are unchanged from the pre-proxy client.
    """
    proxy = normalise_proxy(proxy_url).httpx if proxy_url is not None else None
    headers = build_headers(choose_user_agent())
    last_exc: Exception | None = None
    last_block: ScrapedResult | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True, proxy=proxy) as client:
                response = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            if proxy_url is not None:
                logger.warning(
                    "proxy_unreachable", url=url, proxy=_redact_proxy(proxy_url), error=str(exc)
                )
                return _error_result(url), _ACTION_ROTATE_DEAD
            last_exc = exc
            delay = _RETRY_BACK_OFF[min(attempt, len(_RETRY_BACK_OFF) - 1)]
            logger.warning(
                "http_request_error", url=url, attempt=attempt, error=str(exc), delay=delay
            )
            await asyncio.sleep(delay)
            continue

        block = classify_block(response.status_code, response.text)
        if block is not None:
            if proxy_url is not None:
                logger.warning(
                    "scrape_blocked",
                    url=url,
                    status=response.status_code,
                    classification=block.value,
                    proxy=_redact_proxy(proxy_url),
                )
                return _block_result(url, response, block), _ACTION_ROTATE_BLOCK
            if response.status_code == 200:
                # A 200-status challenge page with no proxy to rotate to — record it.
                logger.warning("scrape_blocked_no_proxy", url=url, classification=block.value)
                return _block_result(url, response, block), _ACTION_RETURN
            # A 429/503 block with no proxy: fall through to the transient back-off
            # (preserving the existing Retry-After behaviour), but remember it so an
            # exhausted retry chain resolves to BLOCKED rather than a bare HTTP_ERROR.
            last_block = _block_result(url, response, block)
        else:
            final = _result_for_status(url, response, attempt)
            if final is not None:
                return final, _ACTION_RETURN

        # Retryable status — compute back-off delay (existing behaviour).
        status = response.status_code
        if status == 429:
            delay = float(response.headers.get("Retry-After", _DEFAULT_RETRY_AFTER))
            logger.warning("http_429_rate_limited", url=url, attempt=attempt, retry_after=delay)
        else:
            delay = _RETRY_BACK_OFF[min(attempt, len(_RETRY_BACK_OFF) - 1)]
            logger.warning(
                "http_error_retrying", url=url, status=status, attempt=attempt, delay=delay
            )

        await asyncio.sleep(delay)
        headers = build_headers(choose_user_agent())

    if last_block is not None:
        logger.warning("http_block_persisted_no_proxy", url=url)
        return last_block, _ACTION_RETURN
    logger.error("http_all_retries_exhausted", url=url, last_error=str(last_exc))
    return _error_result(url), _ACTION_RETURN


async def fetch_page(url: str, redis_client: object | None = None) -> ScrapedResult:
    """Fetch *url* with retry, rate-limiting, robots.txt checking, and proxy rotation.

    A fresh proxy is picked per call from ``settings.PROXY_URLS`` (empty ⇒ direct).
    On a detected block/CAPTCHA the fetch rotates to the next proxy up to
    ``settings.MAX_PROXY_ROTATIONS`` times before resolving to BLOCKED/CAPTCHA; an
    unreachable proxy rotates without consuming that budget, and once every proxy
    has been tried the call fails bounded rather than looping.
    """
    domain = _extract_domain(url)
    await _check_robots(url, redis_client)
    await _apply_rate_limit(domain, redis_client)

    rotator = ProxyRotator()
    block_budget = settings.MAX_PROXY_ROTATIONS
    dead_tries = 0

    while True:
        result, action = await _fetch_via_proxy(url, rotator.current())

        if action == _ACTION_RETURN:
            return result

        if action == _ACTION_ROTATE_DEAD:
            dead_tries += 1
            if dead_tries < rotator.count:
                rotator.next_proxy()
                continue
            logger.error("all_proxies_unreachable", url=url, tried=dead_tries)
            return result

        # _ACTION_ROTATE_BLOCK
        if block_budget > 0:
            block_budget -= 1
            logger.info("rotating_proxy_on_block", url=url, remaining_budget=block_budget)
            rotator.next_proxy()
            continue
        logger.warning(
            "scrape_block_persisted", url=url, classification=result.extraction_status.value
        )
        return result
