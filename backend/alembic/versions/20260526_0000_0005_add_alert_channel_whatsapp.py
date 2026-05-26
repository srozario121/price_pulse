"""add_alert_channel_whatsapp

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-26 00:00:00.000000+00:00

Item 5 amendments:

1. Extend notification_channel_enum with 'whatsapp' value.
   NOTE: ALTER TYPE … ADD VALUE cannot run inside a transaction, so it is
   executed with op.execute() before the table-level column additions.

2. Add channel notification_channel_enum NOT NULL DEFAULT 'email' to price_alert.
3. Add webhook_url VARCHAR(512) NULL to price_alert.
4. Add whatsapp_number VARCHAR(20) NULL to price_alert.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend notification_channel_enum with 'whatsapp'.
    #    ALTER TYPE … ADD VALUE must run outside a transaction.
    op.execute("COMMIT")
    op.execute("ALTER TYPE notification_channel_enum ADD VALUE IF NOT EXISTS 'whatsapp'")

    # 2. Add channel column (NOT NULL with default 'email').
    op.add_column(
        "price_alert",
        sa.Column(
            "channel",
            sa.Enum("email", "webhook", "whatsapp", name="notification_channel_enum"),
            nullable=False,
            server_default="email",
        ),
    )

    # 3. Add webhook_url column.
    op.add_column(
        "price_alert",
        sa.Column("webhook_url", sa.String(512), nullable=True),
    )

    # 4. Add whatsapp_number column (E.164 format, e.g. +447911123456).
    op.add_column(
        "price_alert",
        sa.Column("whatsapp_number", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("price_alert", "whatsapp_number")
    op.drop_column("price_alert", "webhook_url")
    op.drop_column("price_alert", "channel")
    # Note: Postgres does not support removing enum values.
    # The 'whatsapp' value is left in notification_channel_enum on downgrade.
