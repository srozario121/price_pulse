"""Product ORM model — represents a tracked retail product URL."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.alert import PriceAlert
    from app.models.price_history import PriceRecord


class Product(Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # Open string validated at the API boundary against the enabled SourcePreset
    # registry — no native enum, so onboarding a new source is a data change
    # (Item 18). See services/source_preset_service.py.
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    css_selector: Mapped[str | None] = mapped_column(String, nullable=True)
    css_selector_currency: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    price_records: Mapped[list[PriceRecord]] = relationship(
        "PriceRecord", back_populates="product", cascade="all, delete-orphan"
    )
    price_alerts: Mapped[list[PriceAlert]] = relationship(
        "PriceAlert", back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id!r} name={self.name!r}>"
