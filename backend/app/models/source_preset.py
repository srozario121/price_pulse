"""SourcePreset ORM model — the runtime-editable registry of monitoring sources.

Each row is a *preset*: a named source type (``source_type``, the caller-facing
key on ``POST /products``) mapped to an extraction ``strategy`` (which scraper
class runs), the Celery ``queue`` the scrape is dispatched to, and default
generic-selector hints. Presets replace the two divergent hardcoded
``SourceType`` enums (``models/product.py`` + ``scrapers/registry.py``) with a
single DB-backed source of truth, so onboarding a new UK retailer is a data
change rather than an enum + migration + ``if source_type == …`` code change.

Seeded with six built-ins (``amazon``, ``generic``, ``ebay``, ``currys``,
``john_lewis``, ``facebook_marketplace``) by the create-table migration. The
column is a plain ``String`` (no native enum), matching the ``extraction_status``
open-string convention (Items 15–17).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SourcePreset(Base):
    __tablename__ = "source_preset"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # The caller-facing key, matched against ``product.source_type``.
    source_type: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    # Host patterns this preset covers (informational for now; host→preset
    # inference is a deliberately deferred later item). JSON array column.
    host_patterns: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    # Which scraper class runs, resolved by scrapers/registry.py's strategy map.
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    default_css_selector: Mapped[str | None] = mapped_column(String, nullable=True)
    default_css_selector_currency: Mapped[str | None] = mapped_column(String, nullable=True)
    # Celery queue the scrape is dispatched to (browser scrapers → "playwright").
    queue: Mapped[str] = mapped_column(String(50), nullable=False, server_default="default")
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<SourcePreset source_type={self.source_type!r} strategy={self.strategy!r}>"
