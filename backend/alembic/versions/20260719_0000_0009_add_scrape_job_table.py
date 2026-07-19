"""add_scrape_job_table

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-19 00:00:00.000000+00:00

Item 17 — queued-scrape visibility. Creates the ``scrape_job`` table: one durable
lifecycle record per ``scrape_product`` dispatch (both on-demand and scheduled),
driven by Celery signals. ``status`` / ``extraction_status`` are plain string
columns (no native enum), matching the ``price_record.extraction_status``
convention, so folding new outcomes in needs no further migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scrape_job",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("queue", sa.String(32), server_default=sa.text("'default'"), nullable=False),
        sa.Column("trigger", sa.String(16), server_default=sa.text("'scheduled'"), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("extraction_status", sa.String(20), nullable=True),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("retries", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # A single unique index on task_id (matches ``unique=True, index=True`` on the
    # model) — the upsert key for idempotent signal writes (ON CONFLICT DO NOTHING).
    op.create_index("ix_scrape_job_product_enqueued", "scrape_job", ["product_id", "enqueued_at"])
    op.create_index("ix_scrape_job_status", "scrape_job", ["status"])
    op.create_index("ix_scrape_job_task_id", "scrape_job", ["task_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_scrape_job_task_id", table_name="scrape_job")
    op.drop_index("ix_scrape_job_status", table_name="scrape_job")
    op.drop_index("ix_scrape_job_product_enqueued", table_name="scrape_job")
    op.drop_table("scrape_job")
