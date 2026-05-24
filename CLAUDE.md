# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Planning Mode — Clarification Gate

When entering plan mode (via `/plan` or `EnterPlanMode`), **always ask clarifying questions before producing a plan**. Do not start designing until the answers are known. Cover whichever of these are uncertain given the request:

1. **Scope** — Which files, modules, or workflows are in scope? What is explicitly out of scope?
2. **Behaviour** — What should the feature do in edge cases or failure paths?
3. **Constraints** — Are there performance, rate-limiting, or external-site compatibility constraints?
4. **Definition of done** — What does success look like? Tests only, or also a manual smoke-test against a real product URL?
5. **Dependencies** — Does this block or get blocked by other in-flight work?

Ask only the questions that are genuinely unclear — do not ask about things already stated in the request or derivable from the codebase. Wait for answers before writing the plan.

## Commands

```bash
# Install all dependencies (backend + frontend) and wire pre-commit hooks
make install        # uv sync (workspace) + cd frontend && npm install + pre-commit install

# Start full stack (Docker Compose)
make up                          # production-like stack (detached)
make down                        # stop stack
make logs                        # all service logs
make logs SERVICE=backend        # specific service

# Development (hot-reload)
make dev                         # docker-compose.dev.yml (hot-reload volume mounts) — backend, celery-worker, celery-beat, postgres, redis, Flower :5555, pgAdmin :5050

# Backend only (no Docker)
cd backend && uv sync
uv run uvicorn app.main:app --reload --port 8000

# Frontend only (no Docker)
cd frontend && npm install
npm run dev                      # Vite dev server on port 5173

# Run all tests
make test                        # backend (pytest) + frontend (vitest)
make test-backend                # pytest only
make test-frontend               # vitest only

# Backend test variants
cd backend
uv run pytest                                           # all tests
uv run pytest tests/unit/                              # unit only
uv run pytest tests/integration/                       # integration only
uv run pytest tests/unit/test_price_service.py         # single file
uv run pytest -m "not live_api"                        # skip external calls
uv run pytest --cov=app --cov-report=term-missing      # with coverage

# Frontend test variants
cd frontend
npm run test                     # vitest watch mode
npm run test:run                 # vitest single run
npm run test:coverage            # vitest with coverage

# Quality gates
make quality                     # backend radon + frontend vitest coverage report
make lint                        # ruff (backend) + eslint (frontend)
make format                      # ruff format (backend) + prettier (frontend)

# Database migrations
make migrate                     # apply pending Alembic migrations
make migrate MSG="add_alerts"    # generate new migration
make shell-db                    # psql into the running DB container

# Celery workers (local, no Docker)
make worker                      # start celery worker
make beat                        # start celery beat scheduler

# Docker builds
make build                       # build all Docker images
make build SERVICE=backend       # build single image

# Code analysis
make structure                   # show backend package tree with module counts
```

## Architecture

### Overview

A monorepo price-monitoring platform. Users add retail product URLs; Celery tasks scrape prices on a schedule; React frontend displays price history and alert status.

```
price_pulse/
├── backend/        # FastAPI app + Celery workers
├── frontend/       # React + Vite SPA
├── docker/         # Dockerfiles and Nginx config
├── docs/architecture/          # C4 architecture docs
├── config/         # Quality thresholds (TOML)
├── .claude/agents/ # Claude Code SDLC agents
└── .github/agents/ # GitHub Copilot SDLC agents
```

### Backend (`backend/app/`)

Layered FastAPI application:

**Entry**: `main.py` → FastAPI app factory; mounts `/api/v1` router; registers exception handlers; lifespan hook connects DB.

**API layer** (`api/v1/`): thin route handlers — validate input, call service, return schema. No business logic in routes.
- `products.py` — CRUD for tracked products
- `prices.py` — paginated price history; trigger on-demand scrape
- `alerts.py` — CRUD for price alert thresholds

**Service layer** (`services/`): business logic; the only layer that writes to the DB.
- `price_service.py` — deduplicates by HTML hash; persists `PriceRecord`; calls `alert_service.evaluate_alerts`
- `alert_service.py` — compares latest price against all active alerts; marks triggered alerts and dispatches notification tasks

**Scraping layer** (`scrapers/`): pluggable adapters per retail source type.
- `base.py` — abstract `BaseScraper`; `http_client.py` — shared async httpx with retry/back-off
- `generic.py` — CSS-selector-driven; `amazon.py` — Amazon-specific extraction
- `registry.py` — maps `source_type` → scraper class

**Models** (`models/`): SQLAlchemy ORM models only — no business logic.
**Schemas** (`schemas/`): Pydantic v2 request/response schemas — separate from ORM models.
**Core** (`core/`): `config.py` (Pydantic `Settings`), `database.py` (async engine + `get_db`), `logging.py` (structlog), `exceptions.py`.

