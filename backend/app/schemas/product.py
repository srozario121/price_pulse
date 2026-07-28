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

    ``failure_category`` groups the latest failure as ``blocked`` / ``captcha``
    (Item 15) / ``selector_miss`` (Item 16) / ``other``, so an anti-blocking spike
    and a markup-drift spike are each distinguishable from ordinary
    extraction/HTTP failures — and from each other, since they need different
    responses (rotate proxies vs regenerate selectors).

    ``host`` is the normalised selector-profile key, so a drift affecting every
    product on one retailer is visible as one host rather than N products.
    """

    product: ProductRead
    latest_status: str
    latest_captured_at: datetime
    last_success_at: datetime | None
    failure_category: str
    host: str


class SelectorIssueReportRead(BaseModel):
    """``POST /products/{id}/report-selector-issue`` response (202).

    ``regeneration_enqueued`` is False when the report was accepted but the host's
    cooldown window has not elapsed — the report still counted, it just did not
    queue duplicate work.
    """

    product_id: int
    host: str
    status: str
    regeneration_enqueued: bool
