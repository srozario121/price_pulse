"""FastAPI application factory.

Import order matters:
  1. `app.core.logging` — configures structlog before anything else runs
  2. Everything else

Lifespan: verifies DB connectivity on startup and releases the engine
          on shutdown. A startup failure raises immediately so the
          container exits with non-zero (detected by Docker health-check).
"""

# ── 1. Configure logging before any other import ──────────────────────────────
from collections.abc import AsyncGenerator

# ── 2. Standard / third-party imports ─────────────────────────────────────────
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.exceptions import HTTPException

import app.core.logging  # noqa: F401  (side-effect import)
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.core.exceptions import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Async lifespan: startup probe + graceful engine disposal."""
    # ── Startup ──
    logger.info("startup", debug=settings.DEBUG, log_level=settings.LOG_LEVEL)
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        logger.info("db_connected", url=settings.DATABASE_URL.split("@")[-1])
    except Exception as exc:
        logger.error("db_unreachable", error=str(exc))
        raise RuntimeError("Database is unreachable at startup") from exc

    yield  # application runs here

    # ── Shutdown ──
    await engine.dispose()
    logger.info("shutdown")


# ── App factory ────────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    app = FastAPI(
        title="Price Pulse API",
        description="Retail product price monitoring platform.",
        version="0.1.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ──
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # ── Health check ──
    @app.get("/health", tags=["ops"], summary="Readiness probe")
    async def health() -> dict[str, str]:
        """Check that the API process and database are alive.

        Returns 200 `{"status": "ok"}` when DB is reachable,
        503 `{"status": "error", "detail": "db unavailable"}` otherwise.
        """
        from fastapi.responses import JSONResponse

        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "ok"}
        except Exception as exc:
            logger.error("health_check_failed", error=str(exc))
            return JSONResponse(  # type: ignore[return-value]
                status_code=503,
                content={"status": "error", "detail": "db unavailable"},
            )

    # ── API v1 router (populated from item 6) ──
    # from app.api.v1.router import api_router
    # app.include_router(api_router, prefix="/api/v1")

    return app


# Module-level app instance used by uvicorn / gunicorn
app = create_app()
