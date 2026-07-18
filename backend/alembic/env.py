"""Alembic migration environment — async driver, autogenerate from ORM models.

Uses the `run_sync` pattern so migrations execute over asyncpg without
needing psycopg2. The DATABASE_URL is read from app settings rather than
`alembic.ini` so there is one single source of truth.

Auto-import all ORM models below the `# ── Models` comment so that
`alembic revision --autogenerate` detects every table.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── App imports ───────────────────────────────────────────────────────────────
from app.core.config import settings
from app.core.database import Base

# ── Models — import every module so Alembic sees all mapped tables ─────────────
# (populate this list as models are added in item 3)
from app.models import (  # noqa: F401
    alert,
    notification_log,
    price_history,
    product,
    source_preset,
)

# ── Alembic config ─────────────────────────────────────────────────────────────
config = context.config

# Override the URL from alembic.ini with the value from Settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ── Offline mode (generate SQL script without connecting) ─────────────────────


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout/file)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (connect to DB and apply) ─────────────────────────────────────


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations on an established synchronous connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations via run_sync."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — wraps async runner in asyncio."""
    asyncio.run(run_async_migrations())


# ── Dispatch ───────────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
