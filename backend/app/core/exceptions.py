"""Custom exception handlers for FastAPI.

Registered on the app instance in main.py. All handlers return RFC 7807
`{"detail": ...}` shapes so the frontend always sees a predictable format.

Handler summary:
  HTTPException           → original status_code + {"detail": exc.detail}
  RequestValidationError  → 422 + FastAPI's default {"detail": errors}
  Exception (catch-all)   → 500 + {"detail": "internal server error"}
                            (full traceback logged via structlog at ERROR)
"""

import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle explicit HTTP errors raised anywhere in the application."""
    logger.warning(
        "http_exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


def _serialisable_errors(errors: list[dict]) -> list[dict]:
    """Return *errors* with any non-JSON-serialisable ``ctx`` values stringified.

    When a request schema raises ``ValueError`` from a custom field/model
    validator, Pydantic v2 puts the **exception object** in ``ctx["error"]``.
    Passing that straight to ``JSONResponse`` raises ``TypeError: Object of type
    ValueError is not JSON serializable``, turning an intended 422 into a 500.
    The human-readable text is already in ``msg``, so stringifying ``ctx`` loses
    nothing and keeps the response shape stable.
    """
    cleaned: list[dict] = []
    for error in errors:
        item = dict(error)
        ctx = item.get("ctx")
        if isinstance(ctx, dict):
            item["ctx"] = {key: str(value) for key, value in ctx.items()}
        cleaned.append(item)
    return cleaned


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle Pydantic / FastAPI request-validation failures (422)."""
    errors = _serialisable_errors(exc.errors())
    logger.warning(
        "validation_error",
        errors=errors,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=422,
        content={"detail": errors},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for any unhandled exception — logs full traceback, returns 500."""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error"},
    )
