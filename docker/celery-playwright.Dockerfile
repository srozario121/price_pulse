# Playwright-capable Celery worker for Amazon scraping
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace files
COPY pyproject.toml uv.lock* ./
COPY backend/pyproject.toml backend/

# Install runtime deps only (--frozen ensures the lockfile is honoured)
RUN uv sync --frozen --no-dev --no-install-workspace

# Install Playwright browsers
RUN uv run --project backend playwright install chromium

# Copy application code
COPY backend/ ./backend/

WORKDIR /app/backend

# pool is set in celery_app.py (worker_pool="celery.concurrency.aio:TaskPool")
# and is NOT passed via CLI because Celery 5.x does not expose "asyncio" as a -P shorthand
CMD ["uv", "run", "celery", "-A", "app.workers.celery_app", "worker", "-Q", "playwright", "--loglevel=info"]
