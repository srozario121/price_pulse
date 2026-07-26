"""Common Pydantic schemas shared across all API v1 endpoints."""

from typing import Literal

from pydantic import BaseModel, field_validator

from app.schemas.product import FailingProductRead, ProductRead


class PaginatedResponse[T](BaseModel):
    """Typed pagination envelope returned by every list endpoint.

    ``total`` is the count of all matching records before pagination.
    ``limit`` is capped at 100.
    """

    items: list[T]
    total: int
    limit: int
    offset: int

    @field_validator("limit")
    @classmethod
    def limit_max_100(cls, v: int) -> int:
        if v > 100:
            raise ValueError("limit must not exceed 100")
        return v


class FailingProductsResponse(PaginatedResponse[FailingProductRead]):
    """``GET /products/failing`` envelope with failure-category aggregate counts.

    Extends the standard pagination envelope with per-category totals across
    *all* flagged products (not just the current page), so a spike is visible at a
    glance: ``blocked_count`` / ``captcha_count`` for anti-blocking (Item 15) and
    ``selector_miss_count`` for markup drift (Item 16). They are separate fields
    because they call for different responses — rotate proxies vs regenerate the
    host's selector.
    """

    blocked_count: int
    captcha_count: int
    selector_miss_count: int


class ScrapeJobResponse(BaseModel):
    """Response body for POST /products/{id}/scrape (202 Accepted).

    ``task_id`` is the Celery task ID; the caller can use it to poll for results.
    ``product`` reflects the current product state so the UI can render
    immediately without a second GET request.
    """

    task_id: str
    status: Literal["queued"]
    product: ProductRead
