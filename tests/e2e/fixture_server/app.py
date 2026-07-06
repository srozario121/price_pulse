"""Deterministic fixture scrape target for the E2E harness.

Serves canned product HTML through the real ``generic`` scraper path (a
``.price`` element the default Product ``css_selector`` extracts) and lets
scenarios mutate the served price so alert-trigger behaviour can be forced.

Endpoints
---------
- ``GET  /health``                 → liveness probe for compose
- ``GET  /fixtures/{slug}``        → product HTML with the current price
- ``PUT  /fixtures/{slug}/price``  → set the price (creates the slug if new)
- ``GET  /fixtures/{slug}/price``  → current price as JSON (debugging)

State is in-memory and per-process — the e2e stack is torn down between runs,
and scenarios use unique slugs, so no persistence or reset is required.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="Price Pulse E2E Fixture Server")

# slug → price string (e.g. "199.99"). Seeded with one default product.
_PRICES: dict[str, str] = {"default": "199.99"}


class PriceBody(BaseModel):
    price: str


def _render(slug: str, price: str) -> str:
    return (
        "<!doctype html><html><head><title>Fixture Product "
        f"{slug}</title></head><body>"
        f"<h1 class='product-name'>Fixture {slug}</h1>"
        f"<span class='currency'>$</span>"
        f"<span class='price'>{price}</span>"
        "</body></html>"
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/fixtures/{slug}", response_class=HTMLResponse)
async def get_fixture(slug: str) -> str:
    price = _PRICES.get(slug)
    if price is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown slug {slug}")
    return _render(slug, price)


@app.get("/fixtures/{slug}/price")
async def get_price(slug: str) -> dict[str, str]:
    price = _PRICES.get(slug)
    if price is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown slug {slug}")
    return {"slug": slug, "price": price}


@app.put("/fixtures/{slug}/price")
async def set_price(slug: str, body: PriceBody) -> dict[str, str]:
    """Set the served price for *slug*, creating the slug if it does not exist."""
    _PRICES[slug] = body.price
    return {"slug": slug, "price": body.price}
