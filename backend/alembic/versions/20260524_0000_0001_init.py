"""init

Revision ID: 0001
Revises:
Create Date: 2026-05-24 00:00:00.000000+00:00

Empty baseline migration. Models and their tables will be added in the
next revision once domain models are defined in item 3.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No tables yet — models added in item 3.
    pass


def downgrade() -> None:
    pass
