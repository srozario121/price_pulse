"""Structlog configuration — executed at module import time.

Import this module *before* creating the FastAPI app so all log output
uses the configured processors. `main.py` imports it as the first line.

Format:
  - DEBUG=True  → ConsoleRenderer (pretty-print, colour)
  - DEBUG=False → JSONRenderer (structured, machine-readable)

Uses stdlib `LoggerFactory` so `logger.name` is always available (needed
by `add_logger_name` and compatible with third-party library log output).
"""

import logging
import sys

import structlog


def _configure_structlog(debug: bool) -> None:  # noqa: FBT001
    """Configure structlog with appropriate renderer for the environment."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if debug:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    # Use stdlib LoggerFactory so loggers have `.name` for add_logger_name
    structlog.configure(
        processors=[
            *shared_processors,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure the stdlib root logger so uvicorn / sqlalchemy / celery
    # output is captured and formatted consistently.
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )


def configure_logging() -> None:
    """Public entry point called by main.py on startup."""
    from app.core.config import settings  # late import to avoid circular dep

    _configure_structlog(debug=settings.DEBUG)


# Run at import time so that any module that does `import app.core.logging`
# immediately benefits from structured output.
configure_logging()
