"""ScrapeJob ORM model — one lifecycle record per ``scrape_product`` dispatch.

A durable, queryable surface for scrape-job visibility (Item 17). Unlike the
Celery result backend (ephemeral, TTL'd, poor at filtering), this table survives
worker/Redis restarts and can be filtered by product / status / queue / task id.

Rows are created producer-side on ``before_task_publish`` (both the on-demand API
path and the RedBeat scheduled path) and transitioned worker-side on
``task_prerun`` / ``task_postrun`` — see ``workers/scrape_job_signals.py``. The
extraction outcome is folded into ``status`` (``ScrapeJobStatus``) while the raw
scrape retval and any error text are retained in ``extraction_status`` / ``detail``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.product import Product


class ScrapeJob(Base):
    __tablename__ = "scrape_job"
    __table_args__ = (
        Index("ix_scrape_job_product_enqueued", "product_id", "enqueued_at"),
        Index("ix_scrape_job_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    # Celery task UUID — the join key back to the 202 trigger response, and the
    # upsert key that keeps a retried/redelivered task to exactly one row.
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    # Celery queue the job was dispatched to (``default`` / ``playwright``).
    queue: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'default'"))
    # ``on_demand`` (API-triggered) vs ``scheduled`` (RedBeat beat-fired).
    trigger: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'scheduled'")
    )
    # Plain string + ScrapeJobStatus StrEnum (no native DB enum), matching the
    # extraction_status column convention — cheap to extend without a migration.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'queued'"))
    # The raw scrape_product retval (extraction outcome) once the task finishes.
    extraction_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Error text (task exception) or a short summary; diagnostic only.
    detail: Mapped[str | None] = mapped_column(String, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    product: Mapped[Product] = relationship("Product", back_populates="scrape_jobs")

    def __repr__(self) -> str:
        return (
            f"<ScrapeJob id={self.id!r} product_id={self.product_id!r} "
            f"task_id={self.task_id!r} status={self.status!r}>"
        )
