"""SelectorProfile ORM model — the per-host LLM-generated price selector (Item 16).

Price extraction no longer depends solely on hardcoded CSS selector lists. When a
page loads fine but no selector matches a price (``selector_miss``), an LLM
generates a replacement selector; once it is *validated* against the live page it
is stored here and reused by every subsequent scrape of that host with no further
LLM calls.

Keyed by **host**, not by product or source type: all products on
``amazon.co.uk`` share markup, so one healed selector fixes all of them at once.
Regional storefronts are deliberately distinct rows (``amazon.co.uk`` vs
``amazon.com``) — the 2026-07-12 investigation showed their markup differs.

**One row per host, with an in-place version counter** rather than a row per
generation. The cooldown and attempt-budget state (``failed_attempts``,
``last_attempt_at``) has to exist for a host that has *never* produced a valid
selector, which a version-per-row table has nowhere to put; a counter keeps that
state and the promotion history on the single row the extraction path reads.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SelectorProfile(Base):
    __tablename__ = "selector_profile"
    __table_args__ = (Index("ix_selector_profile_status", "status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Normalised lower-case hostname without a leading "www." — see
    # services/selector_profile_service.host_for_url.
    host: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    # The source_type of the product that triggered generation. Diagnostic only —
    # lookups are by host, since a host maps to exactly one markup family.
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # NULL until the first validated generation lands; the host row exists before
    # that so cooldown/attempt state has somewhere to live.
    price_selector: Mapped[str | None] = mapped_column(String, nullable=True)
    currency_selector: Mapped[str | None] = mapped_column(String, nullable=True)
    # SelectorProfileStatus as a plain string (no native DB enum), matching the
    # extraction_status convention — new states need no migration.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'stale'"))
    # Bumped on every promotion; 0 means "never successfully generated".
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # The model's self-reported confidence in the promoted selector (0.0–1.0).
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Which provider/model produced the promoted selector — needed to explain a
    # bad selector after the fact, and to spot a provider that generates poorly.
    generated_by_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    generated_by_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Consecutive failed generate-and-validate attempts; reset to 0 on promotion.
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Drives the per-host cooldown — set on every attempt, successful or not.
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Why the last attempt failed; diagnostic only.
    detail: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SelectorProfile id={self.id!r} host={self.host!r} "
            f"status={self.status!r} version={self.version!r}>"
        )
