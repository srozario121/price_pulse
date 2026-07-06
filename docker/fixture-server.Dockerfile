# =============================================================================
# Price Pulse — E2E Fixture Server
# Tiny FastAPI app serving canned product HTML with a mutable price.
# Used only by the e2e docker-compose overlay; never part of the prod stack.
# =============================================================================

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# DL3013: loose pins are acceptable for this throwaway test-only service.
# hadolint ignore=DL3013
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.30"

COPY tests/e2e/fixture_server/app.py ./app.py

EXPOSE 9000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:9000/health').status==200 else 1)" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
