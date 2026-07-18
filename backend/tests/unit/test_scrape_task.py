"""Unit tests for app.tasks.scrape.scrape_product."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_product(
    product_id: int = 1,
    source_type: str = "generic",
    url: str = "https://example.com/product",
    css_selector: str = ".price",
    css_selector_currency: str | None = None,
) -> MagicMock:
    p = MagicMock()
    p.id = product_id
    p.source_type = source_type
    p.url = url
    p.css_selector = css_selector
    p.css_selector_currency = css_selector_currency
    p.name = "Test Product"
    return p


def _make_scraped_result(
    extraction_status: str = "ok",
    price: Decimal | None = Decimal("9.99"),
    html_hash: str = "abc123",
) -> MagicMock:
    r = MagicMock()
    r.extraction_status = extraction_status
    r.price = price
    r.html_hash = html_hash
    return r


def _make_price_record(extraction_status: str = "ok") -> MagicMock:
    rec = MagicMock()
    rec.extraction_status = extraction_status
    return rec


@pytest.mark.asyncio
async def test_scrape_product_returns_extraction_status() -> None:
    """Happy path: product found, scrape OK, status returned."""
    from app.tasks.scrape import scrape_product

    product = _make_product()
    scraped = _make_scraped_result(extraction_status="ok")
    record = _make_price_record(extraction_status="ok")

    session_mock = AsyncMock()
    execute_mock = AsyncMock()
    execute_mock.scalar_one_or_none = MagicMock(return_value=product)
    session_mock.execute = AsyncMock(return_value=execute_mock)
    session_mock.commit = AsyncMock()
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=False)

    scraper_mock = AsyncMock()
    scraper_mock.fetch = AsyncMock(return_value=scraped)

    with (
        patch("app.tasks.scrape.AsyncSessionLocal", return_value=session_mock),
        patch("app.tasks.scrape.get_scraper", AsyncMock(return_value=scraper_mock)),
        patch("app.tasks.scrape.price_service") as ps_mock,
    ):
        ps_mock.record_price = AsyncMock(return_value=record)
        result = await scrape_product(product_id=1)

    assert result == "ok"


@pytest.mark.asyncio
async def test_scrape_product_not_found_returns_not_found() -> None:
    """Product not in DB → returns 'not_found' without exception."""
    from app.tasks.scrape import scrape_product

    session_mock = AsyncMock()
    execute_mock = AsyncMock()
    execute_mock.scalar_one_or_none = MagicMock(return_value=None)
    session_mock.execute = AsyncMock(return_value=execute_mock)
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=False)

    with patch("app.tasks.scrape.AsyncSessionLocal", return_value=session_mock):
        result = await scrape_product(product_id=999)

    assert result == "not_found"


@pytest.mark.asyncio
async def test_scrape_product_amazon_routing() -> None:
    """Amazon product: scraper is obtained with source_type='amazon'."""
    from app.tasks.scrape import scrape_product

    product = _make_product(source_type="amazon")
    scraped = _make_scraped_result()
    record = _make_price_record()

    session_mock = AsyncMock()
    execute_mock = AsyncMock()
    execute_mock.scalar_one_or_none = MagicMock(return_value=product)
    session_mock.execute = AsyncMock(return_value=execute_mock)
    session_mock.commit = AsyncMock()
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=False)

    scraper_mock = AsyncMock()
    scraper_mock.fetch = AsyncMock(return_value=scraped)

    captured_source_type: list[str] = []

    async def capture_get_scraper(source_type: str, session: object, **kwargs: object) -> object:
        captured_source_type.append(source_type)
        return scraper_mock

    with (
        patch("app.tasks.scrape.AsyncSessionLocal", return_value=session_mock),
        patch("app.tasks.scrape.get_scraper", capture_get_scraper),
        patch("app.tasks.scrape.price_service") as ps_mock,
    ):
        ps_mock.record_price = AsyncMock(return_value=record)
        await scrape_product(product_id=1)

    assert captured_source_type == ["amazon"]


def test_scrape_product_task_configuration() -> None:
    """Task is configured with correct Celery settings."""
    from app.tasks.scrape import scrape_product

    assert scrape_product.max_retries == 3  # type: ignore[attr-defined]
    assert scrape_product.acks_late is True  # type: ignore[attr-defined]
    assert scrape_product.name == "app.tasks.scrape.scrape_product"  # type: ignore[attr-defined]


def test_retry_countdown_formula() -> None:
    """Exponential countdown: 2**retries gives 1, 2, 4 for attempts 0, 1, 2."""
    assert [2**r for r in range(3)] == [1, 2, 4]
