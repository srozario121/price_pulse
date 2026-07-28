"""Structured-output types for LLM selector generation (Item 16).

``SelectorSuggestion`` is passed to Pydantic AI as ``output_type``, so the model's
reply is schema-validated at the framework boundary — every provider returns the
same shape and no provider-specific response parsing exists anywhere in the app.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class SelectorSuggestion(BaseModel):
    """A CSS selector the model believes extracts the price from a product page.

    ``confidence`` is the model's own 0.0–1.0 estimate. It is recorded for
    diagnostics and used as a cheap pre-filter, but it is never the deciding
    factor: a suggestion is promoted only after it actually extracts a plausible
    numeric price from the live page (see ``services/selector_generation``).
    """

    price_selector: str = Field(
        description="A CSS selector matching the element whose text is the current price."
    )
    currency_selector: str | None = Field(
        default=None,
        description=(
            "Optional CSS selector for the currency symbol/code, when it sits in a "
            "different element from the price."
        ),
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="How confident the model is that price_selector is correct (0.0–1.0).",
    )

    @field_validator("price_selector")
    @classmethod
    def price_selector_non_empty(cls, v: str) -> str:
        """Reject a blank selector before it can be stored or validated."""
        selector = v.strip()
        if not selector:
            raise ValueError("price_selector must not be empty")
        return selector

    @field_validator("currency_selector")
    @classmethod
    def blank_currency_is_none(cls, v: str | None) -> str | None:
        """Normalise an empty-string currency selector to ``None``."""
        if v is None:
            return None
        selector = v.strip()
        return selector or None
