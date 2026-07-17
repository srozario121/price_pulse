"""drop_extraction_status_check

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-17 00:00:00.000000+00:00

Item 15 (anti-blocking) adds two new extraction-status values — 'blocked' and
'captcha' — and Item 16 will add 'selector_miss'. Migration 0004 created
``price_record.extraction_status`` with a CHECK constraint restricting it to
('ok', 'extraction_failed', 'http_error'), so inserting any new value raises an
IntegrityError.

Rather than widen the constraint for each new status, drop it entirely: the
column stays ``String(20)`` and becomes a genuinely open string, which is what
the app-level ``ExtractionStatus`` StrEnum already assumes. Future status
additions then need no further DB change.

``downgrade`` recreates the original three-value constraint (which would fail if
any 'blocked'/'captcha'/'selector_miss' rows exist — expected, since those
values are only produced after this migration is applied).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_price_record_extraction_status",
        "price_record",
        type_="check",
    )


def downgrade() -> None:
    op.create_check_constraint(
        "ck_price_record_extraction_status",
        "price_record",
        "extraction_status IN ('ok', 'extraction_failed', 'http_error')",
    )
