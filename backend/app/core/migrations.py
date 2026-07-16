"""Startup schema-version guard.

Compares the Alembic head revision(s) defined by the migration scripts against
the revision(s) recorded in the database's ``alembic_version`` table so the
application refuses to start against an out-of-date or unmigrated schema —
instead of failing later with confusing runtime errors such as
``UndefinedTableError: relation "product" does not exist``.

The check is intentionally read-only: it never applies migrations. Apply them
explicitly with ``make migrate`` (``alembic upgrade head``). It can be disabled
via ``MIGRATION_CHECK_ON_STARTUP=false`` — the E2E overlay does this because it
provisions its schema with ``create_all`` (see ``scripts/create_schema.py``)
rather than through the migration chain, so ``alembic_version`` is never stamped.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# .../backend/app/core/migrations.py → parents[2] == .../backend, the directory
# that holds alembic.ini and the alembic/ migration package.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def get_expected_heads() -> set[str]:
    """Return the head revision id(s) defined by the migration scripts on disk."""
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    # Pin an absolute script location so the lookup is independent of CWD.
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    return set(script.get_heads())


async def get_current_heads(session: AsyncSession) -> set[str]:
    """Return the revision id(s) currently stamped in the database.

    Returns an empty set when the schema has never been migrated (i.e. the
    ``alembic_version`` table does not exist). ``to_regclass`` is used so an
    absent table yields ``NULL`` rather than raising and poisoning the session.
    """
    regclass = (
        await session.execute(text("SELECT to_regclass('public.alembic_version')"))
    ).scalar()
    if regclass is None:
        return set()
    rows = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
    return set(rows)


async def verify_schema_is_current(session: AsyncSession) -> None:
    """Raise ``RuntimeError`` when the DB schema is not at the migration head.

    Logs an actionable message (pointing at ``make migrate``) before raising so
    the reason is obvious in container logs.
    """
    expected = get_expected_heads()
    current = await get_current_heads(session)

    if current == expected:
        logger.info("db_schema_current", revision=sorted(expected))
        return

    logger.error(
        "db_schema_out_of_date",
        db_revision=sorted(current) or None,
        expected_revision=sorted(expected),
        hint="run 'make migrate' (alembic upgrade head) to apply pending migrations",
    )
    raise RuntimeError(
        f"Database schema is out of date "
        f"(db={sorted(current) or 'unmigrated'}, expected={sorted(expected)}). "
        f"Run 'make migrate' to apply pending Alembic migrations."
    )
