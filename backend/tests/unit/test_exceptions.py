"""Unit tests for exception handlers in app.core.exceptions.

Each handler is tested in isolation by calling it directly with a mock
Request and the relevant exception, then asserting on the JSONResponse.
"""

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException


def _mock_request(path: str = "/test", method: str = "GET") -> Request:
    """Build a minimal Starlette Request for handler testing."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [],
    }
    return Request(scope=scope)


class TestHTTPExceptionHandler:
    """http_exception_handler maps exc.status_code → response status_code."""

    @pytest.mark.asyncio
    async def test_returns_correct_status_code(self):
        # Arrange
        from app.core.exceptions import http_exception_handler

        request = _mock_request()
        exc = HTTPException(status_code=404, detail="Not Found")

        # Act
        response = await http_exception_handler(request, exc)

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_detail_body(self):
        # Arrange
        import json

        from app.core.exceptions import http_exception_handler

        request = _mock_request()
        exc = HTTPException(status_code=403, detail="Forbidden")

        # Act
        response = await http_exception_handler(request, exc)
        body = json.loads(response.body)

        # Assert
        assert body == {"detail": "Forbidden"}

    @pytest.mark.asyncio
    async def test_500_http_exception(self):
        # Arrange
        import json

        from app.core.exceptions import http_exception_handler

        request = _mock_request()
        exc = HTTPException(status_code=500, detail="server error")

        # Act
        response = await http_exception_handler(request, exc)
        body = json.loads(response.body)

        # Assert
        assert response.status_code == 500
        assert body["detail"] == "server error"


class TestValidationExceptionHandler:
    """validation_exception_handler returns 422 with detail errors."""

    @pytest.mark.asyncio
    async def test_returns_422(self):
        # Arrange

        from app.core.exceptions import validation_exception_handler

        request = _mock_request(method="POST")
        # Build a minimal RequestValidationError
        errors = [{"loc": ("body", "name"), "msg": "field required", "type": "missing"}]
        exc = RequestValidationError(errors=errors)  # type: ignore[arg-type]

        # Act
        response = await validation_exception_handler(request, exc)

        # Assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_detail_key(self):
        # Arrange
        import json

        from app.core.exceptions import validation_exception_handler

        request = _mock_request(method="POST")
        errors = [{"loc": ("body", "url"), "msg": "invalid url", "type": "url_parsing"}]
        exc = RequestValidationError(errors=errors)  # type: ignore[arg-type]

        # Act
        response = await validation_exception_handler(request, exc)
        body = json.loads(response.body)

        # Assert
        assert "detail" in body


class TestUnhandledExceptionHandler:
    """unhandled_exception_handler returns 500 for any Exception."""

    @pytest.mark.asyncio
    async def test_returns_500(self):
        # Arrange
        from app.core.exceptions import unhandled_exception_handler

        request = _mock_request()
        exc = RuntimeError("something unexpected")

        # Act
        response = await unhandled_exception_handler(request, exc)

        # Assert
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_returns_internal_server_error_body(self):
        # Arrange
        import json

        from app.core.exceptions import unhandled_exception_handler

        request = _mock_request()
        exc = ValueError("db exploded")

        # Act
        response = await unhandled_exception_handler(request, exc)
        body = json.loads(response.body)

        # Assert
        assert body == {"detail": "internal server error"}

    @pytest.mark.asyncio
    async def test_does_not_leak_internal_message(self):
        # Arrange
        import json

        from app.core.exceptions import unhandled_exception_handler

        request = _mock_request()
        exc = RuntimeError("super secret internal detail")

        # Act
        response = await unhandled_exception_handler(request, exc)
        body = json.loads(response.body)

        # Assert — internal error message must NOT appear in response
        assert "super secret" not in json.dumps(body)
