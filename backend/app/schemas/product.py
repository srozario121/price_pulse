"""Pydantic v2 schemas for Product."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProductBase(BaseModel):
    name: str
    url: str
    # Validated at the API boundary against the enabled SourcePreset registry
    # (unknown/disabled → 422); no longer a native enum (Item 18).
    source_type: str
    css_selector: str | None = None
    css_selector_currency: str | None = None
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductRead(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    source_type: str | None = None
    css_selector: str | None = None
    css_selector_currency: str | None = None
    is_active: bool | None = None


class FailingProductRead(BaseModel):
    """A product whose latest scrapes have all failed extraction.

    Surfaced by ``GET /products/failing`` so a quietly-broken crawl (e.g. a
    permanently CAPTCHA-walled source) is visible instead of silently recording
    price-less records forever.

    ``failure_category`` (Item 15) groups the latest failure as ``blocked`` /
    ``captcha`` / ``other`` so an anti-blocking spike is distinguishable from
    ordinary extraction/HTTP failures.
    """

    product: ProductRead
    latest_status: str
    latest_captured_at: datetime
    last_success_at: datetime | None
    failure_category: str
