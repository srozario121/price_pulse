"""Async SQLAlchemy engine, session factory, and base model class.

All ORM models import `Base` from here. All route handlers that need
a database session declare a dependency on `get_db`.

Usage in a route:
    from app.core.database import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    async def my_route(db: AsyncSession = Depends(get_db)):
        ...
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.config import settings


def _make_engine():
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
