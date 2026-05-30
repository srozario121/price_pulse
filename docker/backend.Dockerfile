# =============================================================================
# Price Pulse — Backend Dockerfile
# Multi-stage build: builder installs deps with uv; runtime is slim.
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

# Copy workspace root files first so uv can resolve the full locked dependency tree
COPY pyproject.toml uv.lock* ./
COPY backend/pyproject.toml backend/
RUN uv sync --frozen --no-dev

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
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------------------------------------------------------------------------
# Production stage — lean runtime image
# ---------------------------------------------------------------------------
FROM base AS production

# Create non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Install curl so the HEALTHCHECK CMD (curl -f http://localhost:8000/health) works.
# python:3.12-slim does not include curl; installing it here as root before
# switching to the non-root user.
# DL3008: pinning distro package versions is impractical with rolling base images.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY backend/ .

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
