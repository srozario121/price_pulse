"""add_extraction_status_nullable_price

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-26 00:00:00.000000+00:00

Three amendments to price_record required by the Item 4 scraping engine:

1. price → nullable  (NULL stored for http_error / extraction_failed records)
2. currency → nullable + drop server default  (NULL for failed scrapes; the
   'GBP' default was only valid when every record had a price)
3. extraction_status VARCHAR(20) NOT NULL DEFAULT 'ok'  (encodes scrape
   outcome: 'ok', 'extraction_failed', 'http_error')
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Make price nullable
    op.alter_column(
        "price_record",
        "price",
        existing_type=sa.Numeric(12, 4),
        nullable=True,
    )

    # 2. Make currency nullable and drop the 'GBP' server default
    op.alter_column(
        "price_record",
        "currency",
        existing_type=sa.String(3),
        nullable=True,
        server_default=None,
    )

    # 3. Add extraction_status with CHECK constraint
    op.add_column(
        "price_record",
        sa.Column(
            "extraction_status",
            sa.String(20),
            sa.CheckConstraint(
                "extraction_status IN ('ok', 'extraction_failed', 'http_error')",
                name="ck_price_record_extraction_status",
            ),
            nullable=False,
            server_default="ok",
        ),
    )


def downgrade() -> None:
    op.drop_column("price_record", "extraction_status")

    op.alter_column(
        "price_record",
        "currency",
        existing_type=sa.String(3),
        nullable=False,
        server_default=sa.text("'GBP'"),
    )

    op.alter_column(
        "price_record",
        "price",
        existing_type=sa.Numeric(12, 4),
        nullable=False,
    )
