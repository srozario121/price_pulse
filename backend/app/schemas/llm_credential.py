"""Pydantic v2 schemas for the per-product BYO LLM credential (Item 16).

The write schema is the only place the plaintext key ever appears; the read
schema deliberately has no field that could carry it, so the secret cannot leak
through a response by accident — not even if a future handler returns the ORM
row directly, because ``ProductLLMCredentialRead`` is built field-by-field.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import LLM_PROVIDERS, azure_config_error


class ProductLLMCredentialWrite(BaseModel):
    """Request body for ``PUT /products/{id}/llm-credential``."""

    provider: str = Field(description=f"One of {LLM_PROVIDERS}")
    model: str = Field(min_length=1, description="Model name; for Azure, the deployment name")
    api_key: str = Field(
        min_length=1, description="Provider API key — stored encrypted, never returned"
    )
    azure_endpoint: str | None = Field(default=None, description="Required when provider=azure")
    azure_api_version: str | None = Field(
        default=None,
        description=(
            "Required for a classic Azure endpoint; must be omitted for a v1 endpoint (…/openai/v1)"
        ),
    )

    @field_validator("provider")
    @classmethod
    def provider_supported(cls, v: str) -> str:
        provider = v.strip().lower()
        if provider not in LLM_PROVIDERS:
            raise ValueError(f"provider must be one of {LLM_PROVIDERS}")
        return provider

    @model_validator(mode="after")
    def azure_fields_coherent(self) -> ProductLLMCredentialWrite:
        """Reject an incoherent Azure credential at the API boundary (422).

        Applies the same rule as the admin default (``azure_config_error``, named
        for this schema's fields) so a BYO credential cannot store a configuration
        that would only fail later, inside the regeneration worker.
        """
        if self.provider != "azure":
            return self
        error = azure_config_error(
            self.azure_endpoint,
            self.azure_api_version,
            endpoint_name="azure_endpoint",
            version_name="azure_api_version",
        )
        if error:
            raise ValueError(error)
        return self


class ProductLLMCredentialRead(BaseModel):
    """Response body for the credential endpoints — metadata only, never the key."""

    product_id: int
    provider: str
    model: str
    # True whenever a credential row exists; the key itself is never exposed.
    has_key: bool
    # A non-reversible hint (e.g. "…f4c2") so an operator can tell which key is
    # stored without the response carrying anything usable.
    key_hint: str
    azure_endpoint: str | None = None
    azure_api_version: str | None = None
    created_at: datetime
    updated_at: datetime
