"""Shared pytest fixtures for all backend tests.

Environment variables are patched at module import time (via os.environ
before the app package is first loaded) so `Settings()` sees the test values.

Fixtures:
  db_session   — async SQLAlchemy session (SQLite in-memory, create/drop per test)
  async_client — httpx.AsyncClient bound to a fresh FastAPI instance;
                 the `get_db` dependency is overridden to use the same
                 SQLite engine so routes interact with the test DB.
"""

import os

import pytest

# ── Patch env BEFORE any app import so pydantic-settings reads test values ────
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-characters-long")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("CORS_ORIGINS", '["http://localhost:5173"]')

# ── Now it's safe to import app modules ───────────────────────────────────────
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ── Database fixtures ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def db_engine():
    """In-memory SQLite engine with schema created and torn down per test."""
    from app.core.database import Base

    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Async session scoped to a single test; rolled back on completion."""
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


# ── HTTP client fixture ───────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def async_client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired to a fresh FastAPI app using the test SQLite DB.

    The `get_db` dependency is overridden so every route uses the same
    in-memory engine as `db_session`.
    """
    from app.core.database import Base, get_db
    from app.main import create_app

    # Build a test-scoped session factory
    test_session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    # Ensure schema exists (idempotent — engine may already have tables)
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    test_app = create_app()
    test_app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=test_app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ── Postgres testcontainer fixtures (integration tests) ───────────────────────


@pytest.fixture(scope="session")
def pg_container():
    """Start a Postgres container once for the entire test session.

    Kept as a separate fixture so pg_engine can be function-scoped
    while the container itself is only started once.
    """
    from testcontainers.postgres import PostgresContainer  # type: ignore[import]

    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest_asyncio.fixture()
async def pg_engine(pg_container):
    """Function-scoped async engine pointing at the Postgres testcontainer.

    Creates the full schema on setup and drops it on teardown, providing
    complete isolation between integration tests.  Uses NullPool so async
    connections are always created in the current test event loop.
    """
    # Ensure every model is registered with Base.metadata before create_all.
    from app.models import alert, notification_log, price_history, product  # noqa: F401
    from app.core.database import Base
    from sqlalchemy.pool import NullPool

    raw_url: str = pg_container.get_connection_url()
    async_url = raw_url.replace("+psycopg2", "+asyncpg").replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    engine = create_async_engine(async_url, echo=False, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def pg_session(pg_engine) -> AsyncGenerator[AsyncSession, None]:
    """Async session against the Postgres testcontainer; rolled back on completion."""
    session_factory = async_sessionmaker(
        bind=pg_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()
