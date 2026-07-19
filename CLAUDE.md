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
make quality                     # backend radon + frontend vitest coverage + intra-tier coverage overlap
make lint                        # ruff (backend) + eslint (frontend)
make format                      # ruff format (backend) + prettier (frontend)

# Test suite health — intra-tier coverage duplication (also run inside make quality)
make check-coverage-overlap          # backend: flag same-tier tests covering the same source line
make check-coverage-overlap-frontend # frontend: per-file vitest runs, then same-tier overlap report

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

# Docker quality gates
make lint-docker                 # hadolint all Dockerfiles (fails on ERROR/WARN; INFO is shown but non-fatal)
make validate-nginx              # nginx -t syntax check of docker/nginx.conf via Docker (--add-host=backend:127.0.0.1)
make scan                        # Trivy CRITICAL CVE scan on built backend + frontend images
make smoke                       # full-stack smoke test: up → health poll → nginx-health → down

# Executed E2E behaviour (BDD) — runs the docs/behaviour/ Gherkin catalogue
make test-e2e                    # up e2e overlay → backend pytest-bdd + frontend playwright-bdd → down
make test-e2e-smoke              # only @smoke-tagged scenarios (fast; runs on every PR)
make e2e-up                      # bring the e2e compose overlay up (fixture-server + webhook-sink + test hooks)
make e2e-down                    # tear the e2e overlay down and remove volumes

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
- `prices.py` — paginated price history; trigger on-demand scrape (tags the dispatch with a `pp_trigger="on_demand"` Celery header for `ScrapeJob` tracking, Item 17)
- `alerts.py` — CRUD for price alert thresholds
- `scrape_jobs.py` — scrape-job visibility (Item 17): `GET /scrape-jobs` (paginated, filterable by `product_id`/`status`/`queue`/`task_id`), `GET /products/{id}/scrape-jobs`, and best-effort `GET /scrape-jobs/queue-depth`

**Service layer** (`services/`): business logic; the only layer that writes to the DB.
- `price_service.py` — deduplicates by HTML hash; persists `PriceRecord`; calls `alert_service.evaluate_alerts`
- `alert_service.py` — compares latest price against all active alerts; marks triggered alerts and dispatches notification tasks

**Scraping layer** (`scrapers/`): pluggable adapters per retail source type.
- `base.py` — abstract `BaseScraper`; `http_client.py` — shared async httpx with retry/back-off
- `generic.py` — CSS-selector-driven; `amazon.py` — Amazon-specific extraction
- `ebay.py` — eBay UK (httpx + `ld+json`); `currys.py`, `john_lewis.py`, `facebook_marketplace.py` — Playwright, on the shared `playwright_base.py` `PlaywrightScraper` base (`ld+json`-first + CSS-selector DOM fallback); Facebook Marketplace classifies its login wall / bot-check as `blocked`/`captcha` (Item 18)
- `registry.py` — **data-driven**: `get_scraper` / `queue_for_source_type` are async and resolve the scraper class (via a `strategy` → class map) and Celery queue from the DB-backed `SourcePreset` registry (Item 18). A `source_type` is valid iff an enabled `SourcePreset` row exists; it is validated at the API boundary (unknown/disabled → 422). Onboarding a UK retailer is a data change (`SourcePreset` row) not an enum/migration change. `GET /api/v1/sources` exposes the enabled presets.
- `anti_blocking.py` — shared UA/header pool, proxy rotation + normaliser, and the `classify_block` block/CAPTCHA classifier used by both fetch paths (Item 15)
- **Extraction statuses** (`models/enums.py` `ExtractionStatus`): `ok`, `extraction_failed` (selector/parse failure), `http_error` (transient), `blocked` (429/503/IP-ban after proxy rotations exhausted), `captcha` (robot-check interstitial, often HTTP 200). The DB column is an open `String(20)` (no CHECK constraint — see migration 0006), so new statuses need no migration.

