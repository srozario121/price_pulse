"""Integration tests for GET /health.

Uses the `async_client` fixture (httpx.AsyncClient against the test app
with SQLite in-memory DB) to verify the health endpoint behaviour.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestHealthEndpoint:
    """GET /health — DB reachable path."""

    @pytest.mark.asyncio
    async def test_returns_200_when_db_ok(self, async_client):
        # Arrange — async_client uses SQLite so DB is always reachable

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_ok_status(self, async_client):
        # Arrange / Act
        response = await async_client.get("/health")
        body = response.json()

        # Assert
        assert body == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_returns_json_content_type(self, async_client):
        # Arrange / Act
        response = await async_client.get("/health")

        # Assert
        assert "application/json" in response.headers["content-type"]


class TestHealthEndpointDbFailure:
    """GET /health — DB unreachable path returns 503."""

    @pytest.mark.asyncio
    async def test_returns_503_when_db_unavailable(self, async_client):
        # Arrange — patch where main.py resolves AsyncSessionLocal (not the source module)
        from sqlalchemy.exc import OperationalError

        with patch("app.main.AsyncSessionLocal") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(side_effect=OperationalError("DB gone", None, None))
            mock_session_factory.return_value = mock_session

            # Act
            response = await async_client.get("/health")

        # Assert
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_503_body_shape(self, async_client):
        # Arrange
        from sqlalchemy.exc import OperationalError

        with patch("app.main.AsyncSessionLocal") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(side_effect=OperationalError("gone", None, None))
            mock_session_factory.return_value = mock_session

            # Act
            response = await async_client.get("/health")
            body = response.json()

        # Assert
        assert body["status"] == "error"
        assert "db unavailable" in body["detail"]


class TestNotFoundRoute:
    """Routes that don't exist return FastAPI's standard 404 shape."""

    @pytest.mark.asyncio
    async def test_unknown_path_returns_404(self, async_client):
        # Arrange / Act
        response = await async_client.get("/nonexistent")

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_404_body_has_detail_key(self, async_client):
        # Arrange / Act
        response = await async_client.get("/nonexistent")
        body = response.json()

        # Assert
        assert "detail" in body


@pytest.mark.live_api
class TestHealthLiveApi:
    """Live E2E test — requires `make dev` running on port 8000."""

    @pytest.mark.asyncio
    async def test_health_against_running_stack(self):
        # Arrange
        import httpx

        # Act
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health")

        # Assert
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
