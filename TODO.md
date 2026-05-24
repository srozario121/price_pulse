# TODO — Price Pulse

Price monitoring platform: track retail product prices across external web sources and alert users when it's a good time to buy.

---

## 1. Repository Scaffolding

Set up the full monorepo skeleton — directory structure, Make commands, Docker Compose, environment config, CI pipeline, and OSS repository hygiene files.

### Design decisions (resolved)

- **Package manager**: `uv` with a root-level uv workspace (`pyproject.toml` at repo root declares `[tool.uv.workspace]` with `members = ["backend"]`). `uv sync` at root installs the full workspace. Rationale: consistent with presentation_helper; enables future shared packages without restructuring.
- **Commit convention**: Conventional Commits (`type(scope): subject` — feat, fix, chore, docs, refactor, test, ci). `commitlint` enforced in CI and via pre-commit hook. Rationale: enables automated CHANGELOG generation and consistent PR history.
- **Branch strategy**: GitHub Flow — `main` is always deployable; all work happens on short-lived feature branches merged via PR. Rationale: minimal overhead for a small team; CI gates enforce quality before merge.
- **Dev strategy**: Docker Compose everywhere. `make dev` uses `docker-compose.dev.yml` override (volume mounts for hot-reload). No native process management for development. Rationale: reproducible environment across machines from day one.
- **Dev extras**: `docker-compose.dev.yml` includes Flower (Celery monitoring, port 5555) and pgAdmin (DB UI, port 5050) so the full development observability stack is available immediately.
- **CI test database**: Postgres service container (`services: postgres:`) in GitHub Actions. Rationale: matches production dialect; catches Postgres-specific query issues that SQLite would miss.
- **CI Docker build**: Docker images are built on every PR (`docker build`) but not pushed. Images are pushed to registry only on merge to `main`. `--cache-from` keeps PR build times low.
- **Pre-commit hooks**: `.pre-commit-config.yaml` is created in this item. `make install` runs `uv sync` + `cd frontend && npm install` + `pre-commit install` so every developer gets all hooks on first checkout.
- **Environment variables**: Root `.env.example` is the single source of truth for all variables — backend vars (`DATABASE_URL`, `REDIS_URL`, etc.) and frontend vars (`VITE_API_URL`, etc.) in one file. Docker Compose loads `.env` from repo root.
- **Licence spelling**: Use `LICENSE` (American English) — matches GitHub licence detection, SPDX tooling, and OSS convention.

### Tasks

