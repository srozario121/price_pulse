"""source_type_enum_to_string

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-17 00:00:00.000000+00:00

Item 18 — migrate ``product.source_type`` off the native Postgres
``source_type_enum`` type to a validated ``String`` column. Existing values are
preserved (``USING source_type::text``); the native enum type is then dropped.

This eliminates an ``ALTER TYPE … ADD VALUE`` migration per new retailer: the
DB-backed ``source_preset`` registry (migration 0007) is now the single source of
truth for valid source types, validated at the API boundary. Consistent with the
``extraction_status`` open-string convention (Items 15–17).

``downgrade`` recreates the original four-value enum and converts the column
back; it will fail if any row holds a value outside the original set
(e.g. ``john_lewis``/``facebook_marketplace``), which is expected since those
values only become storable after this upgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ORIGINAL_ENUM_VALUES = ("generic", "amazon", "ebay", "currys")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "product",
            "source_type",
            type_=sa.String(length=50),
            existing_type=sa.Enum(*_ORIGINAL_ENUM_VALUES, name="source_type_enum"),
            postgresql_using="source_type::text",
            existing_nullable=False,
        )
        op.execute("DROP TYPE IF EXISTS source_type_enum")
    else:
        # SQLite and other non-native-enum backends store StrEnum columns as
        # plain text already; widen to a bounded String for consistency.
        with op.batch_alter_table("product") as batch:
            batch.alter_column(
                "source_type",
                type_=sa.String(length=50),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        enum_type = sa.Enum(*_ORIGINAL_ENUM_VALUES, name="source_type_enum")
        enum_type.create(bind, checkfirst=True)
        op.alter_column(
            "product",
            "source_type",
            type_=enum_type,
            existing_type=sa.String(length=50),
            postgresql_using="source_type::source_type_enum",
            existing_nullable=False,
        )
    else:
        with op.batch_alter_table("product") as batch:
            batch.alter_column(
                "source_type",
                type_=sa.Enum(*_ORIGINAL_ENUM_VALUES, name="source_type_enum"),
                existing_nullable=False,
            )
