# =============================================================================
# Price Pulse — Backend Dockerfile
# Multi-stage build: builder installs deps with uv; runtime is slim.
# NOTE: This is a scaffold stub. Production-grade multi-stage build added in
# Item 8 (Docker Containerisation).
# =============================================================================

FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ---------------------------------------------------------------------------
# Builder stage — install dependencies
# ---------------------------------------------------------------------------
FROM base AS builder

COPY backend/pyproject.toml ./
RUN uv sync --no-dev

# ---------------------------------------------------------------------------
# Development stage — includes dev dependencies for hot-reload
# ---------------------------------------------------------------------------
FROM base AS development

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY backend/pyproject.toml ./
RUN uv sync

COPY backend/ .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------------------------------------------------------------------------
# Production stage — lean runtime image
# ---------------------------------------------------------------------------
FROM base AS production

# Create non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY backend/ .

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
