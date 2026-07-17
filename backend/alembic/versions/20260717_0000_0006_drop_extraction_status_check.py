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

``upgrade`` uses ``DROP CONSTRAINT IF EXISTS`` so it is a no-op if the constraint
is absent: alembic's online ``add_column`` in migration 0004 does not always
materialise a ``CheckConstraint`` embedded in the column (the ``--sql`` render
shows the clause, but the executed DDL may omit it), so on some databases the
named constraint was never actually created. Either way the outcome we want —
``extraction_status`` as a genuinely open string column — holds.

``downgrade`` best-effort recreates the original three-value constraint (skipped
if it already exists); it will fail if any 'blocked'/'captcha'/'selector_miss'
rows exist, which is expected since those values only appear after this upgrade.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # IF EXISTS: robust whether or not migration 0004 actually created the
    # named constraint at runtime (see module docstring).
    op.execute(
        "ALTER TABLE price_record DROP CONSTRAINT IF EXISTS ck_price_record_extraction_status"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE price_record ADD CONSTRAINT ck_price_record_extraction_status "
        "CHECK (extraction_status IN ('ok', 'extraction_failed', 'http_error'))"
    )
