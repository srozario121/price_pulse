"""add_css_selector_currency

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-26 00:00:00.000000+00:00

Adds css_selector_currency column to product table so GenericScraper
can extract the currency symbol from a separate CSS selector and map
it to an ISO 4217 code (e.g. £ → GBP).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product",
        sa.Column("css_selector_currency", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product", "css_selector_currency")