**Celery** (`workers/`, `tasks/`):
- `workers/celery_app.py` — Celery factory; autodiscovers `tasks/`
- `tasks/scrape.py` — `scrape_product(product_id)` — fetch → extract → service; retry with exponential back-off
- `tasks/schedule.py` — beat schedule (default: all active products every 30 min)
- `tasks/notify.py` — `send_notification(alert_id)` — dispatch + persist `NotificationLog`

**Migrations**: Alembic under `backend/alembic/`; `env.py` imports all models for autogenerate.

### Frontend (`frontend/src/`)

Vite + React + TypeScript SPA:

- `api/client.ts` — typed API wrapper; all HTTP calls go through here
- `pages/` — `Dashboard`, `ProductDetail`, `AlertManager`
- `components/PriceChart.tsx` — Recharts `LineChart` for price history
- `hooks/` — `useProducts`, `usePrices`, `useAlerts` (react-query)
- `store/` — Zustand for UI state (selected product, filter state)

Server state is managed entirely by react-query (stale-while-revalidate, 60s polling). UI-only state lives in Zustand.

### Data Flow

```
User adds URL → POST /api/v1/products
→ Celery Beat fires scrape_product every 30m
  → scraper fetches page → extracts price
  → price_service deduplicates + stores PriceRecord
  → alert_service evaluates alerts
    → send_notification task if threshold crossed
→ Frontend polls /api/v1/products/{id}/prices every 60s
  → PriceChart re-renders
```

### Test Structure

```
backend/tests/
├── unit/        # isolated, no DB — mock SQLAlchemy session and httpx
├── integration/ # real DB (SQLite in-memory or test postgres container)
└── e2e/         # @pytest.mark.live_api — hit real product URLs; skipped by default
```

All tests use **Arrange-Assert-Act** pattern:
```python
def test_price_deduplication():
    # Arrange
    existing_hash = "abc123"
    service = PriceService(db=mock_db)
    # Act
    result = service.record_price(product_id=1, html_hash=existing_hash)
    # Assert
    assert result.is_duplicate is True
```

Live API tests are skipped by default: `uv run pytest -m "not live_api"`.

```
frontend/tests/
├── unit/        # component unit tests with @testing-library/react
└── integration/ # MSW mock service worker for API-integrated tests
```

### Environment Configuration

Copy `.env.example` to `.env`. Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async Postgres connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker + result backend |
| `CELERY_BROKER_URL` | same as `REDIS_URL` | Explicit broker override |
| `SECRET_KEY` | (required, min 32 chars) | Reserved for JWT auth (validated at startup) |
| `DEBUG` | `false` | Enable debug mode; also controls CORS and log format |
| `CORS_ORIGINS` | `["*"]` when DEBUG=true, required otherwise | Allowed CORS origins (comma-separated) |
| `SCRAPE_INTERVAL_MINUTES` | `30` | Default Celery Beat interval |
| `LOG_LEVEL` | `INFO` | structlog level |
| `VITE_API_URL` | `http://localhost:8000` | Frontend API base URL (Vite build-time var) |

## Quality Thresholds

- Backend test coverage: ≥ 90%
- Frontend test coverage: ≥ 80%
- Cyclomatic complexity (CC) P95: < 7
- Maintainability Index (MI) P5: > 10
- Halstead effort P95: < 500
- Quality targets defined in `config/quality-thresholds.toml`

## Custom Agents

`.claude/agents/` contains Claude Code agents for SDLC workflows:

- `quality.md` — run backend + frontend quality gates; produce reports in `logs/quality/<timestamp>/`
- `architecture-maintainer.md` — review structure drift; refresh `docs/architecture/repository-architecture.md`; propose TODO updates
- `profiling-reviewer.md` — analyse pytest-benchmark results; identify slow endpoints and Celery task bottlenecks

`.github/agents/` contains GitHub Copilot agents for the same workflows plus:

- `plan-review.agent.md` — structured clarification loop for a single `TODO.md` item
- `module-grouping-reviewer.agent.md` — two-pass file-tree + AST analysis of flat-module drift in `backend/app/`
- `quality.agent.md` — canonical quality-gate runner
- `profiling-reviewer.agent.md` — profiling analysis and optimization proposals

## Large File Reading Strategy

For files over 200 lines, use a two-phase approach:

```bash
# Phase 1 — map with tree-sitter
echo '(function_definition name: (identifier) @name)' > /tmp/ts-q.scm
tree-sitter query /tmp/ts-q.scm "$FILE"

# Phase 2 — read only the relevant section
# Read(file_path="...", offset=<row>, limit=<num_lines>)
```

Fallback: `grep -n "^def \|^class "` to get line numbers, then `Read` with `offset`+`limit`.

## Changelog

When committing new features, bug fixes, or breaking changes, add an entry to `CHANGELOG.md` under `## [Unreleased]` using [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) categories: **Added**, **Changed**, **Fixed**, **Removed**. Increment the patch version in `pyproject.toml` and move unreleased items into a dated version section on release.
