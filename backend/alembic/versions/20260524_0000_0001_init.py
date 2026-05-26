"""init

Revision ID: 0001
Revises:
Create Date: 2026-05-24 00:00:00.000000+00:00

Empty baseline migration. Models and their tables will be added in the
next revision once domain models are defined in item 3.
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No tables yet — models added in item 3.
    pass


def downgrade() -> None:
    pass
