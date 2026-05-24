"""Integration tests for database connectivity and the get_db dependency.

Uses the SQLite in-memory test engine from conftest fixtures to verify:
  - get_db yields a working AsyncSession
  - db_session can execute simple queries
  - lifespan startup completes without errors (covered by async_client fixture setup)
"""

import pytest
from sqlalchemy import text


class TestDbSession:
    """db_session fixture yields a functional AsyncSession."""

    @pytest.mark.asyncio
    async def test_session_can_execute_select_1(self, db_session):
        # Arrange / Act
        result = await db_session.execute(text("SELECT 1"))

        # Assert
        row = result.fetchone()
        assert row is not None
        assert row[0] == 1

    @pytest.mark.asyncio
    async def test_session_is_async_session(self, db_session):
        # Arrange
        from sqlalchemy.ext.asyncio import AsyncSession

        # Assert
        assert isinstance(db_session, AsyncSession)


class TestGetDbDependency:
    """get_db dependency yields a working session when used via async_client."""

    @pytest.mark.asyncio
    async def test_health_endpoint_uses_db(self, async_client):
        """The /health endpoint executes SELECT 1 via get_db — if it returns
        200 the dependency is wired correctly."""
        # Arrange / Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_db_yields_async_session_directly(self):
        """Invoke get_db as an async generator and verify the yielded type."""
        # Arrange
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.core.database import get_db

        # Act
        gen = get_db()
        session = await gen.__anext__()

        # Assert
        assert isinstance(session, AsyncSession)

        # Cleanup — close the generator cleanly
        try:
            await gen.aclose()
        except Exception:
            pass
