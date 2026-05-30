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
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6 Mobile Safari/537.36",
]

_RETRY_BACK_OFF: list[float] = [1.0, 2.0, 4.0]
_MAX_RETRIES = 3
_DEFAULT_RETRY_AFTER = 60


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


async def fetch_page(url: str, redis_client: object | None = None) -> ScrapedResult:
    """Fetch *url* with retry, rate-limiting, and robots.txt checking."""
    domain = _extract_domain(url)
    await _check_robots(url, redis_client)
    await _apply_rate_limit(domain, redis_client)

    headers = {"User-Agent": random.choice(_USER_AGENTS)}
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)

            final = _result_for_status(url, response, attempt)
            if final is not None:
                return final

            # Retryable status — compute back-off delay
            status = response.status_code
            if status == 429:
                delay = float(response.headers.get("Retry-After", _DEFAULT_RETRY_AFTER))
                logger.warning("http_429_rate_limited", url=url, attempt=attempt, retry_after=delay)
            else:
                delay = _RETRY_BACK_OFF[min(attempt, len(_RETRY_BACK_OFF) - 1)]
                logger.warning("http_error_retrying", url=url, status=status, attempt=attempt, delay=delay)

            await asyncio.sleep(delay)
            headers = {"User-Agent": random.choice(_USER_AGENTS)}

        except httpx.RequestError as exc:
            last_exc = exc
            delay = _RETRY_BACK_OFF[min(attempt, len(_RETRY_BACK_OFF) - 1)]
            logger.warning("http_request_error", url=url, attempt=attempt, error=str(exc), delay=delay)
            await asyncio.sleep(delay)

    logger.error("http_all_retries_exhausted", url=url, last_error=str(last_exc))
    return _error_result(url)
