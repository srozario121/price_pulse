"""Deterministic fixture scrape target for the E2E harness.

Serves canned product HTML through the real ``generic`` scraper path (a
``.price`` element the default Product ``css_selector`` extracts) and lets
scenarios mutate the served price so alert-trigger behaviour can be forced.

A slug can also be switched to a **drifted** layout (Item 16): the same price in
markup no built-in selector matches, simulating a retailer rotating its DOM. That
is what makes the self-healing loop observable end to end — the scrape records
``selector_miss``, an LLM generates a replacement selector, and a later scrape of
the *same unchanged page* succeeds.

Endpoints
---------
- ``GET  /health``                 → liveness probe for compose
- ``GET  /fixtures/{slug}``        → product HTML with the current price
- ``PUT  /fixtures/{slug}/price``  → set the price (creates the slug if new)
- ``GET  /fixtures/{slug}/price``  → current price as JSON (debugging)
- ``PUT  /fixtures/{slug}/layout`` → switch between ``standard`` and ``drifted``

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

# slug → layout. "standard" serves the `.price` element every existing scenario
# relies on; "drifted" serves the same price in markup no configured selector
# matches (Item 16).
_LAYOUTS: dict[str, str] = {}
STANDARD = "standard"
DRIFTED = "drifted"
_VALID_LAYOUTS = (STANDARD, DRIFTED)


class PriceBody(BaseModel):
    price: str


class LayoutBody(BaseModel):
    layout: str


def _render_standard(slug: str, price: str) -> str:
    return (
        "<!doctype html><html><head><title>Fixture Product "
        f"{slug}</title></head><body>"
        f"<h1 class='product-name'>Fixture {slug}</h1>"
        f"<span class='currency'>$</span>"
        f"<span class='price'>{price}</span>"
        "</body></html>"
    )


def _render_drifted(slug: str, price: str) -> str:
    """Serve *price* in markup that no built-in or configured selector matches.

    Deliberately hostile to a lucky guess: the class names are opaque, and the
    page carries a struck-through was-price and a review count that both parse as
    plausible numbers. A generated selector only passes the scenario if it picks
    the real amount, so "the LLM returned something that parses" is not enough.
    """
    return (
        "<!doctype html><html><head><title>Fixture Product "
        f"{slug}</title></head><body>"
        f"<h1 class='product-name'>Fixture {slug}</h1>"
        "<span class='q9v-was'>$499.00</span>"
        "<div id='buybox-v2'>"
        "<span class='q9v-cur'>$</span>"
        f"<span class='q9v-amount'>{price}</span>"
        "</div>"
        "<span class='q9v-reviews'>318 reviews</span>"
        "</body></html>"
    )


def _render(slug: str, price: str) -> str:
    if _LAYOUTS.get(slug, STANDARD) == DRIFTED:
        return _render_drifted(slug, price)
    return _render_standard(slug, price)


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


@app.put("/fixtures/{slug}/layout")
async def set_layout(slug: str, body: LayoutBody) -> dict[str, str]:
    """Switch *slug* between the standard and drifted markup (Item 16).

    Creates the slug at a default price if new, so a scenario can provision a
    drifted page in one call.
    """
    if body.layout not in _VALID_LAYOUTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"layout must be one of {_VALID_LAYOUTS}",
        )
    _PRICES.setdefault(slug, "199.99")
    _LAYOUTS[slug] = body.layout
    return {"slug": slug, "layout": body.layout}
