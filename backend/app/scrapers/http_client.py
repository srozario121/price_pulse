"""Shared async HTTP client with retry, rate-limiting, and robots.txt support."""
from __future__ import annotations

import asyncio
import hashlib
import random
import urllib.robotparser
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
import structlog

from app.core.config import settings
from app.models.enums import ExtractionStatus
from app.schemas.scraper import ScrapedResult

logger = structlog.get_logger()

# Pool of common browser User-Agent strings
_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.6 Mobile Safari/537.36",
]

_RETRY_BACK_OFF: list[float] = [1.0, 2.0, 4.0]
_MAX_RETRIES = 3
_DEFAULT_RETRY_AFTER = 60


def _extract_domain(url: str) -> str:
    return urlparse(url).netloc


def _compute_hash(html: str) -> str:
    return hashlib.sha256(html.encode()).hexdigest()


async def _check_robots(url: str, redis_client: object | None) -> None:
    """Fetch and parse robots.txt; log WARNING if path is disallowed (log-and-proceed)."""
    parsed = urlparse(url)
    domain = parsed.netloc
    robots_url = f"{parsed.scheme}://{domain}/robots.txt"
    cache_key = f"robots:{domain}"

    robots_text: str | None = None

    if redis_client is not None:
        try:
            cached = await redis_client.get(cache_key)  # type: ignore[union-attr]
            if cached is not None:
                robots_text = cached if isinstance(cached, str) else cached.decode()
        except Exception:
            pass  # Redis failure is non-fatal

    if robots_text is None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(robots_url)
                robots_text = response.text if response.status_code == 200 else ""
        except Exception:
            robots_text = ""

        if redis_client is not None:
            try:
                await redis_client.set(cache_key, robots_text, ex=3600)  # type: ignore[union-attr]
            except Exception:
                pass

    if robots_text:
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(robots_text.splitlines())
        path = parsed.path or "/"
        if not rp.can_fetch("*", url):
            logger.warning(
                "robots_txt_disallowed",
                url=url,
                path=path,
                robots_url=robots_url,
            )


async def _apply_rate_limit(domain: str, redis_client: object | None) -> None:
    """Sleep if a rate-limit key for *domain* exists in Redis; then set the key."""
    if redis_client is None:
        return
    cache_key = f"rate_limit:{domain}"
    try:
        exists = await redis_client.get(cache_key)  # type: ignore[union-attr]
        if exists is not None:
            await asyncio.sleep(settings.SCRAPE_MIN_DELAY_SECONDS)
        await redis_client.set(  # type: ignore[union-attr]
            cache_key, "1", ex=settings.SCRAPE_MIN_DELAY_SECONDS
        )
    except Exception:
        pass  # Redis failure is non-fatal


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


async def fetch_page(url: str, redis_client: object | None = None) -> ScrapedResult:
    """Fetch *url* with retry, rate-limiting, and robots.txt checking.

    Returns a ScrapedResult.  On permanent failure (all retries exhausted)
    returns a result with extraction_status=HTTP_ERROR.
    """
    domain = _extract_domain(url)

    # robots.txt check (log-and-proceed)
    await _check_robots(url, redis_client)

    # Rate limiting
    await _apply_rate_limit(domain, redis_client)

    headers = {"User-Agent": random.choice(_USER_AGENTS)}

    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=headers)

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

            if status == 429:
                retry_after = float(
                    response.headers.get("Retry-After", _DEFAULT_RETRY_AFTER)
                )
                logger.warning(
                    "http_429_rate_limited",
                    url=url,
                    attempt=attempt,
                    retry_after=retry_after,
                )
                await asyncio.sleep(retry_after)
                # rotate user agent for retry
                headers = {"User-Agent": random.choice(_USER_AGENTS)}
                continue

            if status in (403, 500, 502, 503, 504) or status >= 500:
                delay = _RETRY_BACK_OFF[min(attempt, len(_RETRY_BACK_OFF) - 1)]
                logger.warning(
                    "http_error_retrying",
                    url=url,
                    status=status,
                    attempt=attempt,
                    delay=delay,
                )
                await asyncio.sleep(delay)
                headers = {"User-Agent": random.choice(_USER_AGENTS)}
                continue

            # Non-retryable error (404, 400, etc.)
            logger.error("http_error_non_retryable", url=url, status=status)
            return _error_result(url)

        except httpx.RequestError as exc:
            last_exc = exc
            delay = _RETRY_BACK_OFF[min(attempt, len(_RETRY_BACK_OFF) - 1)]
            logger.warning(
                "http_request_error",
                url=url,
                attempt=attempt,
                error=str(exc),
                delay=delay,
            )
            await asyncio.sleep(delay)

    logger.error("http_all_retries_exhausted", url=url, last_error=str(last_exc))
    return _error_result(url)
