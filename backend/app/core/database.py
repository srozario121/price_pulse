"""Async SQLAlchemy engine, session factory, and base model class.

All ORM models import `Base` from here. All route handlers that need
a database session declare a dependency on `get_db`.

Usage in a route:
    from app.core.database import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    async def my_route(db: AsyncSession = Depends(get_db)):
        ...
"""

import sys
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import settings


def _running_under_celery() -> bool:
    """True when this process was launched as a Celery worker or beat.

    Celery runs each task under celery-aio-pool's AsyncIOPool, whose event loop
    differs from the transient loops used elsewhere in the worker (e.g. the
    ``asyncio.run`` loop that ``startup_sync_schedules`` uses at worker start).
    A pooled asyncpg connection is bound to the loop that created it, so reusing
    it from another loop raises ``RuntimeError: Event loop is closed`` /
    ``got Future ... attached to a different loop`` — which burned a retry on the
    first scrape of every worker. The FastAPI app runs on a single persistent
    uvicorn loop and is unaffected, so it keeps normal connection pooling.

    Detection is deliberately broad because the workers are launched in several
    ways (``celery ... worker``, ``python .../celery ... beat``, ``uv run celery
    ... worker``): the program name may be ``celery`` or the interpreter, so we
    also treat a ``worker``/``beat`` subcommand in argv as a positive signal.
    """
    argv = sys.argv or []
    prog = argv[0] if argv else ""
    if prog.endswith("celery") or "celery" in prog:
        return True
    return any(arg in {"worker", "beat"} for arg in argv[1:])


def _make_engine() -> AsyncEngine:
    """Build async engine with options appropriate for the configured driver."""
    url = settings.DATABASE_URL
    is_sqlite = url.startswith("sqlite")

    if is_sqlite:
        # SQLite in-memory: use StaticPool so all connections share one DB,
        # and disable thread checks (aiosqlite runs in a thread).
        return create_async_engine(
            url,
            echo=settings.DEBUG,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    if _running_under_celery():
        # NullPool opens (and closes) a fresh connection per session, always on
        # the current task's event loop — no connection is ever reused across
        # loops. See _running_under_celery for why this matters in workers.
        return create_async_engine(url, echo=settings.DEBUG, poolclass=NullPool)

    return create_async_engine(
        url,
        echo=settings.DEBUG,
        pool_pre_ping=True,  # recycle stale connections automatically
        pool_size=10,
        max_overflow=20,
    )


engine = _make_engine()

# ── Session factory ───────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ── Declarative base ──────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base — all ORM models inherit from this."""


# ── Dependency ────────────────────────────────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a per-request async DB session.

    The session is automatically closed (and the transaction rolled back
    on error) when the request context exits.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
