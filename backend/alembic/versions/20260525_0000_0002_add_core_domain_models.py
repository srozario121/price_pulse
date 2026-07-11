"""add_core_domain_models

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-25 00:00:00.000000+00:00

Creates all four core domain tables, native Postgres ENUM types,
FK constraints, and named query indexes in one atomic migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── ENUM types ─────────────────────────────────────────────────────────────
    # Each native enum below is created inline by the CREATE TABLE that first
    # uses it (source_type→product, alert_direction→price_alert,
    # notification_channel/status→notification_log). We intentionally do NOT
    # create the types explicitly here: under the asyncpg driver a standalone
    # ``Enum.create(checkfirst=True)`` does not suppress the implicit CREATE TYPE
    # emitted by the subsequent ``create_table``, producing a duplicate
    # ``CREATE TYPE`` and a ``DuplicateObjectError``. Letting each owning table
    # create its own type exactly once is driver-agnostic and idempotent.

    # ── product ────────────────────────────────────────────────────────────────
    op.create_table(
        "product",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "generic",
                "amazon",
                "ebay",
                "currys",
                name="source_type_enum",
                native_enum=True,
            ),
            nullable=False,
        ),
        sa.Column("css_selector", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )

    # ── price_record ───────────────────────────────────────────────────────────
    op.create_table(
        "price_record",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("price", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "currency",
            sa.String(3),
            server_default=sa.text("'GBP'"),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("raw_html_hash", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── price_alert ────────────────────────────────────────────────────────────
    op.create_table(
        "price_alert",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("threshold_price", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "direction",
            sa.Enum(
                "above",
                "below",
                name="alert_direction_enum",
                native_enum=True,
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── notification_log ───────────────────────────────────────────────────────
    op.create_table(
        "notification_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum(
                "email",
                "webhook",
                name="notification_channel_enum",
                native_enum=True,
            ),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sent",
                "failed",
                name="notification_status_enum",
                native_enum=True,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["price_alert.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Indexes ────────────────────────────────────────────────────────────────
    op.create_index(
        "ix_price_record_product_captured",
        "price_record",
        ["product_id", "captured_at"],
    )
    op.create_index(
        "ix_price_record_html_hash",
        "price_record",
        ["raw_html_hash"],
    )
    op.create_index(
        "ix_price_alert_product_active",
        "price_alert",
        ["product_id", "is_active"],
    )
    op.create_index(
        "ix_notification_log_alert_sent",
        "notification_log",
        ["alert_id", "sent_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_log_alert_sent", table_name="notification_log")
    op.drop_index("ix_price_alert_product_active", table_name="price_alert")
    op.drop_index("ix_price_record_html_hash", table_name="price_record")
    op.drop_index("ix_price_record_product_captured", table_name="price_record")

    op.drop_table("notification_log")
    op.drop_table("price_alert")
    op.drop_table("price_record")
    op.drop_table("product")

    sa.Enum(name="notification_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="notification_channel_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="alert_direction_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="source_type_enum").drop(op.get_bind(), checkfirst=True)
