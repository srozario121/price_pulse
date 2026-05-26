# Playwright-capable Celery worker for Amazon scraping
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace files
COPY pyproject.toml uv.lock* ./
COPY backend/pyproject.toml backend/

# Install runtime deps only
RUN uv sync --no-dev --project backend

# Install Playwright browsers
RUN uv run --project backend playwright install chromium

# Copy application code
COPY backend/ ./backend/

WORKDIR /app/backend

CMD ["uv", "run", "celery", "-A", "app.workers.celery_app", "worker", "--pool=gevent", "-Q", "playwright", "--loglevel=info"]
