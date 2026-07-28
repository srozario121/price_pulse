"""ProductLLMCredential ORM model — a per-product bring-your-own LLM key (Item 16).

The repo has no auth/user system yet, so the product is the only ownership
boundary that exists: an external user who wants selector generation billed to
their own provider account attaches a credential to their product.

The key is **encrypted at rest** (Fernet, via ``core/crypto.py``), decrypted only
inside ``services/llm/client.resolve_llm_config`` at generation time, and never
returned by any endpoint — the read schema exposes provider/model and a masked
hint only. One credential per product (unique FK), replaced wholesale by ``PUT``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.product import Product


class ProductLLMCredential(Base):
    __tablename__ = "product_llm_credential"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Unique: a product has at most one credential; PUT replaces it in place.
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # One of core.config.LLM_PROVIDERS, validated at the API boundary (422).
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # Provider-specific model name; for Azure this is the deployment name.
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    # Fernet token — never the plaintext key, never logged, never serialised out.
    encrypted_api_key: Mapped[str] = mapped_column(String, nullable=False)
    azure_endpoint: Mapped[str | None] = mapped_column(String, nullable=True)
    azure_api_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    product: Mapped[Product] = relationship("Product", back_populates="llm_credential")

    def __repr__(self) -> str:
        # Deliberately omits encrypted_api_key — repr output reaches logs.
        return (
            f"<ProductLLMCredential id={self.id!r} product_id={self.product_id!r} "
            f"provider={self.provider!r} model={self.model!r}>"
        )
