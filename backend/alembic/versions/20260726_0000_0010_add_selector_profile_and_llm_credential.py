"""add_selector_profile_and_llm_credential

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-26 00:00:00.000000+00:00

Item 16 — LLM-generated self-healing selectors. Creates two tables:

``selector_profile``
    One row per host carrying the validated, LLM-generated price selector plus
    its regeneration state (attempt budget + cooldown). ``status`` is a plain
    ``String(20)`` (no native enum), matching the ``extraction_status``
    convention, so new lifecycle states need no further migration.

``product_llm_credential``
    A per-product bring-your-own LLM credential. ``encrypted_api_key`` holds a
    Fernet token — never plaintext. Unique on ``product_id`` (one credential per
    product) and cascade-deleted with the product.

No migration is needed for the new ``selector_miss`` extraction status: the
``ck_price_record_extraction_status`` CHECK constraint was dropped in 0006, so
``price_record.extraction_status`` is an open string column.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "selector_profile",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("price_selector", sa.String(), nullable=True),
        sa.Column("currency_selector", sa.String(), nullable=True),
        sa.Column("status", sa.String(20), server_default=sa.text("'stale'"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("generated_by_provider", sa.String(20), nullable=True),
        sa.Column("generated_by_model", sa.String(100), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Unique on host — the lookup key for every extraction, and the upsert key
    # that keeps concurrent regenerations of the same host to one row.
    op.create_index("ix_selector_profile_host", "selector_profile", ["host"], unique=True)
    op.create_index("ix_selector_profile_status", "selector_profile", ["status"])

    op.create_table(
        "product_llm_credential",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("encrypted_api_key", sa.String(), nullable=False),
        sa.Column("azure_endpoint", sa.String(), nullable=True),
        sa.Column("azure_api_version", sa.String(32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_llm_credential_product_id",
        "product_llm_credential",
        ["product_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_product_llm_credential_product_id", table_name="product_llm_credential")
    op.drop_table("product_llm_credential")
    op.drop_index("ix_selector_profile_status", table_name="selector_profile")
    op.drop_index("ix_selector_profile_host", table_name="selector_profile")
    op.drop_table("selector_profile")
