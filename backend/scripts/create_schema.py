"""Provision the full ORM schema directly via ``Base.metadata.create_all``.

The production stack applies Alembic migrations; the E2E harness instead
provisions the schema with ``create_all`` — the same known-good path the
integration-test fixtures use — so behaviour scenarios run against a populated
database without coupling the harness to the migration chain.

Run inside the backend container against the e2e overlay:
    docker compose ... exec -T backend /app/.venv/bin/python scripts/create_schema.py
"""

from __future__ import annotations

import asyncio

from app.core.database import Base, engine

# Import every model module so its tables/enums register on Base.metadata.
from app.models import alert, notification_log, price_history, product  # noqa: F401


async def _main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(_main())
    print("e2e schema created")