- [x] Initialise git repository; add `.gitignore` (Python, Node, Docker, uv, `.env` artefacts)
- [x] Create root `pyproject.toml` with `[tool.uv.workspace]` declaring `members = ["backend"]`; add dev-only root deps (`pre-commit`, `commitlint`)
- [x] Create `Makefile` with targets: `install` (uv sync + npm install + pre-commit install), `dev`, `test`, `test-backend`, `test-frontend`, `build`, `up`, `down`, `logs`, `lint`, `format`, `quality`, `migrate`, `shell-backend`, `shell-db`
- [x] Create `docker-compose.yml` (production-like: backend, celery-worker, celery-beat, frontend, postgres, redis) with `depends_on` health-checks and named volumes
- [x] Create `docker-compose.dev.yml` override: volume mounts for hot-reload on backend + celery, exposed ports, Flower on port 5555, pgAdmin on port 5050
- [x] Create `.env.example` with all required variables documented — backend (`DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `SECRET_KEY`, `DEBUG`, `SCRAPE_INTERVAL_MINUTES`, `LOG_LEVEL`) and frontend (`VITE_API_URL`)
- [x] Create `.pre-commit-config.yaml` — hooks: `commitlint`, `ruff` (Python lint + format), `eslint`, `prettier`, `trailing-whitespace`, `end-of-file-fixer`
- [x] Create `README.md` with project overview, prerequisites, quick-start (`make install && make dev`), and make-target reference table
- [x] Create `CONTRIBUTING.md` — GitHub Flow branch strategy, Conventional Commits format with examples, PR checklist, `make quality` gate requirement before raising a PR
- [x] Create `CHANGELOG.md` — initial `## [Unreleased]` section; `## [0.1.0] - <date>` entry for project init
- [x] Create `.github/workflows/ci.yml` with jobs: `lint` (commitlint + ruff + eslint), `test-backend` (pytest with Postgres service container), `test-frontend` (vitest), `build` (docker build all images, no push; runs on every PR)
- [x] Add `LICENSE` (MIT)

### Test strategy

- **Unit**: N/A — scaffolding only.
- **Integration**: N/A.
- **Negative**: N/A.
- **Live E2E**: N/A.
- **Smoke**: CI pipeline (`ci.yml`) runs on first PR and must pass all four jobs. `make dev` brings the full stack to healthy state (verify `GET /health` 200 once backend is added in item 2).

### Documentation

- **`CLAUDE.md`** — update: `make install` description to include `pre-commit install`; `make dev` description to clarify Docker Compose everywhere; env variable table to add `VITE_API_URL`.
- **`CONTRIBUTING.md`** — create: as specified in tasks above.
- **`CHANGELOG.md`** — create: initial project entry.

---

## 2. Backend Foundation

Bootstrap the FastAPI application with layered architecture, database connectivity, configuration management, and Alembic migrations.

### Design decisions (resolved)

- **Database driver**: `asyncpg` only — no `psycopg2-binary`. The SQLAlchemy async engine uses `postgresql+asyncpg://` and Alembic `env.py` uses the `run_sync` pattern (wraps a synchronous `connection.run_sync(do_run_migrations)` inside an async context) so migrations also execute over asyncpg. Rationale: single driver install; avoids maintaining two Postgres libraries.
- **Health-check depth**: `GET /health` executes `SELECT 1` against the DB. Returns `{"status": "ok"}` with HTTP 200 on success; returns `{"status": "error", "detail": "db unavailable"}` with HTTP 503 on failure. Rationale: Docker `depends_on` health-checks and load balancers need a real readiness signal, not just process presence.
- **Settings class scope**: All application env vars are defined in a single `Settings` class in `config.py` — `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `SECRET_KEY`, `DEBUG`, `LOG_LEVEL`, `SCRAPE_INTERVAL_MINUTES`, and `CORS_ORIGINS`. Rationale: single source of truth; later items (Celery, logging) import `settings` without touching `Settings` again.
- **CORS origins**: `CORS_ORIGINS` env var (comma-separated list). Defaults to `["*"]` when `DEBUG=true`; required (no default) when `DEBUG=false`. `CORSMiddleware` reads from `settings.CORS_ORIGINS`. Rationale: prevents accidental wildcard CORS in production deployments.
- **Structlog format**: DEBUG-aware — `ConsoleRenderer` (pretty-print) when `settings.DEBUG=true`, structured JSON otherwise. Configured at module import time in `logging.py` (before app startup and lifespan hook). Rationale: local developer experience without sacrificing production log-aggregator compatibility.
- **Error response format**: FastAPI default RFC 7807 shape (`{"detail": ...}`). Custom handlers for `HTTPException` and `RequestValidationError` preserve this shape; catch-all 500 handler logs the traceback via structlog and returns `{"detail": "internal server error"}`. Rationale: standard shape, well-documented, expected by frontend clients.
- **SECRET_KEY use**: Reserved for JWT authentication (future item). In item 2, `config.py` validates presence and minimum length (32 chars) but does not consume the value. Rationale: fail-fast at startup so deployments without a secret are rejected immediately.
- **Local test database**: SQLite in-memory (`sqlite+aiosqlite:///:memory:`) for unit and integration tests. CI overrides `DATABASE_URL` with the Postgres service container. `aiosqlite` added as a dev dependency. Rationale: fast local iteration; Postgres-specific behaviour caught in CI.
- **Test infrastructure timing**: `backend/tests/conftest.py` created in item 2. Contains `asyncio_mode = "auto"` pytest config, `async_client` fixture (`httpx.AsyncClient` over `app`), and `db_session` fixture (async session scoped per test, with `create_all`/`drop_all` teardown). All subsequent items inherit these fixtures without re-implementing them.
- **Live E2E definition**: `@pytest.mark.live_api` test hits `http://localhost:8000/health` against a running `make dev` stack. Validates full path: FastAPI process → SQLAlchemy → Postgres container. Skipped by default (`pytest -m "not live_api"`).

### Tasks

- [x] Scaffold `backend/` directory tree: `backend/app/`, `backend/app/core/`, `backend/app/api/`, `backend/app/api/v1/`, `backend/app/models/`, `backend/app/schemas/`, `backend/app/services/`, `backend/app/scrapers/`, `backend/app/workers/`, `backend/app/tasks/`; add `__init__.py` to every package
- [x] Create `backend/pyproject.toml` with `[project]` metadata, uv workspace member declaration, and dependency groups:
  - **runtime**: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic[email]`, `pydantic-settings`, `celery[redis]`, `redis`, `httpx`, `structlog`
  - **dev**: `aiosqlite`, `pytest`, `pytest-cov`, `pytest-asyncio`, `httpx`, `ruff`, `mypy`, `radon`
  - **`[tool.pytest.ini_options]`**: `asyncio_mode = "auto"`; `addopts = "--strict-markers -m 'not live_api'"`; `markers = ["live_api: marks tests that hit real external services (skipped by default)"]`
- [x] Implement `backend/app/core/config.py` — `class Settings(BaseSettings)` covering all app env vars: `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `SECRET_KEY` (field validator: min 32 chars), `DEBUG: bool = False`, `LOG_LEVEL: str = "INFO"`, `SCRAPE_INTERVAL_MINUTES: int = 30`, `CORS_ORIGINS: list[str]` (validator: defaults to `["*"]` when `DEBUG=true`, raises `ValueError` if empty when `DEBUG=false`); export singleton `settings = Settings()`
- [x] Implement `backend/app/core/logging.py` — call `structlog.configure(...)` at module import time; use `ConsoleRenderer` when `settings.DEBUG=true`, `JSONRenderer` otherwise; add `add_log_level` and `TimeStamper` processors; bind `request_id` as a no-op processor stub for future middleware use
- [x] Implement `backend/app/core/database.py` — `create_async_engine(settings.DATABASE_URL)`; `AsyncSessionLocal = async_sessionmaker(...)`; `get_db` async generator yielding `AsyncSession`; expose `Base = declarative_base()` imported by all models
- [x] Implement `backend/app/main.py` — import `backend.app.core.logging` first (triggers structlog config); FastAPI app factory; `CORSMiddleware` with `settings.CORS_ORIGINS`; async lifespan hook (test DB connectivity on startup — log warning and raise if unreachable); register exception handlers from `exceptions.py`; `GET /health` route (runs `SELECT 1`, returns 200 or 503)
- [x] Create `backend/alembic/` via `alembic init`; rewrite `env.py` to: import `settings.DATABASE_URL`, use `run_async_engine` + `run_sync` pattern for async migrations, auto-import `Base.metadata` (which imports all `backend/app/models/` modules so Alembic sees every table)
- [x] Create initial Alembic migration: empty schema baseline (`alembic revision --autogenerate -m "init"`)
- [x] Implement `backend/app/core/exceptions.py` — register handlers on `app` for: `HTTPException` (log at WARNING, return `{"detail": exc.detail}` with `exc.status_code`), `RequestValidationError` (return 422 with FastAPI's default `{"detail": errors}` body), unhandled `Exception` (log full traceback at ERROR, return 500 `{"detail": "internal server error"}`)
- [x] Create `backend/tests/conftest.py` — define: `app` fixture overriding `DATABASE_URL` to `sqlite+aiosqlite:///:memory:`; `async_client` fixture returning `httpx.AsyncClient(app=app, base_url="http://test")` as async context manager; `db_session` fixture running `create_all` on setup and `drop_all` on teardown
- [x] Create `backend/tests/unit/` and `backend/tests/integration/` directories with `__init__.py` stubs

### Test strategy

- **Unit** (no DB required — Arrange-Act-Assert pattern):
  - `config.py`: `Settings` loads values from patched environment; `SECRET_KEY` under 32 chars raises `ValidationError`; `CORS_ORIGINS` defaults to `["*"]` when `DEBUG=true`; empty `CORS_ORIGINS` with `DEBUG=false` raises `ValueError`
  - `logging.py`: `ConsoleRenderer` selected when `DEBUG=true`; `JSONRenderer` selected when `DEBUG=false`
  - `exceptions.py`: `HTTPException` handler returns correct status code and `{"detail": ...}` body; `RequestValidationError` handler returns 422; catch-all 500 handler returns `{"detail": "internal server error"}`

- **Integration** (uses `async_client` + SQLite in-memory):
  - `GET /health` returns 200 `{"status": "ok"}` when DB is reachable
  - `GET /health` returns 503 `{"status": "error", "detail": "db unavailable"}` when DB engine is patched to raise on connect
  - Lifespan hook creates and releases DB connection without error on clean startup
  - `get_db` dependency yields a working `AsyncSession` that can execute a simple query

- **Negative**:
  - Missing `SECRET_KEY` → `ValidationError` raised at `Settings()` instantiation (before app starts)
  - Invalid `DATABASE_URL` dialect → error logged and app exits non-zero at lifespan startup
  - `GET /health` with DB deliberately broken → 503 (not unhandled 500)
  - `POST /nonexistent` → FastAPI 404 `{"detail": "Not Found"}` (default shape preserved)

- **Live E2E** (`@pytest.mark.live_api` — requires `make dev` running):
  - `GET http://localhost:8000/health` → 200 `{"status": "ok"}` — validates full path: FastAPI → SQLAlchemy → Postgres container
  - Skipped by default: `pytest -m "not live_api"`

### Documentation

- **`CLAUDE.md`** — update: env variable table to add `CORS_ORIGINS` row; architecture section for `backend/app/core/` to note structlog import-time init and DEBUG-aware format
- **`CHANGELOG.md`** — add `### Added` entry under `## [Unreleased]` when item is implemented: backend foundation (FastAPI, async SQLAlchemy, Alembic, structlog)
- **`backend/pyproject.toml`** — created (new file)
- **`backend/alembic/README`** — auto-generated by `alembic init`; no manual edits required

---

## 3. Data Models & Migrations

Define the core domain models: products, price history, price sources, user alerts, and notification logs.

### Tasks

- [ ] `backend/app/models/product.py` — `Product` (id, name, url, source_type, created_at, updated_at, is_active)
- [ ] `backend/app/models/price_history.py` — `PriceRecord` (id, product_id FK, price, currency, captured_at, raw_html_hash)
- [ ] `backend/app/models/alert.py` — `PriceAlert` (id, product_id FK, threshold_price, direction [above/below], is_active, notified_at)
- [ ] `backend/app/models/notification_log.py` — `NotificationLog` (id, alert_id FK, channel, payload, sent_at, status)
- [ ] `backend/app/schemas/` — Pydantic v2 response/request schemas mirroring each model; keep models and schemas strictly separated
- [ ] Generate and apply Alembic migration for full schema

### Test strategy

- **Unit**: schema serialisation round-trips; model `__repr__` helpers
- **Integration**: create/read/delete each model via SQLAlchemy session (uses test DB)
- **Negative**: FK constraint violations raise `IntegrityError`; invalid enum values rejected by schema
- **Live E2E**: not required

---

## 4. Price Scraping Engine

Implement the pluggable scraping layer that fetches product pages, extracts prices, and stores price records. Start with two source adapters: generic CSS-selector and Amazon.

### Tasks

- [ ] Define `backend/app/scrapers/base.py` — abstract `BaseScraper` with `fetch(url) -> ScrapedResult` and `extract_price(html) -> Decimal | None`
- [ ] Implement `backend/app/scrapers/generic.py` — CSS-selector-driven scraper (selector stored on `Product`)
- [ ] Implement `backend/app/scrapers/amazon.py` — Amazon-specific price extraction (handle dynamic rendering via httpx + selective parsing)
- [ ] `backend/app/scrapers/registry.py` — map `source_type` enum to scraper class; raise `UnknownSourceError` for unregistered types
- [ ] `backend/app/services/price_service.py` — `record_price(product_id, scraped_result)`: deduplicate by html hash, persist `PriceRecord`, trigger alert evaluation
- [ ] `backend/app/services/alert_service.py` — `evaluate_alerts(product_id)`: load active alerts, compare against latest price, mark triggered alerts
- [ ] Add `User-Agent` rotation and request throttling to respect `robots.txt` conventions
- [ ] Add `backend/app/scrapers/http_client.py` — shared async httpx client with retry logic (exponential back-off, 3 retries)

### Test strategy

- **Unit**: `extract_price` for each adapter with fixture HTML; registry lookup; deduplication logic; alert evaluation threshold comparisons
- **Integration**: `record_price` end-to-end with test DB; alert `notified_at` updated correctly
- **Negative**: HTTP 404/5xx → `ScraperError` raised; malformed HTML → `None` returned without crash; unknown source_type → `UnknownSourceError`
- **Live E2E**: `@pytest.mark.live_api` hitting a stable public product URL (run manually / on-demand)

---

## 5. Celery Task Infrastructure

Configure Celery with Redis broker/backend, scheduled periodic scraping via Celery Beat, and task monitoring.

### Tasks

- [ ] `backend/app/workers/celery_app.py` — Celery factory; configure broker/backend from `Settings`; autodiscover tasks from `backend/app/tasks/`
- [ ] `backend/app/tasks/scrape.py` — `scrape_product(product_id: int)` task: fetch → extract → `price_service.record_price`; handle retries and DLQ logging
- [ ] `backend/app/tasks/schedule.py` — `beat_schedule` dict; default: scrape all active products every 30 minutes
- [ ] `backend/app/tasks/notify.py` — `send_notification(alert_id: int)` task: load alert, dispatch notification (email stub + webhook), persist `NotificationLog`
- [ ] Wire `celery-worker` and `celery-beat` Docker services in compose files
- [ ] Add `make worker` and `make beat` targets to Makefile for local development
- [ ] Implement Flower monitoring service in `docker-compose.dev.yml` (port 5555)

### Test strategy

- **Unit**: task signature; retry logic; beat schedule has correct keys and intervals
- **Integration**: dispatch `scrape_product` via `task.apply()` against test DB; verify `PriceRecord` created
- **Negative**: scraper raises exception → task retries N times then logs to DLQ; DB unavailable → graceful failure
- **Live E2E**: not required (worker/beat integration covered by compose smoke test)

---

## 6. REST API Endpoints

Expose all domain operations via a versioned FastAPI router (`/api/v1`).

### Tasks

- [ ] `backend/app/api/v1/products.py` — CRUD: `POST /products`, `GET /products`, `GET /products/{id}`, `PATCH /products/{id}`, `DELETE /products/{id}`
- [ ] `backend/app/api/v1/prices.py` — `GET /products/{id}/prices` (paginated history); `POST /products/{id}/scrape` (trigger on-demand scrape)
- [ ] `backend/app/api/v1/alerts.py` — CRUD: `POST /alerts`, `GET /alerts`, `GET /alerts/{id}`, `PATCH /alerts/{id}`, `DELETE /alerts/{id}`
- [ ] `backend/app/api/v1/router.py` — aggregate all sub-routers; mount at `/api/v1`
- [ ] Add pagination using `limit`/`offset` query params; enforce max page size 100
- [ ] Add OpenAPI tags, descriptions, and response model annotations to all routes
- [ ] Generate and commit `backend/openapi.json` snapshot for contract testing

### Test strategy

- **Unit**: route parameter validation; pagination helpers
- **Integration**: full HTTP round-trips via `httpx.AsyncClient` against `TestClient`; assert correct status codes and response shapes
- **Negative**: `GET /products/99999` → 404; `POST /products` with missing fields → 422; `POST /products/{id}/scrape` on inactive product → 400
- **Live E2E**: not required

---

## 7. Frontend — React Application

Scaffold and implement the React frontend: product dashboard, price history charts, alert management, and real-time update polling.

### Tasks

- [ ] Initialise `frontend/` with Vite + React + TypeScript; add `vitest`, `@testing-library/react`, `msw` (mock service worker), `tailwindcss`, `recharts` (price charts), `react-query` (server state)
- [ ] `frontend/src/api/client.ts` — typed Axios/fetch wrapper for `/api/v1`; handle 4xx/5xx with typed errors
- [ ] `frontend/src/pages/Dashboard.tsx` — product list with latest price and alert status badges
- [ ] `frontend/src/pages/ProductDetail.tsx` — price history chart (Recharts `LineChart`) + alert list
- [ ] `frontend/src/pages/AlertManager.tsx` — create/edit/delete alerts; threshold input with currency formatting
- [ ] `frontend/src/components/PriceChart.tsx` — reusable line chart component; supports date-range filtering
- [ ] `frontend/src/hooks/useProducts.ts`, `usePrices.ts`, `useAlerts.ts` — react-query hooks with stale-while-revalidate
- [ ] `frontend/src/store/` — Zustand store for global UI state (selected product, filter state)
- [ ] Add polling for real-time price updates (`refetchInterval: 60_000`)
- [ ] Implement responsive layout with Tailwind; support light/dark mode via `prefers-color-scheme`

### Test strategy

- **Unit**: `PriceChart` renders with mock data; API client formats requests correctly; Zustand store mutations
- **Integration**: `Dashboard` fetches and displays product list (MSW mock); `ProductDetail` renders chart with seeded data
- **Negative**: API returns 500 → error boundary displayed; empty product list → empty-state component shown
- **Live E2E**: not required (frontend-only; covered by integration tests with MSW)

---

## 8. Docker Containerisation

Write production-grade multi-stage Dockerfiles and finalise compose configuration.

### Tasks

- [ ] `docker/backend.Dockerfile` — multi-stage: builder (uv install) + slim runtime; non-root user; health-check
- [ ] `docker/frontend.Dockerfile` — multi-stage: Node build + Nginx static serve; Nginx config with SPA fallback
- [ ] `docker/nginx.conf` — reverse-proxy `/api` to backend; serve frontend static files; gzip compression
- [ ] Finalise `docker-compose.yml` with named volumes, `depends_on` health-checks, resource limits
- [ ] Finalise `docker-compose.dev.yml` overrides: volume mounts for hot-reload, Flower on port 5555, pgAdmin on port 5050
- [ ] Add `make build` (builds all images), `make up` (compose up -d), `make down`, `make logs SERVICE=...` targets
- [ ] Verify `make up` brings the full stack to healthy state within 60 seconds

### Test strategy

- **Unit**: N/A
- **Integration**: `make up` smoke test — `GET /health` returns 200; frontend serves `index.html`
- **Negative**: backend crashes on bad DB URL → exits with non-zero; missing Redis → worker fails fast with log message
- **Live E2E**: not required

---

## 9. Claude Code Agents

Adapt and install agents from `presentation_helper` for price_pulse SDLC workflows.

### Tasks

- [ ] Copy and adapt `.claude/agents/quality.md` — adjust paths to `backend/`, `frontend/`, pytest + vitest gates
- [ ] Copy and adapt `.claude/agents/architecture-maintainer.md` — point at `docs/architecture/repository-architecture.md`
- [ ] Create `.claude/agents/profiling-reviewer.md` — adapted for backend `pytest-benchmark` + frontend Lighthouse CLI
- [ ] Copy `.github/agents/plan-review.agent.md` — update test-layer taxonomy to include frontend vitest
- [ ] Copy `.github/agents/module-grouping-reviewer.agent.md` — scope to `backend/app/` Python flat-file drift
- [ ] Copy `.github/agents/quality.agent.md` — update gate commands for this stack
- [ ] Copy `.github/agents/profiling-reviewer.agent.md` — adapt profiling paths for price_pulse layout
- [ ] Create `.github/skills/plan-review/findings.md` (empty stub with header)
- [ ] Create `docs/architecture/repository-architecture.md` — initial C4 system/container/component doc

### Test strategy

- **Unit**: N/A (agent files are markdown)
- **Integration**: manually invoke each agent and verify it produces expected output shape
- **Negative**: N/A
- **Live E2E**: N/A

---

## 10. CI/CD & Quality Gates

Wire GitHub Actions, configure quality thresholds, and add pre-commit hooks.

### Tasks

- [ ] `.github/workflows/ci.yml` — jobs: `lint` (ruff + eslint), `test-backend` (pytest --cov), `test-frontend` (vitest --coverage), `build` (docker build), `security` (pip-audit + npm audit)
- [ ] Configure coverage upload to Codecov
- [ ] Add `.pre-commit-config.yaml` — ruff (Python), eslint + prettier (JS/TS), trailing whitespace, end-of-file-fixer
- [ ] `config/quality-thresholds.toml` — define CC, MI, Halstead, coverage targets
- [ ] `make quality` target — runs radon CC/MI/Halstead on backend; vitest coverage on frontend; reports pass/fail
- [ ] Add `make lint` and `make format` targets (ruff check/format for backend; eslint --fix + prettier for frontend)
- [ ] Enforce branch protection: require CI green before merge

### Test strategy

- **Unit**: threshold config is parseable TOML; quality report JSON schema validates
- **Integration**: `make quality` exits 0 on clean codebase; exits 1 on injected complexity violation
- **Negative**: missing `config/quality-thresholds.toml` → clear error message, not silent pass
- **Live E2E**: not required

---

## References

- FastAPI docs: https://fastapi.tiangolo.com/
- Celery docs: https://docs.celeryq.dev/
- SQLAlchemy async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Alembic: https://alembic.sqlalchemy.org/
- Vitest: https://vitest.dev/
- React Query: https://tanstack.com/query/latest
- MSW: https://mswjs.io/
- Recharts: https://recharts.org/
