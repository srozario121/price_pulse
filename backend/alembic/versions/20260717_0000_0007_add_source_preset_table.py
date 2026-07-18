"""add_source_preset_table

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-17 00:00:00.000000+00:00

Item 18 — configurable monitoring sources. Creates the ``source_preset`` table
(the runtime-editable registry that replaces the two hardcoded ``SourceType``
enums) and seeds the six built-in presets: ``amazon``, ``generic``, ``ebay``,
``currys``, ``john_lewis`` and ``facebook_marketplace``.

The seed is idempotent — it inserts only presets whose ``source_type`` is not
already present — so re-running (or running after a partial manual seed) never
raises a unique-constraint error.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen seed snapshot — intentionally inlined (NOT imported from app code) so this
# historical migration replays identically regardless of later edits to the app's
# BUILTIN_SOURCE_PRESETS. queue: browser scrapers → "playwright", httpx → "default".
_SEED: list[dict[str, object]] = [
    {
        "source_type": "generic",
        "label": "Generic (CSS selector)",
        "host_patterns": [],
        "strategy": "generic",
        "queue": "default",
    },
    {
        "source_type": "amazon",
        "label": "Amazon",
        "host_patterns": ["amazon.co.uk", "amazon.com"],
        "strategy": "amazon",
        "queue": "playwright",
    },
    {
        "source_type": "ebay",
        "label": "eBay UK",
        "host_patterns": ["ebay.co.uk"],
        "strategy": "ebay",
        "queue": "default",
    },
    {
        "source_type": "currys",
        "label": "Currys",
        "host_patterns": ["currys.co.uk"],
        "strategy": "currys",
        "queue": "playwright",
    },
    {
        "source_type": "john_lewis",
        "label": "John Lewis",
        "host_patterns": ["johnlewis.com"],
        "strategy": "john_lewis",
        "queue": "playwright",
    },
    {
        "source_type": "facebook_marketplace",
        "label": "Facebook Marketplace",
        "host_patterns": ["facebook.com"],
        "strategy": "facebook_marketplace",
        "queue": "playwright",
    },
]


def upgrade() -> None:
    op.create_table(
        "source_preset",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("host_patterns", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("strategy", sa.String(50), nullable=False),
        sa.Column("default_css_selector", sa.String(), nullable=True),
        sa.Column("default_css_selector_currency", sa.String(), nullable=True),
        sa.Column("queue", sa.String(50), server_default=sa.text("'default'"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type"),
    )

    # Idempotent seed: insert only presets not already present.
    preset_table = sa.table(
        "source_preset",
        sa.column("source_type", sa.String),
        sa.column("label", sa.String),
        sa.column("host_patterns", sa.JSON),
        sa.column("strategy", sa.String),
        sa.column("queue", sa.String),
    )
    bind = op.get_bind()
    existing = set(bind.execute(sa.select(preset_table.c.source_type)).scalars().all())
    rows = [row for row in _SEED if row["source_type"] not in existing]
    if rows:
        op.bulk_insert(preset_table, rows)


def downgrade() -> None:
    op.drop_table("source_preset")
