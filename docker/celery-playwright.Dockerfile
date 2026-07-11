# Playwright-capable Celery worker for Amazon scraping
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace files
COPY pyproject.toml uv.lock* ./
COPY backend/pyproject.toml backend/

# Export all workspace member deps from the frozen lockfile and install into .venv
# uv sync --no-install-workspace from workspace root produces an empty venv in this setup.
# Pin the interpreter to 3.12 to match the rest of the stack (backend + default
# worker run python:3.12-slim). Without --python, uv provisions the newest
# CPython it can find (e.g. 3.14), on which celery-aio-pool's async tracer fails
# to await `async def` tasks — the task returns an un-awaited coroutine and
# Celery raises "Object of type coroutine is not JSON serializable".
RUN uv export --frozen --no-dev --no-hashes --package price-pulse-backend --output-file /tmp/requirements.txt && \
    uv venv --python 3.12 .venv && \
    uv pip install --no-cache-dir -r /tmp/requirements.txt

# Install Playwright browsers
RUN uv run --project backend playwright install chromium

# Copy application code
COPY backend/ ./backend/

WORKDIR /app/backend

# Worker pool is set in celery_app.py (worker_pool="custom" → celery-aio-pool
# AsyncIOPool via CELERY_CUSTOM_WORKER_POOL) so async def tasks are awaited;
# not passed via CLI.
CMD ["uv", "run", "celery", "-A", "app.workers.celery_app", "worker", "-Q", "playwright", "--loglevel=info"]
