"""PriceRecord ORM model — one price observation for a tracked product."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.product import Product


class PriceRecord(Base):
    __tablename__ = "price_record"
    __table_args__ = (
        Index("ix_price_record_product_captured", "product_id", "captured_at"),
        Index("ix_price_record_html_hash", "raw_html_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(
        String(3), server_default=text("'GBP'"), nullable=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    raw_html_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extraction_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'ok'")
    )

    product: Mapped[Product] = relationship("Product", back_populates="price_records")

    def __repr__(self) -> str:
        return f"<PriceRecord id={self.id!r} product_id={self.product_id!r} price={self.price!r}>"