**Models** (`models/`): SQLAlchemy ORM models only — no business logic.
**Schemas** (`schemas/`): Pydantic v2 request/response schemas — separate from ORM models.
**Core** (`core/`): `config.py` (Pydantic `Settings`), `database.py` (async engine + `get_db`), `logging.py` (structlog), `exceptions.py`.

**Celery** (`workers/`, `tasks/`):
- `workers/celery_app.py` — Celery factory; autodiscovers `tasks/`
- `tasks/scrape.py` — `scrape_product(product_id)` — fetch → extract → service; retry with exponential back-off
- `tasks/schedule.py` — beat schedule (default: all active products every 30 min)
- `tasks/notify.py` — `send_notification(alert_id)` — dispatch + persist `NotificationLog`
- `tasks/maintenance.py` — `prune_scrape_jobs` — daily beat task (static `beat_schedule`) deleting `ScrapeJob` rows older than `SCRAPE_JOB_RETENTION_DAYS` (Item 17)
- `workers/scrape_job_signals.py` — **Celery-signal lifecycle tracking** (Item 17): `before_task_publish` (both on-demand + scheduled dispatch) creates a `queued` `ScrapeJob` row; `task_prerun`→`started`; `task_postrun` finalises, folding the extraction outcome into `success`/`failure`. Writes use a dedicated **synchronous** session (the signals fire inside the worker's running aio-pool loop, so `asyncio.run()` would raise); every handler filters to `scrape_product`, is fully guarded (never breaks scraping/notification), and upserts by the unique `task_id`. Imported by `celery_app.py` so handlers register in the API, beat, and worker processes.

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
└── e2e/         # executed BDD (pytest-bdd) against the live e2e compose stack;
                 # excluded from the default run — invoke via make test-e2e
```

**Expected E2E behaviour is specified in `docs/behaviour/`** as executed Gherkin
(the single source of truth). Backend scenarios run under `pytest-bdd`
(`backend/tests/e2e/steps/`), frontend UI journeys under `playwright-bdd`
(`frontend/tests/e2e/steps/`); both runners are pointed at `docs/behaviour/`.
Each scenario carries a stable `@PP-E2E-NNN` ID and the `@smoke` subset runs on
every PR. See `docs/behaviour/README.md`. The suite runs against the Item 13
e2e overlay (`make test-e2e`); Item 13 owns the harness, Item 14 the catalogue.

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
| `SCRAPE_JOB_RETENTION_DAYS` | `7` | Age (days) beyond which `prune_scrape_jobs` deletes `ScrapeJob` rows (Item 17) |
| `PROXY_URLS` | `` (empty ⇒ disabled) | BYO rotating-proxy list, comma-separated (`scheme://[user:pass@]host[:port]`, schemes: http/https/socks5/socks5h/socks4). Per-request pick + rotate-on-block across both fetch paths |
| `MAX_PROXY_ROTATIONS` | `2` | Max proxy rotations per fetch on a detected block before the scrape resolves to `blocked`/`captcha` |
| `LOG_LEVEL` | `INFO` | structlog level |
| `E2E_TEST_HOOKS` | `false` | Mounts gated `/api/v1/_test/` hooks; set true **only** by `docker-compose.e2e.yml` |
| `VITE_API_URL` | `http://localhost:8000` | Frontend API base URL (Vite build-time var) |

## Quality Thresholds

- Backend test coverage: ≥ 90%
- Frontend test coverage: ≥ 80%
- Cyclomatic complexity (CC) P95: < 7
- Maintainability Index (MI) P5: > 10
- Halstead effort P95: < 500
- Intra-tier coverage duplication: no net-new same-tier duplicate lines beyond the recorded baseline (backend + frontend); enforced via `[test-health]` in `config/quality-thresholds.toml` (`max_intra_tier_duplicate_lines_backend` / `_frontend`)
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
