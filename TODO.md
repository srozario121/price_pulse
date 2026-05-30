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

### Design decisions (resolved)

- **Native Postgres ENUM types**: All enumerated fields use `native_enum=True` SQLAlchemy `Enum` columns backed by named Postgres ENUM types. Four ENUM types created in the Alembic migration: `source_type_enum` (`generic`, `amazon`, `ebay`, `currys`), `alert_direction_enum` (`above`, `below`), `notification_channel_enum` (`email`, `webhook`), `notification_status_enum` (`pending`, `sent`, `failed`). Rationale: DB-level type enforcement; Postgres ENUM is more storage-efficient than VARCHAR + CHECK.
- **SQLite / native ENUM conflict**: Native PG ENUM types are incompatible with the SQLite in-memory test DB used in item 2. Resolution: integration tests (CRUD, FK, cascade) use a real Postgres container via `testcontainers[postgres]`; a new session-scoped `pg_engine` fixture is added to `tests/conftest.py` that integration tests opt into by requesting `pg_engine` instead of `db_engine`. Unit tests (schema round-trips, `__repr__`) keep SQLite. Rationale: clean separation — unit tests remain fast; integration tests match the production dialect.
- **Price column precision**: `NUMERIC(12, 4)` — exact decimal representation, no floating-point drift, supports prices up to 99,999,999.9999. Rationale: monetary values require exact arithmetic.
- **currency field**: `VARCHAR(3)`, default `'GBP'`. ISO 4217 code. Rationale: default simplifies UK-focused scrapers while remaining ISO-standard.
- **raw_html_hash**: `VARCHAR(64)` (SHA-256 hex digest, 64 chars). Indexed (non-unique) on `PriceRecord(raw_html_hash)` for deduplication lookups in `price_service`. Deduplication query: `WHERE product_id = ? AND raw_html_hash = ?`. No unique constraint — different products may have identical HTML. Rationale: SHA-256 collision resistance is adequate; per-product deduplication is the correct scope.
- **Cascade delete policy**: Full `cascade="all, delete-orphan"` on all FK relationships. `Product` deleted → `PriceRecord` + `PriceAlert` deleted → `NotificationLog` deleted. Rationale: no orphaned history for a removed product; consistent housekeeping.
- **Product.url uniqueness**: Unique constraint on `Product.url`. Duplicate URL insert returns 409 Conflict at the API layer. Rationale: prevents tracking the same product twice.
- **updated_at auto-update**: ORM-level `server_default=func.now()`, `onupdate=func.now()` on the `Column` definition. Fires on every ORM-mediated UPDATE. Rationale: no DB trigger needed; consistent with async ORM usage pattern.
- **notified_at vs sent_at**: Both retained with distinct purposes. `PriceAlert.notified_at` is a denormalized quick-check flag (when was this alert last notified — avoids a JOIN on every alert read). `NotificationLog.sent_at` records per-delivery timestamps for audit and retry. Rationale: different query patterns; redundancy is intentional and documented.
- **Schema file organisation**: One file per domain with `Base`, `Create`, `Read`, `Update` variants. Files: `schemas/product.py` (`ProductBase`, `ProductCreate`, `ProductRead`, `ProductUpdate`), `schemas/price.py` (`PriceRecordCreate`, `PriceRecordRead`), `schemas/alert.py` (`AlertBase`, `AlertCreate`, `AlertRead`, `AlertUpdate`), `schemas/notification.py` (`NotificationLogRead`). Models and schemas remain strictly separated. Rationale: FastAPI convention; independent evolution of API contracts.
- **Database indexes**: Four explicit composite/single-column indexes added in the migration: `ix_price_record_product_captured` on `(product_id, captured_at DESC)` for paginated price history; `ix_price_record_html_hash` on `(raw_html_hash)` for deduplication; `ix_price_alert_product_active` on `(product_id, is_active)` for alert evaluation; `ix_notification_log_alert_sent` on `(alert_id, sent_at DESC)` for notification history. Rationale: hot query paths identified from the scraping and alert evaluation data flows.
- **Alembic migration design**: One combined revision creates all four tables, all four named PG ENUM types, all FK relationships, and all four indexes atomically. Rationale: entire schema created or rolled back as one unit; simpler revision history.
- **testcontainers dependency**: `testcontainers[postgres]` added to `backend/pyproject.toml` dev dependencies in this item so the `pg_engine` fixture is immediately usable.

### Tasks

- [x] Add `testcontainers[postgres]>=0.7` to `[dependency-groups] dev` in `backend/pyproject.toml`
- [x] Add session-scoped `pg_engine` Postgres testcontainer fixture to `backend/tests/conftest.py`: starts a `PostgresContainer`, yields a `create_async_engine` pointing at the container, runs `Base.metadata.create_all` / `drop_all` for setup and teardown; integration tests opt in by requesting `pg_engine` instead of `db_engine`
- [x] `backend/app/models/product.py` — `Product`: `id` (BigInteger PK autoincrement), `name` (String, not null), `url` (String, unique, not null), `source_type` (PG ENUM `source_type_enum`: `generic`/`amazon`/`ebay`/`currys`, not null), `css_selector` (String, nullable — used by generic scraper in item 4), `created_at` (DateTime, `server_default=func.now()`), `updated_at` (DateTime, `server_default=func.now()`, `onupdate=func.now()`), `is_active` (Boolean, default `True`); relationships to `PriceRecord` and `PriceAlert` with `cascade="all, delete-orphan"`
- [x] `backend/app/models/price_history.py` — `PriceRecord`: `id` (BigInteger PK autoincrement), `product_id` (BigInteger FK → `product.id`, not null), `price` (NUMERIC(12,4), not null), `currency` (VARCHAR(3), default `'GBP'`, not null), `captured_at` (DateTime, `server_default=func.now()`), `raw_html_hash` (VARCHAR(64), nullable); back-reference relationship to `Product`
- [x] `backend/app/models/alert.py` — `PriceAlert`: `id` (BigInteger PK autoincrement), `product_id` (BigInteger FK → `product.id`, not null), `threshold_price` (NUMERIC(12,4), not null), `direction` (PG ENUM `alert_direction_enum`: `above`/`below`, not null), `is_active` (Boolean, default `True`), `notified_at` (DateTime, nullable — denormalized last-notified timestamp); back-reference to `Product`; relationship to `NotificationLog` with `cascade="all, delete-orphan"`
- [x] `backend/app/models/notification_log.py` — `NotificationLog`: `id` (BigInteger PK autoincrement), `alert_id` (BigInteger FK → `price_alert.id`, not null), `channel` (PG ENUM `notification_channel_enum`: `email`/`webhook`, not null), `payload` (JSON, nullable), `sent_at` (DateTime, `server_default=func.now()`), `status` (PG ENUM `notification_status_enum`: `pending`/`sent`/`failed`, not null, default `pending`); back-reference to `PriceAlert`
- [x] `backend/app/schemas/product.py` — `ProductBase` (name, url, source_type, css_selector, is_active), `ProductCreate(ProductBase)`, `ProductRead(ProductBase)` (adds id, created_at, updated_at; `model_config = ConfigDict(from_attributes=True)`), `ProductUpdate` (all fields Optional)
- [x] `backend/app/schemas/price.py` — `PriceRecordCreate` (product_id, price, currency, raw_html_hash), `PriceRecordRead` (adds id, captured_at; `from_attributes=True`)
- [x] `backend/app/schemas/alert.py` — `AlertBase` (product_id, threshold_price, direction, is_active), `AlertCreate(AlertBase)`, `AlertRead(AlertBase)` (adds id, notified_at; `from_attributes=True`), `AlertUpdate` (all fields Optional)
- [x] `backend/app/schemas/notification.py` — `NotificationLogRead` (id, alert_id, channel, payload, sent_at, status; `from_attributes=True`)
- [x] Uncomment model imports in `backend/alembic/env.py` at the `# ── Models` stub (line ~25): `from app.models import product, price_history, alert, notification_log`
- [x] Generate combined Alembic migration: `alembic revision --autogenerate -m "add_core_domain_models"`; verify the generated file creates: four PG ENUM types, four tables with correct column types and FK constraints, and four named indexes (`ix_price_record_product_captured`, `ix_price_record_html_hash`, `ix_price_alert_product_active`, `ix_notification_log_alert_sent`)
- [x] Apply migration: `alembic upgrade head` and verify it runs cleanly against a running Postgres instance

### Test strategy

- **Unit** (SQLite in-memory via `db_session` — Arrange-Act-Assert):
  - Schema round-trips: `ProductCreate` → `ProductRead` serialisation preserves all fields; `AlertCreate` with direction `'sideways'` rejected by Pydantic validator; `PriceRecordCreate` with `price=None` raises `ValidationError`
  - `PriceRecordRead.currency` defaults to `'GBP'` when not provided
  - `ProductUpdate` with partial fields leaves unset fields as `None` (all-Optional schema)
  - Model `__repr__`: `Product.__repr__` includes id and name; `PriceRecord.__repr__` includes product_id and price

- **Integration** (Postgres via `pg_engine` testcontainer — Arrange-Act-Assert):
  - Create/read each model: insert `Product`, `PriceRecord`, `PriceAlert`, `NotificationLog`; re-fetch via session; assert all fields persisted correctly including ENUM values
  - FK navigation: fetch `product.price_records` relationship; assert list contains the inserted record
  - Cascade delete: delete `Product` → assert `PriceRecord` and `PriceAlert` rows removed; assert `NotificationLog` removed via alert cascade
  - `updated_at` auto-update: update `Product.name`; flush session; assert `updated_at` is later than `created_at`
  - Index existence: query `pg_indexes` system table; assert all four named indexes exist on their respective tables

- **Negative** (Postgres via `pg_engine` testcontainer — Arrange-Act-Assert):
  - FK violation: insert `PriceRecord` with non-existent `product_id` → `IntegrityError`
  - Unique violation: insert two `Product` rows with same URL → `IntegrityError`
  - Invalid native ENUM: attempt to insert `PriceAlert` with `direction='sideways'` bypassing Pydantic → `StatementError` / DB-level ENUM rejection
  - Not-null violation: insert `PriceRecord` with `price=None` → `IntegrityError`

- **Live E2E** (`@pytest.mark.live_api` — requires `make dev` running):
  - Verify migration applied: connect to the `make dev` Postgres; query `information_schema.tables` and assert all four tables exist; query `pg_type` catalogue and assert all four ENUM types exist
  - Skipped by default: `pytest -m "not live_api"`

### Documentation

- **`backend/pyproject.toml`** — update: add `testcontainers[postgres]>=0.7` to `[dependency-groups] dev`
- **`backend/tests/conftest.py`** — update: add session-scoped `pg_engine` Postgres testcontainer fixture alongside the existing `db_engine` SQLite fixture
- **`backend/alembic/env.py`** — update: uncomment model imports stub at line ~25
- **`CLAUDE.md`** — update: architecture section for `backend/app/models/` to document all four models, key fields, and enum types; test structure section to note integration tests use `pg_engine` (Postgres testcontainer) not SQLite
- **`CHANGELOG.md`** — update at implementation time: add `### Added` entry under `## [Unreleased]`: core domain models (`Product`, `PriceRecord`, `PriceAlert`, `NotificationLog`), native Postgres ENUM types, Alembic migration with indexes

---

## 4. Price Scraping Engine

Implement the pluggable scraping layer that fetches product pages, extracts prices, and stores price records. Two source adapters: generic CSS-selector (httpx + parsel) and Amazon (Playwright headless browser).

**Depends on**: Item 3 (Data Models & Migrations) — must be complete before item 4; `Product`, `PriceRecord`, `PriceAlert` models and the `source_type_enum` native Postgres ENUM are created there.

### Design decisions (resolved)

- **Amazon rendering strategy**: Playwright headless browser (`playwright.async_api`). Amazon product pages are JS-rendered; httpx alone cannot reliably extract prices. Rationale: the only reliable approach without a third-party proxy service.
- **Playwright + Celery async model**: `celery[asyncio]` pool for all Celery workers. Amazon scrape tasks execute as native async tasks. Item 5 (`workers/celery_app.py`) configures the pool. Rationale: clean async execution without a `asyncio.run()` wrapper per task.
- **Playwright browser lifecycle**: Per-task — each `AmazonScraper.fetch()` call launches a fresh browser context and closes it on completion. Fully isolated; no state leak between tasks. Rationale: correctness guarantee; performance impact acceptable at a 30-minute polling interval.
- **Playwright base image**: `mcr.microsoft.com/playwright/python` (Microsoft's official image, includes Chromium). The `celery-playwright` Docker service uses this. The main backend image is unchanged. Rationale: avoids ~500 MB Chromium in the backend image.
- **celery-playwright service**: Separate Docker service for Amazon scraping in both `docker-compose.yml` and `docker-compose.dev.yml`. Consumes only the `playwright` Celery queue. Rationale: production topology requires Amazon scraping from day one; isolating it prevents backend image bloat.
- **Celery queue routing**: Amazon scrape tasks dispatched to the `'playwright'` queue; all others to `'default'`. Item 5 implements `CELERY_TASK_ROUTES`. Item 4 documents the requirement. Rationale: only the Playwright-capable worker handles Amazon tasks.
- **ScrapedResult schema**: Pydantic model in `backend/app/schemas/scraper.py`. Fields: `url: str`, `html: str`, `html_hash: str` (SHA-256 hex, 64 chars), `price: Decimal | None`, `currency: str | None`, `scraped_at: datetime`, `extraction_status: ExtractionStatus`. `BaseScraper.fetch()` always returns `ScrapedResult`; HTTP errors are encoded as `extraction_status='http_error'` rather than raised. Rationale: uniform return type lets `price_service` handle all outcomes without try/except at the call site.
- **ExtractionStatus enum**: Defined in `backend/app/models/enums.py`. Values: `OK = 'ok'`, `EXTRACTION_FAILED = 'extraction_failed'`, `HTTP_ERROR = 'http_error'`. Used by both `ScrapedResult` (scraper layer) and `PriceRecord.extraction_status` (ORM model). `extraction_failed`: page loaded but price not found. `http_error`: HTTP failure after all retries. Rationale: shared enum avoids duplication across layers; placing in `models/enums.py` mirrors item 3's native ENUM pattern.
- **PriceRecord schema amendment (cross-item)**: Item 3 defined `PriceRecord.price` as `NUMERIC(12,4) NOT NULL` and `currency` as `VARCHAR(3) NOT NULL DEFAULT 'GBP'`. Item 4's decision to store all scrape attempts (including failed ones) with `price=NULL` requires item 4 to issue an Alembic migration making both `price` and `currency` nullable. Rationale: fail-path records are stored for observability; nullable columns are the correct modelling.
- **HTML parser**: `parsel` (Scrapy's selector library). CSS and XPath selectors via a consistent API. Rationale: single dep; production-proven in Scrapy; avoids the `beautifulsoup4` + `lxml` two-library split.
- **Amazon extraction strategy**: `page.evaluate()` JS snippet targeting `ld+json` blocks with `@type` of `Product` or `Offer`; extracts `price` and `priceCurrency`. Returns `ScrapedResult(extraction_status='extraction_failed')` if no ld+json match. No CSS selector fallback — fail cleanly rather than returning a wrong value. Rationale: ld+json is the most stable Amazon data surface; CSS selectors break frequently.
- **SourceType enum**: `SourceType(str, Enum)` defined in `backend/app/scrapers/registry.py`. Values mirror the `source_type_enum` Postgres ENUM created in item 3: `GENERIC = 'generic'`, `AMAZON = 'amazon'`, `EBAY = 'ebay'`, `CURRYS = 'currys'`. Item 4 only implements scrapers for `GENERIC` and `AMAZON`; `EBAY` and `CURRYS` entries raise `UnknownSourceError` until implemented. Rationale: Python enum stays in sync with the DB type; future scraper items extend the registry without schema migration.
- **Scraper exceptions**: `backend/app/scrapers/exceptions.py` — `ScraperError(Exception)` (base) and `UnknownSourceError(ScraperError)`. `ScraperError` is raised only for unexpected runtime exceptions (socket errors, Playwright crashes). HTTP-level failures are encoded in `ScrapedResult`. Rationale: keeps scraper-layer errors separate from core HTTP/app exception handlers.
- **GenericScraper selector fields**: `Product.css_selector` (already in item 3 schema — nullable String) is required at scrape time; `ScraperError` raised if `None`. A second field `css_selector_currency` (nullable VARCHAR) is added via item 4 migration; if absent or no match, currency defaults to `'USD'`.
- **Currency detection**: `GenericScraper` uses `Product.css_selector_currency`; maps symbol → ISO code via hardcoded dict (`'$'` → `'USD'`, `'£'` → `'GBP'`, `'€'` → `'EUR'`; unknown symbols stored as-is, defaults to `'USD'`). `AmazonScraper` reads `priceCurrency` from ld+json. Rationale: per-product selector flexibility without a runtime config lookup.
- **HTTP retry policy**: Retries on 5xx, 429, and 403 status codes; 3 retries with exponential back-off (1s, 2s, 4s). 429 honours `Retry-After` header (60s default if absent). After all retries exhausted, returns `ScrapedResult(extraction_status='http_error', price=None)`. Rationale: 403 is often a transient bot-detection block that recovers after a brief delay.
- **User-Agent rotation**: Pool of 8 common browser UA strings hardcoded in `http_client.py`; one selected randomly per request. Not configurable via `Settings`. Rationale: adequate at this scale; adds config complexity without clear benefit.
- **Per-domain rate limiting**: Redis-backed. Key: `rate_limit:{domain}`, TTL = `settings.SCRAPE_MIN_DELAY_SECONDS` (default 2s). Shared across all workers. `http_client.py` checks Redis and sleeps if within the TTL window. Rationale: global limit prevents multiple concurrent workers from flooding a domain.
- **robots.txt compliance (log-and-proceed)**: On first request to a domain, `http_client.py` fetches `/robots.txt` and caches it in Redis (`robots:{domain}`, TTL 1 hour). Checks before each fetch; emits structlog WARNING for disallowed paths but proceeds. Rationale: log-and-proceed satisfies ethical scraping intent while keeping the platform functional for legitimate retail monitoring.
- **HTML hash algorithm**: SHA-256 of the full raw HTML string (hex, 64 chars). Computed before parsing. Matches `PriceRecord.raw_html_hash VARCHAR(64)` column from item 3. Rationale: consistent with item 3's field specification.
- **Deduplication policy**: `price_service.record_price()` compares the new `html_hash` against the most recent `PriceRecord.raw_html_hash` for the product. If equal (regardless of `extraction_status`), skip storing and return the existing record. Rationale: same HTML = same page state = no new data, even if the previous extraction failed.
- **PriceRecord stored for all outcomes**: Every scrape attempt produces a `PriceRecord` row. `extraction_status='ok'`: price extracted. `extraction_status='extraction_failed'`: page loaded, no price found (`price=NULL`). `extraction_status='http_error'`: HTTP failure (`price=NULL`). Rationale: enables scrape-success-rate analytics.
- **Alert evaluation on failed records**: `alert_service.evaluate_alerts()` returns early (structlog WARNING) when latest `PriceRecord.extraction_status != 'ok'`. Rationale: prevents spurious alerts from transient scrape failures.
- **Alert cooldown**: After triggering, `PriceAlert.notified_at` is set to `now()`. `evaluate_alerts()` skips an alert if `now() < notified_at + timedelta(hours=24)` (24h constant in `alert_service.py`). Item 5 promotes this to `Settings.ALERT_COOLDOWN_HOURS`. Rationale: prevents notification spam without requiring the user to manually re-enable the alert.
- **Notification dispatch stub**: `backend/app/services/notifications.py` — `notify_alert(alert_id: int) -> None` logs a structlog event and no-ops. Item 5 replaces this with `send_notification.delay(alert_id)`. Rationale: alert evaluation is fully testable in item 4 without a running Celery broker.

### Tasks

**Schema and type definitions**
- [x] Create `backend/app/models/enums.py` — define `ExtractionStatus(str, Enum)` with `OK = 'ok'`, `EXTRACTION_FAILED = 'extraction_failed'`, `HTTP_ERROR = 'http_error'`
- [x] Create `backend/app/schemas/scraper.py` — define `ScrapedResult` Pydantic model: `url: str`, `html: str`, `html_hash: str`, `price: Decimal | None`, `currency: str | None`, `scraped_at: datetime`, `extraction_status: ExtractionStatus`

**Scraper layer**
- [x] Create `backend/app/scrapers/exceptions.py` — `ScraperError(Exception)` and `UnknownSourceError(ScraperError)`
- [x] Define `backend/app/scrapers/base.py` — abstract `BaseScraper` with abstract `fetch(url: str) -> ScrapedResult`; protected `_compute_hash(html: str) -> str` (SHA-256 hex)
- [x] Implement `backend/app/scrapers/http_client.py` — async httpx client: 8-UA string pool (random selection per request); per-domain Redis rate limit (key `rate_limit:{domain}`, TTL = `settings.SCRAPE_MIN_DELAY_SECONDS`); robots.txt Redis cache (key `robots:{domain}`, TTL 1 hour, log-and-proceed for disallowed paths); retry on 5xx / 429 / 403 with 1s/2s/4s back-off; 429 honours `Retry-After`; returns `ScrapedResult(extraction_status='http_error')` after retries exhausted
- [x] Implement `backend/app/scrapers/generic.py` — `GenericScraper(BaseScraper)`: fetches via `http_client`; uses `parsel.Selector` with `Product.css_selector` (raises `ScraperError` if `None`); extracts currency via `Product.css_selector_currency` mapping symbol → ISO code; returns fully populated `ScrapedResult`
- [x] Implement `backend/app/scrapers/amazon.py` — `AmazonScraper(BaseScraper)`: per-task Playwright browser (async with `async_playwright()` → launch → new_context → new_page → `goto(url, timeout=30_000)` → `evaluate(js_snippet)` → close); JS snippet targets `ld+json` `schema.org/Product` or `/Offer` for `price` + `priceCurrency`; returns `ScrapedResult(extraction_status='extraction_failed')` if ld+json absent; raises `ScraperError` for unexpected Playwright exceptions
- [x] Create `backend/app/scrapers/registry.py` — `SourceType(str, Enum)` with `GENERIC='generic'`, `AMAZON='amazon'`, `EBAY='ebay'`, `CURRYS='currys'`; `_REGISTRY: dict[SourceType, type[BaseScraper]]` (maps only `GENERIC` and `AMAZON`); `get_scraper(source_type: str) -> BaseScraper` — raises `UnknownSourceError` for unregistered strings (including `ebay` and `currys` until their items)

**Service layer**
- [x] Create `backend/app/services/notifications.py` — `notify_alert(alert_id: int) -> None` stub: logs `{"event": "notify_alert_stub", "alert_id": alert_id}` via structlog and returns `None`. Item 5 replaces with `send_notification.delay(alert_id)`.
- [x] Implement `backend/app/services/price_service.py` — `record_price(product_id: int, scraped_result: ScrapedResult) -> PriceRecord`: (1) fetch most recent `PriceRecord` for product; (2) if `raw_html_hash` matches, return existing record (no insert); (3) otherwise insert new `PriceRecord` (propagates `price`, `currency`, `extraction_status` from `ScrapedResult`); (4) call `alert_service.evaluate_alerts(product_id)` only when `extraction_status == ExtractionStatus.OK`
- [x] Implement `backend/app/services/alert_service.py` — `evaluate_alerts(product_id: int) -> None`: (1) fetch latest `PriceRecord`; (2) return early (structlog WARNING) if `extraction_status != ExtractionStatus.OK`; (3) load all `is_active=True` alerts for product; (4) for each: skip if `now() < notified_at + timedelta(hours=24)`; compare `price` against `threshold_price` by `direction`; if triggered, set `notified_at = now()` and call `notifications.notify_alert(alert.id)`

**Dependencies and configuration**
- [x] Add to `backend/pyproject.toml` runtime deps: `playwright>=1.44`, `parsel>=1.9`; replace `celery[redis]` with `celery[redis,asyncio]>=5.4`
- [x] Add `SCRAPE_MIN_DELAY_SECONDS: int = 2` to `backend/app/core/config.py` `Settings`
- [x] Update `Makefile` `install` target: after `uv sync`, add `cd backend && uv run playwright install chromium`
- [x] Register `live_amazon` pytest marker in `backend/pyproject.toml`: `"live_amazon: marks Amazon live-scrape tests; requires celery-playwright service running; flaky in CI due to bot detection — run manually only"`
- [x] Update `.env.example`: add `SCRAPE_MIN_DELAY_SECONDS=2`

**Migrations**
- [x] Generate Alembic migration: add `css_selector_currency VARCHAR NULL` to `products` table (`alembic revision --autogenerate -m "add_css_selector_currency"`)
- [x] Generate Alembic migration: make `price_records.price` and `price_records.currency` nullable; add `extraction_status VARCHAR(20) NOT NULL DEFAULT 'ok'` with `CHECK` constraint (`alembic revision --autogenerate -m "add_extraction_status_nullable_price"`)

**Docker**
- [x] Create `docker/celery-playwright.Dockerfile` — base: `mcr.microsoft.com/playwright/python:latest`; copies `backend/`; runs `uv sync --no-dev`; CMD: `celery -A app.workers.celery_app worker --pool=asyncio -Q playwright --loglevel=info`
- [x] Add `celery-playwright` service to `docker-compose.yml`: built from `celery-playwright.Dockerfile`; env `CELERY_QUEUES=playwright`; `depends_on: [redis, postgres]`
- [x] Add `celery-playwright` service override to `docker-compose.dev.yml`: volume mount for hot-reload; `DEBUG=true`

### Test strategy

- **Unit** (no DB, no network — Arrange-Act-Assert pattern):
  - `base.py`: `BaseScraper` is abstract — direct instantiation raises `TypeError`; `_compute_hash(html)` returns SHA-256 hex of input
  - `generic.py`: `fetch()` with fixture HTML + valid `css_selector` → `ScrapedResult(extraction_status=ExtractionStatus.OK, price=Decimal('9.99'))`; selector returns no match → `ScrapedResult(extraction_status=ExtractionStatus.EXTRACTION_FAILED, price=None)`; `css_selector=None` → `ScraperError` raised; currency map: `'$'`→`'USD'`, `'£'`→`'GBP'`, `'€'`→`'EUR'`; absent `css_selector_currency` defaults to `'USD'`
  - `amazon.py`: mocked `page.evaluate()` returning valid ld+json → `ScrapedResult(extraction_status=ExtractionStatus.OK, price=Decimal('299.99'))`; `evaluate()` returning `None` → `ScrapedResult(extraction_status=ExtractionStatus.EXTRACTION_FAILED)`
  - `registry.py`: `get_scraper('generic')` → `GenericScraper` instance; `get_scraper('amazon')` → `AmazonScraper` instance; `get_scraper('ebay')` → `UnknownSourceError`; `get_scraper('unknown')` → `UnknownSourceError`
  - `http_client.py`: retries exhausted on 5xx → `ScrapedResult(extraction_status=ExtractionStatus.HTTP_ERROR)`; 429 with `Retry-After` header respected; User-Agent header varies across requests (mocked httpx transport); rate-limit Redis key set/checked before fetch (mocked Redis)
  - `price_service.py`: same `html_hash` → no new DB insert (mock session); new hash → `PriceRecord` inserted; `evaluate_alerts` called when `ExtractionStatus.OK`; `evaluate_alerts` NOT called for `EXTRACTION_FAILED`
  - `alert_service.py`: `direction='below'` + `price < threshold` → `notify_alert` called, `notified_at` set; `direction='above'` + `price > threshold` → triggers; within 24h cooldown → `notify_alert` not called; latest record `extraction_status != OK` → early return, WARNING logged
  - `notifications.py`: `notify_alert(alert_id)` returns `None` and emits expected structlog event

- **Integration** (Postgres via `pg_engine` testcontainer — Arrange-Act-Assert pattern):
  - `price_service.py`: `record_price()` end-to-end — `PriceRecord` row created with correct `product_id`, `price`, `currency`, `extraction_status`; deduplication end-to-end — second call with same `html_hash` returns existing row, row count unchanged; `extraction_status='http_error'` stored with `price=NULL` and `currency=NULL`
  - `alert_service.py`: `evaluate_alerts()` updates `PriceAlert.notified_at` on threshold crossing; cooldown respected — second evaluation within 24h does not call `notify_alert` again; `extraction_status='extraction_failed'` record → `notified_at` unchanged

- **Negative**:
  - HTTP 500 after 3 retries → `ScrapedResult(extraction_status=HTTP_ERROR, price=None)` — no unhandled exception
  - Malformed HTML (selector present, no match) → `ScrapedResult(extraction_status=EXTRACTION_FAILED, price=None)` — no crash
  - `get_scraper('unknown')` → `UnknownSourceError`; `get_scraper('ebay')` → `UnknownSourceError` (no scraper registered yet)
  - `GenericScraper` with `Product.css_selector=None` → `ScraperError` raised before HTTP call
  - Alert threshold not crossed → `PriceAlert.notified_at` remains `None`; `notify_alert` not called
  - Playwright page navigation timeout (30s exceeded) → `ScrapedResult(extraction_status=HTTP_ERROR)`
  - `record_price()` with `extraction_status='extraction_failed'` → record stored with `price=NULL`; `evaluate_alerts` NOT called

- **Live E2E** (`@pytest.mark.live_api` / `@pytest.mark.live_amazon` — skipped by default):
  - `@pytest.mark.live_api`: `GenericScraper.fetch('https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html', css_selector='.price_color')` → `price is not None`, `extraction_status=OK`
  - `@pytest.mark.live_amazon`: `AmazonScraper.fetch('https://www.amazon.com/dp/B00004YMCZ')` → `price is not None`, `extraction_status=OK`; requires `celery-playwright` service running (`make dev`); marked flaky in CI — run manually only

### Documentation

- **`backend/pyproject.toml`** — update: add `playwright`, `parsel` to runtime deps; replace `celery[redis]` with `celery[redis,asyncio]`; add `live_amazon` to pytest markers list
- **`backend/app/core/config.py`** — update: add `SCRAPE_MIN_DELAY_SECONDS: int = 2`
- **`.env.example`** — update: add `SCRAPE_MIN_DELAY_SECONDS=2`
- **`Makefile`** — update: `install` target adds `cd backend && uv run playwright install chromium` after `uv sync`
- **`docker/celery-playwright.Dockerfile`** — create (new file)
- **`docker-compose.yml`** — update: add `celery-playwright` service
- **`docker-compose.dev.yml`** — update: add `celery-playwright` service override with volume mount
- **`CLAUDE.md`** — update: env table to add `SCRAPE_MIN_DELAY_SECONDS`; architecture section for `scrapers/` module tree (`base`, `generic`, `amazon`, `registry`, `http_client`, `exceptions`) and `services/` modules (`price_service`, `alert_service`, `notifications`)
- **`CHANGELOG.md`** — add `### Added` entry under `## [Unreleased]` when implemented: price scraping engine (Playwright, parsel, httpx retry/rate-limit, price/alert services, celery-playwright Docker service)

---

## 5. Celery Task Infrastructure

Configure Celery with Redis broker/backend, scheduled periodic scraping via `celery-redbeat` (dynamic per-product intervals), async task execution, and notification dispatch.

**Depends on**: Item 4 (Price Scraping Engine) — `scrape_product` calls `price_service.record_price`; `send_notification` replaces the `notifications.py` stub created in item 4.

### Design decisions (resolved)

- **Beat scheduler**: `celery-redbeat` (Redis-backed dynamic scheduler). The `docker-compose.yml` already referenced `django_celery_beat.schedulers:DatabaseScheduler` — that is a Django-specific package incompatible with this FastAPI stack; it is replaced by `--scheduler redbeat.RedBeatScheduler` in both compose files. Each product's schedule is stored as a `RedBeatSchedulerEntry` in Redis; `redbeat_redis_url = settings.REDIS_URL`. Rationale: no DB migration required for scheduling; per-product configurable intervals; widely used with non-Django stacks.
- **Celery worker pool**: Asyncio pool configured in `celery_app.py` (`worker_pool = 'celery.concurrency.aio:TaskPool'`). All tasks are native `async def` functions. Consistent with `celery[asyncio]` dependency introduced in item 4. Rationale: clean async execution without `asyncio.run()` wrappers inside tasks.
- **Task DB session pattern**: Each task opens `async with AsyncSessionLocal() as session:` directly. No custom base class. Rationale: mirrors the `get_db` dependency pattern; straightforward and testable without extra infrastructure.
- **`CELERY_RESULT_BACKEND` in Settings**: Added to `Settings` class (default `redis://localhost:6379/1`). Already present in `.env.example` but missing from `config.py`. Celery `result_backend` is configured from `settings.CELERY_RESULT_BACKEND`. Rationale: every env var passes through `Settings` — the constraint set in item 2.
- **Queue routing**: `scrape_product` dispatched to `'playwright'` queue when `product.source_type == SourceType.AMAZON`, otherwise `'default'`. `send_notification` always uses `'default'`. `CELERY_TASK_ROUTES` wired in `celery_app.py`. Rationale: item 4 documented the requirement; item 5 implements it so the `celery-playwright` worker handles only Amazon tasks.
- **`ALERT_COOLDOWN_HOURS` in Settings**: Promoted from the hardcoded `timedelta(hours=24)` in `alert_service.py` (item 4) to `Settings.ALERT_COOLDOWN_HOURS: int = 24`. `alert_service.evaluate_alerts()` reads `settings.ALERT_COOLDOWN_HOURS`. Rationale: item 4 explicitly deferred this promotion to item 5; makes the cooldown configurable without code changes.
- **`notifications.py` stub replacement**: `backend/app/services/notifications.py` `notify_alert()` stub from item 4 is replaced with `send_notification.delay(alert_id)`. Rationale: item 4 created the no-op stub so alert evaluation was fully testable without a broker; item 5 wires the real task.
- **Notification channel on PriceAlert**: Three fields added to `PriceAlert` via the item 5 Alembic migration: `channel` (`notification_channel_enum`, NOT NULL, default `'email'`), `webhook_url` (`VARCHAR(512)`, nullable — used only when `channel='webhook'`), and `whatsapp_number` (`VARCHAR(20)`, nullable, E.164 format e.g. `+447911123456` — used only when `channel='whatsapp'`). `AlertCreate`, `AlertRead`, `AlertUpdate` schemas updated accordingly. Rationale: `NotificationLog.channel` is NOT NULL; the alert creator must declare the delivery channel; per-channel contact fields are co-located on the alert row.
- **`notification_channel_enum` extension**: The native Postgres ENUM `notification_channel_enum` was created in item 3 with values `('email', 'webhook')`. Item 5 extends it with `ALTER TYPE notification_channel_enum ADD VALUE 'whatsapp'` in the same migration that adds the new `price_alert` columns. The Python `NotificationChannel` enum in `backend/app/models/notification_log.py` gains `whatsapp = 'whatsapp'`. Rationale: native ENUM extension is additive (no existing rows affected); single migration keeps the schema coherent.
- **Email stub behaviour**: `send_notification` for `channel='email'` emits a structlog INFO event (`{"event": "email_stub", "alert_id": ..., "payload": ...}`) and sets `NotificationLog.status = 'sent'`. No SMTP in item 5. Rationale: email requires an auth/user model (future item); a logged stub prevents a `NotImplementedError` crash and keeps `status` accurate.
- **Webhook behaviour**: `send_notification` for `channel='webhook'` calls `httpx.AsyncClient().post(alert.webhook_url, json=payload, timeout=10.0)`; sets `status='sent'` on 2xx, `status='failed'` on any error, retries on `httpx.TimeoutException`. Rationale: webhook delivery has no auth dependency; this is a real implementation, not a stub.
- **WhatsApp provider**: **Deferred — pending a spike.** A sub-task (see Tasks below) evaluates the available options (Meta WhatsApp Business Cloud API, Twilio, Vonage, MessageBird/Bird) and produces an ADR before any provider SDK is added as a dependency. Rationale: provider choice has significant implications for pricing, sandbox availability, Python SDK maturity, and rate limits; committing to one without evaluation would be premature.
- **WhatsApp behaviour in item 5 (pre-spike stub)**: `send_notification` for `channel='whatsapp'` emits a structlog WARNING event (`{"event": "whatsapp_stub", "alert_id": ..., "whatsapp_number": ...}`) and sets `NotificationLog.status = 'sent'`. No provider SDK called in item 5. Real delivery is implemented in the follow-on item after the spike ADR is approved. Rationale: the channel is wired end-to-end (enum, model, schema, task routing) so it is testable in item 5; provider integration is a separate concern.
- **Notification payload schema**: `{"product_id": int, "product_name": str, "product_url": str, "current_price": str, "threshold_price": str, "direction": str}` — persisted as JSON in `NotificationLog.payload`. Task resolves: alert → product → latest price record. Rationale: self-contained payload; readable in both notification delivery and audit queries.
- **`scrape_product` retry policy**: `max_retries=3`, exponential countdown `2 ** task.request.retries` seconds (1s, 2s, 4s). On `max_retries` exhaustion, structlog ERROR event logged with full exception info. No separate Redis dead-letter queue in item 5. Rationale: mirrors the HTTP retry policy in `http_client.py`; consistent retry behaviour across layers.
- **`send_notification` retry policy**: `max_retries=3`, `default_retry_delay=5` seconds. On final failure, `NotificationLog.status` set to `'failed'` before raising. Rationale: notification failures should not silently disappear; `status='failed'` enables retry auditing and future re-queue logic.
- **Task time limits**: `task_soft_time_limit=120`, `task_time_limit=150` (seconds) set globally in `celery_app.py`. Rationale: prevents zombie scrape tasks from holding workers indefinitely; soft limit allows graceful cleanup before hard kill.
- **Flower pre-existing**: Flower is already wired in `docker-compose.dev.yml` (from item 1, port 5555). The "Implement Flower monitoring service" task in the original item 5 list is a duplicate — removed. Rationale: no re-implementation needed.

### Tasks

**Dependencies and configuration**
- [x] Add `celery-redbeat>=0.13` to `backend/pyproject.toml` runtime dependencies (no WhatsApp provider SDK until spike ADR is approved)
- [x] Add `CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"` to `Settings` in `backend/app/core/config.py`
- [x] Add `ALERT_COOLDOWN_HOURS: int = 24` to `Settings` in `backend/app/core/config.py`
- [x] Update `.env.example`: add `ALERT_COOLDOWN_HOURS=24` (note: `CELERY_RESULT_BACKEND` already present; no WhatsApp provider vars until spike ADR is approved)
- [x] Update `backend/app/services/alert_service.py`: replace hardcoded `timedelta(hours=24)` with `timedelta(hours=settings.ALERT_COOLDOWN_HOURS)`

**Model and schema amendments (cross-item)**
- [x] Add `whatsapp = 'whatsapp'` to `NotificationChannel(str, enum.Enum)` in `backend/app/models/notification_log.py`
- [x] Add `channel` (`notification_channel_enum`, NOT NULL, default `'email'`), `webhook_url` (`VARCHAR(512)`, nullable), and `whatsapp_number` (`VARCHAR(20)`, nullable, E.164) columns to `PriceAlert` model in `backend/app/models/alert.py`
- [x] Update `backend/app/schemas/alert.py`: add `channel: NotificationChannel = NotificationChannel.email`, `webhook_url: str | None = None`, and `whatsapp_number: str | None = None` to `AlertBase`; propagates to `AlertCreate`, `AlertRead`, `AlertUpdate`
- [x] Generate Alembic migration: `alembic revision --autogenerate -m "add_alert_channel_whatsapp"`; verify the generated file includes: `ALTER TYPE notification_channel_enum ADD VALUE 'whatsapp'` (before the table alteration); adds `channel notification_channel_enum NOT NULL DEFAULT 'email'`, `webhook_url VARCHAR(512) NULL`, and `whatsapp_number VARCHAR(20) NULL` columns to `price_alert` table. Note: autogenerate does not emit `ALTER TYPE … ADD VALUE` automatically — add it manually in `upgrade()` before `op.add_column()` calls

**Celery application factory**
- [x] Implement `backend/app/workers/celery_app.py` — create `Celery` app with: `broker=settings.CELERY_BROKER_URL`, `backend=settings.CELERY_RESULT_BACKEND`, `worker_pool='celery.concurrency.aio:TaskPool'`, `task_soft_time_limit=120`, `task_time_limit=150`, `task_routes={'app.tasks.scrape.scrape_product': {'queue': 'default'}, 'app.tasks.notify.send_notification': {'queue': 'default'}}` (Amazon queue override applied at dispatch time, not in static routes), `redbeat_redis_url=settings.REDIS_URL`; call `app.autodiscover_tasks(['app.tasks'])`

**Tasks**
- [x] Implement `backend/app/tasks/scrape.py` — `async def scrape_product(self, product_id: int)` bound task (`bind=True`): open `AsyncSessionLocal`, fetch `Product`, call `registry.get_scraper(product.source_type).fetch(product.url)`, call `price_service.record_price(product_id, result, session)`; dispatch to `'playwright'` queue if `source_type == SourceType.AMAZON`; on exception call `self.retry(countdown=2 ** self.request.retries, max_retries=3)`; on exhaustion log structlog ERROR with full exception
- [x] Implement `backend/app/tasks/schedule.py` — `register_product_schedule(product_id: int, interval_minutes: int) -> None`: creates or updates a `RedBeatSchedulerEntry` for `scrape_product` with `run_every=timedelta(minutes=interval_minutes)`, key `f"scrape:{product_id}"`; `deregister_product_schedule(product_id: int) -> None`: deletes the redbeat key; `startup_sync_schedules() -> None`: queries all `is_active=True` products from DB and calls `register_product_schedule` for each — called at worker startup via the Celery `worker_ready` signal
- [x] Implement `backend/app/tasks/notify.py` — `async def send_notification(self, alert_id: int)` bound task: open `AsyncSessionLocal`, fetch `PriceAlert` with product and latest `PriceRecord`; build payload `{"product_id", "product_name", "product_url", "current_price", "threshold_price", "direction"}`; create `NotificationLog(alert_id=..., channel=alert.channel, payload=payload, status='pending')`; dispatch based on `alert.channel`: `email` → structlog INFO stub + set `status='sent'`; `webhook` → `httpx.AsyncClient().post(alert.webhook_url, json=payload, timeout=10.0)` + set `status='sent'`/`'failed'`; `whatsapp` → structlog WARNING stub (`{"event": "whatsapp_stub", "alert_id": ..., "whatsapp_number": ...}`) + set `status='sent'` (provider wired in follow-on item after spike ADR); on any exception call `self.retry(countdown=5, max_retries=3)`; on exhaustion set `NotificationLog.status='failed'`, log structlog ERROR
- [x] Update `backend/app/services/notifications.py` — replace `notify_alert` stub body with `from app.tasks.notify import send_notification; send_notification.delay(alert_id)` (preserving the function signature so `alert_service.py` import is unchanged)

**WhatsApp provider spike**
- [x] Spike: evaluate WhatsApp delivery providers — compare **Meta WhatsApp Business Cloud API** (direct, no intermediary), **Twilio**, **Vonage**, and **MessageBird/Bird** across: sandbox/test number availability, Python SDK maturity and async support, per-message pricing at low volume, rate limits, webhook vs polling for delivery receipts, and setup complexity. Document findings and the chosen provider in a new ADR at `docs/decisions/whatsapp-provider.md`. Outcome feeds a follow-on task (add to backlog once ADR is approved) that replaces the `whatsapp_stub` with real delivery.

**Docker**
- [x] Update `docker-compose.yml` celery-beat `command`: replace `django_celery_beat.schedulers:DatabaseScheduler` argument with `--scheduler redbeat.RedBeatScheduler`
- [x] Update `docker-compose.dev.yml` celery-beat `command`: add `--scheduler redbeat.RedBeatScheduler`

**Makefile**
- [x] Add `make worker` target: `cd backend && uv run celery -A app.workers.celery_app worker --pool=asyncio --loglevel=debug`
- [x] Add `make beat` target: `cd backend && uv run celery -A app.workers.celery_app beat --scheduler redbeat.RedBeatScheduler --loglevel=debug`

### Test strategy

- **Unit** (no DB, no broker, no network — Arrange-Act-Assert pattern):
  - `celery_app.py`: `app.conf.broker_url` equals `settings.CELERY_BROKER_URL`; `app.conf.result_backend` equals `settings.CELERY_RESULT_BACKEND`; `app.conf.task_soft_time_limit == 120`; `app.conf.task_time_limit == 150`
  - `scrape.py`: `scrape_product.s(1)` creates a correct task signature; retry countdown doubles (`1s → 2s → 4s`) on each attempt (mock `self.retry()`); on `max_retries=3` exhaustion, structlog ERROR event emitted with exception info
  - `scrape.py` Amazon routing: when `product.source_type == SourceType.AMAZON`, task dispatched with `queue='playwright'` (mock `apply_async`)
  - `schedule.py`: `register_product_schedule(42, 30)` creates a `RedBeatSchedulerEntry` with `run_every=timedelta(minutes=30)` and key `"scrape:42"` (mocked Redis); `deregister_product_schedule(42)` calls `entry.delete()`
  - `notify.py`: email channel → structlog INFO stub emitted; `NotificationLog.status` set to `'sent'`; webhook channel → `httpx.AsyncClient.post` called with correct URL and payload (mocked); on `httpx.TimeoutException`, `status='failed'`; WhatsApp channel → structlog WARNING stub emitted with correct `alert_id` and `whatsapp_number`; `NotificationLog.status` set to `'sent'`; no provider SDK called
  - `alert_service.py`: cooldown reads `settings.ALERT_COOLDOWN_HOURS` (not hardcoded 24); patch `ALERT_COOLDOWN_HOURS=1` → 1-hour cooldown applied

- **Integration** (Postgres via `pg_engine` testcontainer, mocked broker via `CELERY_TASK_ALWAYS_EAGER=True` — Arrange-Act-Assert pattern):
  - `scrape_product.apply(args=[product_id])` eager execution → `PriceRecord` row created in DB with correct `product_id` and `extraction_status`
  - `send_notification.apply(args=[alert_id])` email channel → `NotificationLog` row with `status='sent'` created; `PriceAlert.notified_at` updated
  - `send_notification.apply(args=[alert_id])` webhook channel with unreachable URL → `NotificationLog` row with `status='failed'` created; no unhandled exception
  - `send_notification.apply(args=[alert_id])` WhatsApp channel → `NotificationLog` row with `status='sent'` created; no external HTTP call made (stub path)
  - `startup_sync_schedules()` with 3 active products in DB → 3 redbeat keys written (mocked Redis via `fakeredis`)

- **Negative** (Arrange-Act-Assert pattern):
  - `scrape_product` scraper raises `ScraperError` → task retries 3 times then logs structlog ERROR; no unhandled exception propagates
  - `scrape_product` DB session fails on `AsyncSessionLocal()` → `OperationalError` logged; retry applied
  - `send_notification` with non-existent `alert_id` → structlog WARNING; `NotificationLog` not created; no crash
  - `send_notification` webhook URL is `None` while `channel='webhook'` → structlog ERROR; `status='failed'`; no crash
  - `send_notification` WhatsApp number is `None` while `channel='whatsapp'` → structlog ERROR; `status='failed'`; no crash
  - `register_product_schedule` called with `interval_minutes=0` → raises `ValueError` before writing to Redis
  - `deregister_product_schedule` for non-existent product_id → no exception (idempotent delete)

- **Live E2E** (`@pytest.mark.live_api` — requires `make dev` running):
  - `scrape_product.apply_async(args=[product_id])` dispatched to running Celery worker → poll result (10s timeout); `GET /api/v1/products/{id}/prices` returns at least one `PriceRecord`
  - Skipped by default: `pytest -m "not live_api"`

### Documentation

- **`backend/pyproject.toml`** — update: add `celery-redbeat>=0.13` to runtime deps (no WhatsApp provider SDK until spike ADR approved)
- **`backend/app/core/config.py`** — update: add `CELERY_RESULT_BACKEND` and `ALERT_COOLDOWN_HOURS` to `Settings`
- **`.env.example`** — update: add `ALERT_COOLDOWN_HOURS=24`
- **`docs/decisions/whatsapp-provider.md`** — create: ADR output of the WhatsApp provider spike
- **`backend/app/models/notification_log.py`** — update: add `whatsapp = 'whatsapp'` to `NotificationChannel` enum
- **`backend/app/models/alert.py`** — update: add `channel`, `webhook_url`, and `whatsapp_number` fields
- **`backend/app/schemas/alert.py`** — update: add `channel`, `webhook_url`, and `whatsapp_number` to `AlertBase` / propagated variants
- **`backend/alembic/versions/`** — new file: migration with `ALTER TYPE notification_channel_enum ADD VALUE 'whatsapp'` and columns `channel`, `webhook_url`, `whatsapp_number` on `price_alert`
- **`backend/app/services/alert_service.py`** — update: `ALERT_COOLDOWN_HOURS` sourced from `settings`
- **`backend/app/services/notifications.py`** — update: stub replaced with `send_notification.delay()`
- **`docker-compose.yml`** — update: celery-beat command → `--scheduler redbeat.RedBeatScheduler`
- **`docker-compose.dev.yml`** — update: celery-beat command → `--scheduler redbeat.RedBeatScheduler`
- **`Makefile`** — update: add `worker` and `beat` targets
- **`CLAUDE.md`** — update: env table (add `CELERY_RESULT_BACKEND`, `ALERT_COOLDOWN_HOURS`); architecture section for `workers/` and `tasks/` (all four modules: `celery_app`, `scrape`, `schedule`, `notify`) and `services/notifications.py` promotion
- **`CHANGELOG.md`** — add `### Added` entry under `## [Unreleased]` when implemented: Celery task infrastructure (redbeat dynamic scheduler, async tasks, email/webhook/whatsapp-stub notification dispatch)

---

## 6. REST API Endpoints

Expose all domain operations via a versioned FastAPI router (`/api/v1`).

### Design decisions (resolved)

- **Pagination envelope**: All list endpoints return a typed `PaginatedResponse[T]` envelope — `{"items": [...], "total": N, "limit": N, "offset": N}` — defined in `backend/app/schemas/common.py`. `limit` is capped at 100. Rationale: frontend needs total count to calculate page navigation without a second request.
- **`POST /products/{id}/scrape` response**: Async 202 Accepted. Returns `ScrapeJobResponse` (also in `schemas/common.py`): `task_id: str`, `status: Literal["queued"]`, `product: ProductRead`. Rationale: avoids HTTP timeout on slow pages; caller can display the current product state immediately.
- **Celery stub in item 6**: `backend/app/tasks/scrape.py` is created in item 6 as a plain function stub that raises `NotImplementedError`. Item 5 replaces it with a Celery task. The route imports `scrape_product` from `app.tasks.scrape` — no API contract change required when item 5 lands. Rationale: clean separation of concerns; item 6 is independently testable.
- **`GET /alerts?product_id=X`**: Optional `product_id` query param added to `GET /alerts`. Rationale: frontend loads alerts for a specific product without fetching all alerts and filtering client-side.
- **Active filter on list endpoints**: `GET /products` and `GET /alerts` return all records by default. Optional `?is_active=true/false` filter. Rationale: frontend dashboard wants all records; admin tools can filter to active-only.
- **Integration test database**: Route integration tests use a new `pg_async_client` fixture (mirrors `async_client` but uses `pg_engine` Postgres testcontainer). Rationale: native Postgres ENUMs in item 3 models are incompatible with SQLite; route tests must verify real DB behaviour.
- **HTTP success codes**: 201 Created for all POST endpoints; 204 No Content for all DELETE endpoints; 200 OK for GET and PATCH. Rationale: strictly correct per HTTP spec; separates creation from retrieval in client logs.
- **Conflict handling**: `POST /products` and `PATCH /products/{id}` check for duplicate `url` before insert/update — return 409 Conflict if the URL already exists on another product. `AlertUpdate.product_id` field is removed; product FK is read-only on alerts; passing `product_id` in `PATCH /alerts/{id}` returns 422. Rationale: prevents duplicate tracking and accidental alert reassignment.
- **Price history date range**: `GET /products/{id}/prices` accepts optional `from_dt` and `to_dt` (ISO 8601 datetime) query params in addition to `limit`/`offset`. Rationale: `PriceChart` component needs to load a specific time window (e.g., last 7 days) without fetching all history.
- **Live E2E scope**: Full CRUD smoke against a running `make dev` stack — `@pytest.mark.live_api`. Flow: `POST /products` → `GET /products/{id}` → `PATCH /products/{id}` → `DELETE /products/{id}`; `POST /alerts` → `GET /alerts?product_id=X`. Rationale: validates the full HTTP → service → DB path against the real Docker Compose stack.
- **`openapi.json` generation**: `make generate-openapi` Makefile target invokes `app.openapi()` directly and writes `backend/openapi.json`. Run manually before each PR; committed to git for contract testing. Rationale: no live server required; deterministic output from app metadata.
- **`main.py` router mount**: Explicit task to uncomment the router stub at lines 109–111 of `main.py`. Rationale: the stub exists but is inert; item 6 activates it.
- **`AlertUpdate` cleanup**: Remove `product_id` from `AlertUpdate`; it was originally inherited from `AlertBase` and would allow moving an alert between products, which is unintended. Rationale: alert ownership is immutable after creation; routes return 422 if `product_id` is supplied.
- **Default sort order**: `GET /products` ordered by `created_at DESC`; `GET /products/{id}/prices` ordered by `captured_at DESC`; `GET /alerts` ordered by `id ASC`. Rationale: most-recent-first for products and prices is the expected display order; alerts have no natural recency ordering so insertion order is used.

### Tasks

**Schema definitions**
- [x] Create `backend/app/schemas/common.py` — define generic `PaginatedResponse[T](BaseModel)` with fields `items: list[T]`, `total: int`, `limit: int`, `offset: int`; define `ScrapeJobResponse(BaseModel)` with fields `task_id: str`, `status: Literal["queued"]`, `product: ProductRead`
- [x] Update `backend/app/schemas/alert.py` — remove `product_id` field from `AlertUpdate` (product FK is read-only after creation); retain all other optional fields

**Celery stub**
- [x] Create `backend/app/tasks/scrape.py` stub — skipped: Item 5 was already complete; `scrape_product` is a real Celery task; routes call `.delay()` directly

**Route handlers**
- [x] Implement `backend/app/api/v1/products.py` — routes with OpenAPI tags/descriptions/response models:
  - `POST /products` → 201 `ProductRead`; raises 409 if URL already exists
  - `GET /products` → 200 `PaginatedResponse[ProductRead]`; optional `?is_active=true/false`; ordered `created_at DESC`; max page size 100
  - `GET /products/{id}` → 200 `ProductRead`; 404 if not found
  - `PATCH /products/{id}` → 200 `ProductRead`; 404 if not found; 409 if URL conflicts with another product
  - `DELETE /products/{id}` → 204 No Content; 404 if not found
- [x] Implement `backend/app/api/v1/prices.py` — routes with OpenAPI tags/descriptions/response models:
  - `GET /products/{id}/prices` → 200 `PaginatedResponse[PriceRecordRead]`; params: `limit`, `offset`, optional `from_dt` (ISO 8601 datetime), `to_dt` (ISO 8601 datetime); ordered `captured_at DESC`; 404 if product not found
  - `POST /products/{id}/scrape` → 202 `ScrapeJobResponse`; calls `scrape_product.delay(product_id)`; 400 if product `is_active=False`; 404 if product not found
- [x] Implement `backend/app/api/v1/alerts.py` — routes with OpenAPI tags/descriptions/response models:
  - `POST /alerts` → 201 `AlertRead`; 404 if `product_id` does not exist
  - `GET /alerts` → 200 `PaginatedResponse[AlertRead]`; optional `?product_id=X`; optional `?is_active=true/false`; ordered `id ASC`; max page size 100
  - `GET /alerts/{id}` → 200 `AlertRead`; 404 if not found
  - `PATCH /alerts/{id}` → 200 `AlertRead`; 404 if not found; 422 if `product_id` supplied in body
  - `DELETE /alerts/{id}` → 204 No Content; 404 if not found

**Router and wiring**
- [x] Create `backend/app/api/v1/router.py` — instantiate `APIRouter`; include `products_router`, `prices_router`, `alerts_router`; export `api_router`
- [x] Update `backend/app/main.py` — uncomment the router stub (lines 109–111): `from app.api.v1.router import api_router` + `app.include_router(api_router, prefix="/api/v1")`

**Test infrastructure**
- [x] Add `pg_async_client` fixture to `backend/tests/conftest.py` — mirrors `async_client` but uses `pg_engine` (Postgres testcontainer); overrides `get_db` with a Postgres-backed session factory; function-scoped

**Makefile and tooling**
- [x] Add `generate-openapi` target to `Makefile`: `cd backend && uv run python -c "import json; from app.main import app; open('openapi.json','w').write(json.dumps(app.openapi()))"`; run manually before each PR
- [x] Run `make generate-openapi` after implementation and commit `backend/openapi.json`

### Test strategy

- **Unit** (no DB — Arrange-Act-Assert):
  - `PaginatedResponse` schema: serialises `items`, `total`, `limit`, `offset` correctly; `limit > 100` rejected with `ValidationError`
  - `ScrapeJobResponse`: schema round-trip preserves `task_id`, `status`, and nested `ProductRead`
  - Pagination helper: `offset=0, limit=10` with 25 total records → `total=25`, 10 items returned
  - `AlertUpdate` guards: attempting to construct `AlertUpdate(product_id=1)` raises `ValidationError` (field removed from schema)

- **Integration** (Postgres via `pg_async_client` testcontainer — Arrange-Act-Assert):
  - `POST /products` → 201 with correct `ProductRead` body; re-fetch via `GET /products/{id}` → same data
  - `GET /products?is_active=false` → returns only inactive products
  - `GET /products` pagination: seed 15 records, `?limit=5&offset=10` → 5 items, `total=15`
  - `GET /products/{id}/prices?from_dt=...&to_dt=...` → returns only `PriceRecord` rows within the date window
  - `POST /alerts` → 201; `GET /alerts?product_id={id}` → list contains the new alert
  - `PATCH /products/{id}` updates `name`; subsequent `GET /products/{id}` reflects the change
  - `DELETE /products/{id}` → 204; subsequent `GET /products/{id}` → 404

- **Negative** (Arrange-Act-Assert):
  - `GET /products/99999` → 404
  - `POST /products` with missing `name` → 422
  - `POST /products` with duplicate URL → 409 Conflict
  - `PATCH /products/{id}` with URL of an existing product → 409 Conflict
  - `PATCH /alerts/{id}` with `product_id` in body → 422
  - `GET /products/{id}/prices?limit=200` → 422 (exceeds max page size 100)
  - `POST /products/{id}/scrape` on inactive product (`is_active=False`) → 400
  - `POST /products/{id}/scrape` on non-existent product → 404
  - `DELETE /alerts/99999` → 404

- **Live E2E** (`@pytest.mark.live_api` — requires `make dev` running):
  - Full CRUD smoke:
    - `POST /api/v1/products` → 201; assert `id` present in response body
    - `GET /api/v1/products/{id}` → 200; assert `name` matches
    - `PATCH /api/v1/products/{id}` → 200; assert updated field persisted
    - `POST /api/v1/alerts` → 201; `GET /api/v1/alerts?product_id={id}` → list contains the new alert
    - `DELETE /api/v1/products/{id}` → 204; `GET /api/v1/products/{id}` → 404
  - Skipped by default: `pytest -m "not live_api"`

### Documentation

- **`backend/app/schemas/common.py`** — create: `PaginatedResponse[T]` and `ScrapeJobResponse`
- **`backend/app/schemas/alert.py`** — update: remove `product_id` from `AlertUpdate`
- **`backend/app/tasks/scrape.py`** — create: `scrape_product` stub (item 5 replaces with Celery task)
- **`backend/app/api/v1/products.py`** — create: products router
- **`backend/app/api/v1/prices.py`** — create: prices router
- **`backend/app/api/v1/alerts.py`** — create: alerts router
- **`backend/app/api/v1/router.py`** — create: aggregated `api_router`
- **`backend/app/main.py`** — update: uncomment `api_router` mount
- **`backend/tests/conftest.py`** — update: add `pg_async_client` fixture
- **`Makefile`** — update: add `generate-openapi` target
- **`backend/openapi.json`** — create: generated snapshot (run `make generate-openapi` post-implementation)
- **`CLAUDE.md`** — update: commands table to add `make generate-openapi`; architecture API layer section to document all route modules, pagination envelope shape, async 202 scrape pattern
- **`CHANGELOG.md`** — add `### Added` entry under `## [Unreleased]` at implementation time: REST API endpoints (`/api/v1/products`, `/api/v1/alerts`, `/api/v1/prices`), typed pagination envelope, async on-demand scrape trigger

---

## 7. Frontend — React Application

Scaffold and implement the React frontend: product dashboard with infinite-scroll product list, price history charts with date-range filtering, alert management, and real-time update polling.

**Depends on**: Item 6 (REST API Endpoints) for `backend/openapi.json` used by `make generate-types`. Item 7 uses placeholder hand-written types during development; run `make generate-types` once item 6 is complete.

### Design decisions (resolved)

- **Component library**: shadcn/ui (Radix UI primitives + Tailwind CSS). Rationale: accessible unstyled primitives with Tailwind variants; standard with Vite + React stacks; no CSS-in-JS overhead.
- **TypeScript API types**: Generated from `backend/openapi.json` via `openapi-typescript` (`make generate-types`). During item 7 development, hand-write placeholder types in `src/api/types.ts`. Rationale: types stay in sync with the backend contract automatically after item 6 lands.
- **Live E2E layer**: Playwright (`@playwright/test`) smoke tests in `frontend/tests/e2e/`; navigate Dashboard → ProductDetail → AlertManager against running `make dev` stack. `make test-e2e` target added to Makefile. `npx playwright install chromium` added to `make install`. Rationale: all four test layers required; Playwright has native TypeScript support.
- **Date range filter on PriceChart**: shadcn/ui Popover + Calendar (react-day-picker `mode="range"`) for custom from/to range; `date-fns` for formatting/arithmetic. Rationale: richer UX than preset-only buttons; shadcn/ui Calendar available from installed primitives.
- **Dashboard pagination**: Infinite scroll via `useInfiniteQuery` + IntersectionObserver (`react-intersection-observer` `useInView` hook). Sentinel div at list bottom triggers `fetchNextPage()`. Page size: 20. Rationale: react-query `useInfiniteQuery` handles offset cursor natively; no scroll library required.
- **Form library**: `react-hook-form` + `zod` + `@hookform/resolvers`. Conditional fields (`webhook_url` shown only when `channel=webhook`; `whatsapp_number` only when `channel=whatsapp`) driven by `watch('channel')`. Rationale: standard with shadcn/ui Form components; Zod validates conditional required fields at schema level.
- **Shared Layout**: `src/components/Layout.tsx` — top nav with "Price Pulse" brand link and a theme toggle Button (ghost variant, Lucide Sun/Moon icon). Wraps all routes. Rationale: consistent navigation; no sidebar overhead at this scale.
- **Scrape Now UX**: ProductDetail header "Scrape Now" button calls `POST /products/{id}/scrape`. `sonner` toast confirms "Scrape job queued" on 202. Existing 60s `usePrices` `refetchInterval` surfaces the new PriceRecord. Rationale: no websocket or manual status polling needed at a 30-minute scrape cadence.
- **API client pattern**: Single axios instance in `src/api/client.ts`; `baseURL: import.meta.env.VITE_API_URL ?? ''`; error interceptor normalises all API errors to `{detail: string}`; typed resource groups: `productsApi`, `pricesApi`, `alertsApi`. Rationale: centralised transport layer; swappable without touching hooks.
- **MSW handler location**: `frontend/tests/mocks/handlers.ts` + `tests/mocks/server.ts`. Imported in `tests/setup.ts` so every vitest test gets the server automatically. Rationale: mock code co-located with tests, not app source.
- **Zustand store scope**: `selectedProductId: number | null`, `colorScheme: 'light' | 'dark' | 'system'`, `activeProductFilter: boolean | null`, `activeAlertFilter: boolean | null`. React-query owns all server state; Zustand holds UI-only state. Rationale: minimal Zustand footprint; no server cache duplication.
- **Dark mode**: Tailwind `darkMode: 'class'`. Zustand `colorScheme` drives a `useEffect` toggling `document.documentElement.classList`. System default reads `window.matchMedia('(prefers-color-scheme: dark)')` on init. Rationale: shadcn/ui dark variants work transparently with the Tailwind class strategy.
- **Toast library**: `sonner`. `<Toaster />` mounted in `App.tsx`. Rationale: shadcn/ui docs recommend sonner over the built-in Toast component; simpler API.
- **Price formatting**: `formatPrice(price: string | number, currency: string) → string` in `src/lib/formatPrice.ts` using `Intl.NumberFormat('en-GB', { style: 'currency', currency })`. Returns `'—'` for null/undefined. Rationale: ISO-correct; supports GBP/USD/EUR without a symbol lookup table.
- **Product management actions**: Kebab DropdownMenu on each Dashboard row — Edit (opens `ProductFormDialog` in edit mode), Activate/Deactivate (calls `useUpdateProduct`), Delete (opens `ConfirmDialog`). Rationale: all mutations accessible from Dashboard without leaving the list.
- **Loading states**: shadcn/ui `Skeleton` components — skeleton rows in Dashboard list, skeleton chart area in ProductDetail. Rationale: better perceived performance than a spinner; shapes match expected layout.
- **Error boundary**: Single global `<ErrorBoundary>` wrapping `<Routes>` in `App.tsx`. Renders a Card with "Something went wrong", error detail, and "Try again" Button (`setState({ hasError: false })`). Rationale: prevents full blank-screen on any render crash.
- **shadcn/ui setup files**: Explicit tasks for `src/globals.css` (CSS variable tokens + `@tailwind` directives), `src/lib/utils.ts` (`cn()` = clsx + tailwind-merge), `tsconfig.app.json` path alias (`@/*` → `./src/*`), `vite.config.ts` path alias. These are prerequisites for all shadcn/ui components. Rationale: `npx shadcn-ui@latest init` generates them but tasks ensure they are committed and documented.
- **ProductDetail layout**: Header (name, URL, source type Badge, Scrape Now button) → PriceChart → Alerts summary Card (count + "Manage alerts" → `/products/:id/alerts`). Single-column vertical flow. Rationale: no tab switching required to see the chart.
- **AlertManager routing**: `/products/:id/alerts` sub-route. Pre-filters `GET /alerts?product_id=:id`. "Back to product" breadcrumb link. Rationale: contextual — alert management is always in the context of one product.
- **Alert create/edit UI**: shadcn/ui Dialog launched from "Add alert" button or row edit button. Conditional fields rendered via `watch('channel')`. Rationale: consistent with ProductFormDialog pattern; no page navigation required for CRUD.

### Tasks

**Package and tooling setup**
- [x] Update `frontend/package.json` runtime deps: add `tailwindcss`, `postcss`, `autoprefixer`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `tailwindcss-animate`, `sonner`, `react-hook-form`, `@hookform/resolvers`, `zod`, `react-day-picker`, `date-fns`, `react-intersection-observer`
- [x] Update `frontend/package.json` devDeps: add `openapi-typescript`, `@playwright/test`; add script `"generate-types": "npx openapi-typescript ../backend/openapi.json -o src/api/types.ts"`
- [x] Run `npx shadcn-ui@latest init` — select TypeScript, CSS variables, `tailwind.config.ts`, `src/globals.css`, `@/` import alias; verify `darkMode: 'class'` in `tailwind.config.ts` and `content: ['./src/**/*.{ts,tsx}']`
- [x] Install shadcn/ui components via CLI: `npx shadcn-ui@latest add button card dialog dropdown-menu input label select skeleton table badge form popover calendar alert-dialog`
- [x] Update `tsconfig.app.json`: add `"paths": {"@/*": ["./src/*"]}` to `compilerOptions`; update `"include"` to `["src", "tests"]`
- [x] Update `vite.config.ts`: add `import path from 'path'`; add `resolve: { alias: { "@": path.resolve(__dirname, "./src") } }` to `defineConfig`
- [x] Create `frontend/playwright.config.ts`: `baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173'`; `testDir: './tests/e2e'`; `use: { headless: true }`; screenshot on failure
- [x] Update `Makefile` `install` target: add `cd frontend && npx playwright install chromium` after `cd frontend && npm install`
- [x] Add `make test-e2e` Makefile target: `cd frontend && npx playwright test`

**TypeScript types and API client**
- [x] Create `frontend/src/api/types.ts` — hand-write placeholder TypeScript interfaces: `ProductRead`, `ProductCreate`, `ProductUpdate`, `PriceRecordRead`, `AlertRead`, `AlertCreate`, `AlertUpdate`, `PaginatedResponse<T>` (items, total, limit, offset), `ScrapeJobResponse` (task_id, status, product); add comment `// Run make generate-types to replace with generated types after item 6 is complete`
- [x] Create `frontend/src/api/client.ts` — axios instance `baseURL: import.meta.env.VITE_API_URL ?? ''`; response error interceptor extracting `{detail: string}` from 4xx/5xx; `productsApi`: `list(params)`, `get(id)`, `create(data)`, `update(id, data)`, `remove(id)`, `scrape(id)`; `pricesApi`: `list(productId, params)`; `alertsApi`: `list(params)`, `get(id)`, `create(data)`, `update(id, data)`, `remove(id)` — all typed with interfaces from `src/api/types.ts`

**App shell and routing**
- [x] Rewrite `frontend/src/main.tsx` — create `QueryClient` instance; wrap `<App />` in `<QueryClientProvider client={queryClient}>` + `<BrowserRouter>`; mount `<Toaster />` from sonner as sibling of `<App />`
- [x] Create `frontend/src/App.tsx` — `<Routes>`: `path="/"` → `<Dashboard />`, `path="/products/:id"` → `<ProductDetail />`, `path="/products/:id/alerts"` → `<AlertManager />`; wrap all `<Routes>` in `<Layout>` and `<ErrorBoundary>`
- [x] Create `frontend/src/components/Layout.tsx` — top nav: "Price Pulse" brand `<Link to="/">`; right-aligned theme toggle Button (ghost variant, Lucide `<Sun>` / `<Moon>` icon toggled by `colorScheme`); calls Zustand `setColorScheme`; `useEffect` syncs `colorScheme` to `document.documentElement.classList` ('dark' added for dark, removed for light, auto-detects for system); renders `{children}` below nav
- [x] Create `frontend/src/components/ErrorBoundary.tsx` — class-based `React.Component<{children}, {hasError, error}>`; `componentDidCatch` logs error; `getDerivedStateFromError` sets `hasError: true`; renders shadcn/ui `Card` with "Something went wrong" heading, `error.message`, and "Try again" `Button` that calls `this.setState({ hasError: false })`

**Zustand store**
- [x] Create `frontend/src/store/uiStore.ts` — Zustand store: `selectedProductId: number | null` (init null), `colorScheme: 'light' | 'dark' | 'system'` (init by reading `window.matchMedia('(prefers-color-scheme: dark)')` → default 'system'), `activeProductFilter: boolean | null` (init null), `activeAlertFilter: boolean | null` (init null); actions: `setSelectedProductId`, `setColorScheme`, `setActiveProductFilter`, `setActiveAlertFilter`

**Utility functions**
- [x] Create `frontend/src/lib/formatPrice.ts` — `export function formatPrice(price: string | number | null | undefined, currency: string): string` — returns `'—'` for null/undefined; otherwise `new Intl.NumberFormat('en-GB', { style: 'currency', currency, minimumFractionDigits: 2 }).format(Number(price))`

**React-query hooks**
- [x] Create `frontend/src/hooks/useProducts.ts` — `useInfiniteProducts(filter: { isActive?: boolean })`: `useInfiniteQuery` with `queryKey: ['products', filter]`, `queryFn: ({ pageParam }) => productsApi.list({ ...filter, limit: 20, offset: pageParam })`, `initialPageParam: 0`, `getNextPageParam: (last, _, lastOffset) => last.total > lastOffset + 20 ? lastOffset + 20 : undefined`; `useProduct(id: number)`: `useQuery(['product', id], ...)`; `useCreateProduct()`, `useUpdateProduct(id)`, `useDeleteProduct()`: `useMutation` hooks each calling `queryClient.invalidateQueries({ queryKey: ['products'] })` on success
- [x] Create `frontend/src/hooks/usePrices.ts` — `usePrices(productId: number, params: { limit?: number; fromDt?: string; toDt?: string })`: `useQuery` with `queryKey: ['prices', productId, params]`, `refetchInterval: 60_000`, calls `pricesApi.list(productId, params)`
- [x] Create `frontend/src/hooks/useAlerts.ts` — `useAlerts(productId: number, filter?: { isActive?: boolean })`: `useQuery` with `queryKey: ['alerts', productId, filter]`; `useCreateAlert()`, `useUpdateAlert(id)`, `useDeleteAlert()`: `useMutation` hooks each invalidating `['alerts']` on success
- [x] Create `frontend/src/hooks/useScrape.ts` — `useScrapeProduct()`: `useMutation` calling `productsApi.scrape(productId)`, `onSuccess: () => toast('Scrape job queued — price will update shortly')`, `onError: (err) => toast.error(err.detail ?? 'Scrape failed')`; `onSettled`: `queryClient.invalidateQueries({ queryKey: ['prices', productId] })`

**Pages**
- [x] Implement `frontend/src/pages/Dashboard.tsx`:
  - `useInfiniteProducts({ isActive: activeProductFilter })` from Zustand; `useInView` sentinel div at list bottom calls `fetchNextPage()` when `inView && hasNextPage`
  - is_active filter: three shadcn/ui Button variants (All / Active / Inactive) writing Zustand `setActiveProductFilter`
  - "Add product" Button → local `dialogOpen` state → `<ProductFormDialog mode="create">`
  - Skeleton: 5 `<Skeleton className="h-16" />` rows while `isLoading`; empty-state `Card` when `pages[0].total === 0`
  - Product rows (shadcn/ui `Table` or `Card` list): name (clickable `<Link>` → `/products/:id`), source type `Badge`, latest price from most recent `PriceRecordRead` via `formatPrice`, active status `Badge`; `DropdownMenu` with Edit (`<ProductFormDialog mode="edit" product={row}>`), Activate/Deactivate (`useUpdateProduct`), Delete (`<ConfirmDialog>`)

- [x] Implement `frontend/src/pages/ProductDetail.tsx`:
  - `useParams` for `id`; `useProduct(id)` for metadata; set Zustand `selectedProductId` on mount via `useEffect`
  - Header: product `name` (h1), `url` as `<a target="_blank">`, `source_type` `Badge`, "Scrape Now" `Button` calling `useScrapeProduct` (shows Lucide `<Loader2 className="animate-spin">` and `disabled` while mutating)
  - `<PriceChart productId={id} />` below header
  - Alerts summary `Card` at bottom: `useAlerts(id)` count of `is_active=true` alerts + "Manage alerts" `Button` → `navigate('/products/:id/alerts')`
  - Skeleton layout (card skeleton + chart skeleton) while `isLoading`; 404 `Card` if product not found

- [x] Implement `frontend/src/pages/AlertManager.tsx`:
  - `useParams` for `id`; `useAlerts(id, { isActive: activeAlertFilter })` from Zustand
  - "← Back to product" `<Link to="/products/:id">` breadcrumb at top
  - is_active filter buttons (same pattern as Dashboard); `activeAlertFilter` from Zustand
  - "Add alert" `Button` → local `dialogOpen` + `<AlertFormDialog mode="create" productId={id}>`
  - `Table` rows: threshold `formatPrice`, direction `Badge` (above = green, below = red), channel `Badge`, active status `Badge`, `notified_at` formatted datetime; row Edit `Button` → `<AlertFormDialog mode="edit" alert={row}>`; Delete `Button` → `<ConfirmDialog>`
  - Empty state `Card` when no alerts
  - Skeleton rows while `isLoading`

**Components**
- [x] Create `frontend/src/components/PriceChart.tsx`:
  - Props: `productId: number`
  - Local state: `dateRange: { from: Date | undefined; to: Date | undefined }` (init undefined/undefined = load all)
  - `usePrices(productId, { fromDt: dateRange.from ? formatISO(dateRange.from) : undefined, toDt: dateRange.to ? formatISO(dateRange.to) : undefined })`
  - Date range picker: shadcn/ui `Popover` + `Calendar` with `mode="range"` updating `dateRange` state; "Clear" button resets to all-time
  - Recharts `<ResponsiveContainer width="100%" height={300}>` → `<LineChart data={filteredPoints}>` (filter out null-price points); `<XAxis dataKey="captured_at">` with `tickFormatter` using `date-fns format`; `<YAxis tickFormatter>` using `formatPrice`; `<Tooltip content={<CustomTooltip />}>` showing formatted price + currency + ISO date
  - Skeleton `<Skeleton className="h-64 w-full" />` while loading; empty-state `Card` when no data points

- [x] Create `frontend/src/components/ProductFormDialog.tsx`:
  - Props: `mode: 'create' | 'edit'`; `product?: ProductRead`; `open: boolean`; `onOpenChange: (open: boolean) => void`
  - shadcn/ui `Dialog`; `useForm` with `zodResolver`; zod schema: `name: z.string().min(1)`, `url: z.string().url()`, `source_type: z.enum(['generic','amazon','ebay','currys'])`, `css_selector: z.string().optional()`; `css_selector` `FormItem` rendered only when `watch('source_type') === 'generic'`
  - Submit calls `useCreateProduct` or `useUpdateProduct`; `onSuccess`: `toast('Product saved')`, `onOpenChange(false)`, invalidate products query
  - shadcn/ui `Form` + `FormField` + `FormItem` + `FormMessage` for per-field validation feedback

- [x] Create `frontend/src/components/AlertFormDialog.tsx`:
  - Props: `productId: number`; `mode: 'create' | 'edit'`; `alert?: AlertRead`; `open: boolean`; `onOpenChange: (open: boolean) => void`
  - shadcn/ui `Dialog`; `useForm` with `zodResolver`; zod schema: `threshold_price: z.coerce.number().positive()`, `direction: z.enum(['above','below'])`, `channel: z.enum(['email','webhook','whatsapp'])`, `webhook_url: z.string().url().optional()`, `whatsapp_number: z.string().regex(/^\+[1-9]\d{7,14}$/).optional()`; `.superRefine()` makes `webhook_url` required when `channel=webhook` and `whatsapp_number` required when `channel=whatsapp`
  - Conditional `FormItem` visibility driven by `watch('channel')`
  - Submit calls `useCreateAlert` or `useUpdateAlert`; `onSuccess`: `toast('Alert saved')`, `onOpenChange(false)`

- [x] Create `frontend/src/components/ConfirmDialog.tsx`:
  - Props: `title: string`; `description: string`; `open: boolean`; `onOpenChange: (open: boolean) => void`; `onConfirm: () => void`; `isLoading?: boolean`
  - shadcn/ui `AlertDialog` with `AlertDialogAction` styled as destructive `Button`; shows `<Loader2 className="animate-spin">` when `isLoading`

**MSW test infrastructure**
- [x] Create `frontend/tests/mocks/handlers.ts` — MSW v2 `http` handlers for all API endpoints: `GET /api/v1/products` → `PaginatedResponse<ProductRead>` (3 seeded items, total: 3); `POST /api/v1/products` → 201 `ProductRead`; `GET /api/v1/products/:id` → single `ProductRead`; `PATCH /api/v1/products/:id` → 200 `ProductRead`; `DELETE /api/v1/products/:id` → 204; `GET /api/v1/products/:id/prices` → `PaginatedResponse<PriceRecordRead>` (5 seeded records); `POST /api/v1/products/:id/scrape` → 202 `ScrapeJobResponse`; `GET /api/v1/alerts` → `PaginatedResponse<AlertRead>`; `POST /api/v1/alerts` → 201 `AlertRead`; `PATCH /api/v1/alerts/:id` → 200 `AlertRead`; `DELETE /api/v1/alerts/:id` → 204
- [x] Create `frontend/tests/mocks/server.ts` — `import { setupServer } from 'msw/node'; export const server = setupServer(...handlers)`
- [x] Update `frontend/tests/setup.ts` — add `import { server } from './mocks/server'`; add `beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))`, `afterEach(() => server.resetHandlers())`, `afterAll(() => server.close())`

**Playwright E2E**
- [x] Create `frontend/tests/e2e/smoke.spec.ts` — Playwright test: (1) `page.goto('/')` → assert heading "Price Pulse" visible; assert at least one product row rendered; (2) click first product row → assert product name `<h1>` visible; assert Recharts SVG present; assert "Manage alerts" button visible; (3) click "Manage alerts" → assert AlertManager heading visible; assert "Add alert" button visible. Requires `make dev` running (`E2E_BASE_URL=http://localhost:5173` env var)

### Test strategy

- **Unit** (isolated, no network — Arrange-Act-Assert):
  - `formatPrice`: `formatPrice(9.99, 'GBP')` → `'£9.99'`; `formatPrice(null, 'USD')` → `'—'`; `formatPrice(1234.5, 'EUR')` → `'€1,234.50'`
  - `api/client.ts`: axios instance `baseURL` equals `VITE_API_URL`; error interceptor extracts `detail` from 422 response body; 404 response → rejects with `{detail: 'Not Found'}`
  - `uiStore.ts`: `setColorScheme('dark')` updates store; `setActiveProductFilter(true)` updates store; `setSelectedProductId(42)` updates store
  - `PriceChart.tsx`: renders with 5 seeded `PriceRecordRead` fixtures → Recharts SVG present in DOM; renders empty-state `Card` when data is empty array; `CustomTooltip` formats price via `formatPrice`
  - `AlertFormDialog.tsx`: `channel=webhook`, empty `webhook_url` → form submission blocked, validation error shown; `channel=whatsapp`, invalid number format → `FormMessage` shown; `channel=email` → `webhook_url` and `whatsapp_number` fields not in DOM
  - `ProductFormDialog.tsx`: invalid `url` field → `FormMessage` shown; `source_type=amazon` → `css_selector` field not rendered
  - `ConfirmDialog.tsx`: renders `title` and `description`; `isLoading=true` → action button shows spinner and is disabled

- **Integration** (MSW mock server via `tests/mocks/server.ts` — Arrange-Act-Assert):
  - `Dashboard`: renders with MSW `GET /api/v1/products` handler; assert 3 product rows visible; assert formatted price `'£9.99'` in first row; assert Skeleton not rendered after data loads
  - `Dashboard` infinite scroll: MSW returns `total: 40`; IntersectionObserver fires → `fetchNextPage` called; assert page 2 products append to list
  - `Dashboard` empty state: MSW returns `total: 0, items: []`; assert empty-state `Card` rendered
  - `Dashboard` "Add product" modal: click "Add product" → `Dialog` opens; fill form; submit → MSW `POST /api/v1/products` returns 201 → `Dialog` closes; product list refetches
  - `Dashboard` delete: click kebab menu → Delete → `ConfirmDialog` → confirm → MSW `DELETE /api/v1/products/:id` 204 → list refetches
  - `ProductDetail`: renders product header; `<PriceChart>` receives 5 seeded price records; "Manage alerts" button navigates to `/products/:id/alerts`
  - `ProductDetail` Scrape Now: click "Scrape Now" → MSW `POST /api/v1/products/:id/scrape` 202 → sonner toast "Scrape job queued" appears
  - `AlertManager`: renders 2 seeded alerts; "Add alert" modal; submit → MSW `POST /api/v1/alerts` 201 → list refetches; delete flow matches Dashboard pattern

- **Negative** (Arrange-Act-Assert):
  - API returns 500 on `GET /api/v1/products` → `<ErrorBoundary>` "Something went wrong" Card rendered (use `server.use(http.get(..., () => HttpResponse.error()))` override)
  - `GET /api/v1/products/:id` returns 404 → `ProductDetail` 404 Card rendered, not `<ErrorBoundary>`
  - `PriceChart` with all null prices (extraction_failed records) → empty-state Card rendered, Recharts SVG absent
  - `AlertFormDialog` submitted with `channel=webhook` and blank `webhook_url` → form does not submit; `FormMessage` visible
  - `ProductFormDialog` submitted with invalid URL → form does not submit; `FormMessage` visible
  - `useScrapeProduct` on inactive product → API returns 400 → `toast.error` displayed; Scrape Now button re-enabled
  - `formatPrice` with non-numeric string → returns `'—'` without throwing

- **Live E2E** (`@playwright/test` — requires `make dev` running; `E2E_BASE_URL=http://localhost:5173`):
  - `frontend/tests/e2e/smoke.spec.ts`: navigate to `/`; assert "Price Pulse" heading visible; click first product row; assert product name `<h1>` visible; assert Recharts SVG present; click "Manage alerts"; assert AlertManager heading visible; assert "Add alert" button visible

### Documentation

- **`frontend/package.json`** — update: add all new runtime and dev deps; add `generate-types` script
- **`frontend/playwright.config.ts`** — create
- **`frontend/tailwind.config.ts`** — create (via `npx shadcn-ui@latest init`)
- **`frontend/src/globals.css`** — create: shadcn/ui CSS variable tokens + `@tailwind` directives
- **`frontend/src/lib/utils.ts`** — create: `cn()` helper (clsx + tailwind-merge) (via shadcn init)
- **`frontend/src/lib/formatPrice.ts`** — create
- **`frontend/src/api/types.ts`** — create: placeholder types (replaced by `make generate-types`)
- **`frontend/src/api/client.ts`** — create
- **`frontend/src/main.tsx`** — update: rewrite from placeholder to full entrypoint
- **`frontend/src/App.tsx`** — create
- **`frontend/src/store/uiStore.ts`** — create
- **`frontend/src/components/Layout.tsx`** — create
- **`frontend/src/components/ErrorBoundary.tsx`** — create
- **`frontend/src/components/PriceChart.tsx`** — create
- **`frontend/src/components/ProductFormDialog.tsx`** — create
- **`frontend/src/components/AlertFormDialog.tsx`** — create
- **`frontend/src/components/ConfirmDialog.tsx`** — create
- **`frontend/src/pages/Dashboard.tsx`** — create
- **`frontend/src/pages/ProductDetail.tsx`** — create
- **`frontend/src/pages/AlertManager.tsx`** — create
- **`frontend/src/hooks/useProducts.ts`** — create
- **`frontend/src/hooks/usePrices.ts`** — create
- **`frontend/src/hooks/useAlerts.ts`** — create
- **`frontend/src/hooks/useScrape.ts`** — create
- **`frontend/tests/mocks/handlers.ts`** — create
- **`frontend/tests/mocks/server.ts`** — create
- **`frontend/tests/setup.ts`** — update: add MSW server lifecycle
- **`frontend/tests/e2e/smoke.spec.ts`** — create
- **`Makefile`** — update: add `test-e2e` target; update `install` to include `npx playwright install chromium`
- **`CLAUDE.md`** — update: commands table to add `make test-e2e` and `make generate-types`; frontend architecture section to document shadcn/ui, Zustand store shape, routing structure, MSW handler location
- **`CHANGELOG.md`** — add `### Added` entry under `## [Unreleased]` at implementation time: React SPA (shadcn/ui, react-query infinite scroll, PriceChart with date range, AlertManager with conditional notification fields, Playwright E2E)

---

## 8. Docker Containerisation

Write production-grade multi-stage Dockerfiles and finalise compose configuration.

**Depends on**: Items 4–7 (all application code must be complete before the Docker layer is finalised). Item 8 does not add application code — it corrects scaffold stubs produced in earlier items and wires the full production compose.

### Design decisions (resolved)

- **TLS strategy**: Upstream-only. Nginx serves plain HTTP internally on port 80; TLS is terminated at an upstream load balancer or CDN (AWS ALB, Cloudflare, etc.). `nginx.conf` has no `ssl_certificate` blocks. Rationale: TLS termination at the app layer requires cert lifecycle management that belongs in the deployment layer, not the container image.
- **Resource limits**: Concrete `deploy.resources.limits` blocks in `docker-compose.yml` for all services — `backend`: `memory: 512m, cpus: "0.50"`; `celery-worker`: `memory: 512m, cpus: "1.00"`; `celery-beat`: `memory: 256m, cpus: "0.25"`; `celery-playwright`: `memory: 1g, cpus: "1.00"` (Chromium requires 800–900 MB); `postgres`: `memory: 512m, cpus: "0.50"`; `redis`: `memory: 128m, cpus: "0.25"`; `frontend` (Nginx): `memory: 128m, cpus: "0.25"`. Rationale: values derived from expected workloads at a 30-minute scraping cadence; tune after load testing.
- **Healthcheck tool**: `curl` installed in the `production` stage of `backend.Dockerfile` via `apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*`. Rationale: `python:3.12-slim` does not include `curl`; the existing `HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1` would silently fail without it.
- **uv lockfile in builder**: `backend.Dockerfile` builder stage must `COPY pyproject.toml uv.lock* ./` (root workspace files) before `COPY backend/pyproject.toml backend/` so that `uv sync --frozen --no-dev` can resolve the locked dependency tree. The original scaffold only copies `backend/pyproject.toml`, which causes uv to install unpinned latest versions. Rationale: reproducible builds require the lockfile; `--frozen` flags a stale lockfile at build time rather than silently degrading.
- **Celery pool fix**: Item 5 decided `asyncio` pool for all Celery workers. The scaffold stubs use `--concurrency=4` (pre-fork) for `celery-worker` and `--pool=gevent` for `celery-playwright`. Both must be corrected to `--pool=asyncio` in `docker-compose.yml` and `docker/celery-playwright.Dockerfile`. Rationale: pre-fork pool with async tasks causes deadlocks; gevent is incompatible with the `celery.concurrency.aio:TaskPool` decision from item 5.
- **Worker image strategy**: One backend image; `celery-worker` and `celery-beat` services override the CMD in `docker-compose.yml` rather than adding new Dockerfile stages. Rationale: minimises image count; the override pattern is already used in `docker-compose.dev.yml`.
- **CORS_ORIGINS in production**: Add `CORS_ORIGINS=http://localhost` to `.env.example` with a comment that it must be set to the real frontend origin in production. `Settings` raises `ValueError` when `DEBUG=false` and `CORS_ORIGINS` is empty, making a fresh stack unbootable without this var. Rationale: the existing `.env.example` has no `CORS_ORIGINS` entry; `make up` on a fresh checkout would fail at FastAPI startup.
- **Postgres version**: Upgrade `docker-compose.yml` postgres image from `postgres:15-alpine` to `postgres:16-alpine` to match the `testcontainers[postgres]` version used in integration tests. Rationale: dialect consistency between test and production prevents subtle query-plan divergences.
- **Nginx security headers**: Add `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and `X-XSS-Protection: 0` to `docker/nginx.conf`. These do not require HTTPS. Rationale: baseline browser security posture at zero deployment cost.
- **Unit test layer**: Two separate `make` targets — `make lint-docker` (hadolint on all four Dockerfiles; fail on ERROR or WARN level findings) and `make validate-nginx` (`docker run --rm -v $(pwd)/docker/nginx.conf:/etc/nginx/conf.d/default.conf:ro nginx:1.27-alpine nginx -t`; fails if config is invalid). Rationale: these catch structural Dockerfile anti-patterns and config syntax errors without requiring a running stack.
- **Stack smoke test**: `make smoke` target replaces the vague "verify within 60 seconds" task. Script: `docker compose up -d`, poll `GET http://localhost:8000/health` every 5 s (max 12 attempts = 60 s), assert 200; `curl -sf http://localhost/nginx-health`; `docker compose down`. Rationale: scriptable and CI-reproducible.
- **CI smoke job**: New `smoke` job in `.github/workflows/ci.yml` that runs after `build`: `docker compose up -d`, wait for health via polling script, assert, `docker compose down`. Rationale: catches compose wiring regressions that `docker build` alone cannot detect.
- **Image scanning**: New `make scan` target using `aquasec/trivy` Docker image — `docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --exit-code 1 --severity CRITICAL price-pulse-backend:latest price-pulse-frontend:latest`. Run in CI after the `build` job (separate step or job). Fails the build on any CRITICAL CVE. Rationale: trivy requires no host install, runs via Docker; scanning at build time catches known CVEs before images reach any registry.
- **celery-playwright CMD path verification**: Add an explicit task to verify the `celery-playwright` container starts correctly (`docker compose run --rm celery-playwright celery -A app.workers.celery_app inspect ping`) after the pool and WORKDIR fixes are applied. Rationale: the WORKDIR, Python path, and CMD interact in non-obvious ways between the Microsoft Playwright base image and the uv workspace layout.

### Tasks

**Dockerfile fixes (correctness — scaffold stubs)**
- [x] Fix `docker/backend.Dockerfile` builder stage: add `COPY pyproject.toml uv.lock* ./` before `COPY backend/pyproject.toml backend/`; change `RUN uv sync --no-dev` to `RUN uv sync --frozen --no-dev`
- [x] Fix `docker/backend.Dockerfile` production stage: add `RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*` after the non-root user creation so the `HEALTHCHECK CMD curl -f http://localhost:8000/health` does not silently fail
- [x] Fix `docker/celery-playwright.Dockerfile` CMD: change `--pool=gevent` to `--pool=asyncio`; verify WORKDIR and Python path are consistent with the backend image entry-point

**docker-compose.yml finalisation**
- [x] Correct `celery-worker` service command: change `--concurrency=4` to `--pool=asyncio` (e.g. `celery -A app.workers.celery_app worker --pool=asyncio --loglevel=info`)
- [x] Correct `celery-playwright` service command: add `--pool=asyncio` (remove any `--concurrency` or `--pool=gevent` reference)
- [x] Upgrade postgres image: change `postgres:15-alpine` to `postgres:16-alpine`
- [x] Add `deploy.resources.limits` blocks to all seven services: `backend` (512m / 0.50 CPU), `celery-worker` (512m / 1.00), `celery-beat` (256m / 0.25), `celery-playwright` (1g / 1.00), `postgres` (512m / 0.50), `redis` (128m / 0.25), `frontend` (128m / 0.25)

**Nginx security hardening**
- [x] Add security headers to `docker/nginx.conf` `server {}` block: `add_header X-Frame-Options "SAMEORIGIN" always;`, `add_header X-Content-Type-Options "nosniff" always;`, `add_header Referrer-Policy "strict-origin-when-cross-origin" always;`, `add_header X-XSS-Protection "0" always;`

**Environment and configuration**
- [x] Add `CORS_ORIGINS=http://localhost` to `.env.example` under the `# Backend — Application` section with comment: `# Required in production (DEBUG=false); comma-separated list of allowed origins`

**Make targets (new)**
- [x] Add `make lint-docker` target: hadolint on all three Dockerfiles via Docker; `--failure-threshold warning` so INFO findings display but don't fail; fails on any ERROR or WARN finding
- [x] Add `make validate-nginx` target: `nginx -t` via Docker with `--add-host=backend:127.0.0.1` to resolve the upstream name during standalone config parse; asserts exit 0
- [x] Add `make scan` target: `docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --exit-code 1 --severity CRITICAL price-pulse-backend:latest price-pulse-frontend:latest`; fails on any CRITICAL CVE
- [x] Add `make smoke` target: `docker compose up -d`; poll `GET http://localhost:8000/health` every 5 s (12 attempts max); assert 200; `curl -sf http://localhost/nginx-health`; `docker compose down`; exits 1 on timeout or bad status
- [x] Verify `make lint-docker` passes against all four Dockerfiles after fixes; verify `make validate-nginx` passes against updated `nginx.conf`

**Make targets (already exist — verify and document)**
- [x] Verify `make build` (builds all images), `make up` (compose up -d), `make down`, `make logs SERVICE=...` behave correctly with the corrected compose; update `CLAUDE.md` commands table if descriptions differ

**CI update**
- [x] Add `smoke` job to `.github/workflows/ci.yml`: runs after `build` job; steps: `docker compose up -d` → polling health-check script (curl loop, max 60 s) → `curl -sf http://localhost/nginx-health` → assert frontend → `docker compose down`; fails PR if stack does not reach healthy state within the timeout

**Playwright service verification**
- [x] After pool and path fixes, verify `celery-playwright` starts correctly: `docker compose run --rm celery-playwright celery -A app.workers.celery_app inspect ping` → "1 node online / pong"; Chromium 148.0.7778.0 launched and closed cleanly

### Test strategy

- **Unit** (no running containers):
  - `make lint-docker` — run hadolint against `backend.Dockerfile`, `frontend.Dockerfile`, `celery-playwright.Dockerfile`; assert zero ERROR/WARN findings; lint failure blocks CI `smoke` job
  - `make validate-nginx` — run `nginx -t` via Docker against `docker/nginx.conf`; assert exit 0; catches syntax errors before deployment

- **Integration** (requires `docker compose build` first — Arrange-Act-Assert):
  - `make smoke` — `docker compose up -d` → poll `GET http://localhost:8000/health` until 200 (5 s intervals, 12 attempts) → `curl -sf http://localhost/nginx-health` → assert 200 → `docker compose down`
  - Frontend index: `curl -sf http://localhost/` → assert `<div id="root">` present (SPA shell served correctly)
  - API proxy: `curl -sf http://localhost/api/v1/` → assert not 502 (Nginx correctly forwarding to backend)

- **Negative** (Arrange-Act-Assert):
  - Backend with invalid `DATABASE_URL` (e.g. `postgresql+asyncpg://bad@nonexistent/nodb`): start container with override → assert container exits non-zero within 30 s (lifespan startup raises)
  - `celery-worker` with unreachable Redis (`CELERY_BROKER_URL=redis://nonexistent:6379/0`): start isolated container → assert structlog CRITICAL/ERROR emitted and process exits non-zero (no silent hang)
  - `docker compose up` with missing `.env`: compose should emit a clear error about required variables (`SECRET_KEY`, `CORS_ORIGINS`) rather than silently starting with wrong values; assert exit 1 from compose
  - `make validate-nginx` with a deliberately broken nginx.conf (e.g. missing semicolon): assert exit non-zero

- **Live E2E**: Not required. The `make smoke` integration test covers full-stack healthy-state verification against the real Docker Compose stack. The CI `smoke` job promotes this to a gated PR check.

### Documentation

- **`docker/backend.Dockerfile`** — update: fix builder COPY sequence + `uv sync --frozen --no-dev`; add `curl` install in production stage
- **`docker/celery-playwright.Dockerfile`** — update: change `--pool=gevent` to `--pool=asyncio`
- **`docker/nginx.conf`** — update: add four security headers (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `X-XSS-Protection`)
- **`docker-compose.yml`** — update: `celery-worker` command `--pool=asyncio`; `celery-playwright` command `--pool=asyncio`; postgres `16-alpine`; `deploy.resources.limits` for all seven services
- **`.env.example`** — update: add `CORS_ORIGINS=http://localhost` with inline comment
- **`Makefile`** — update: add `lint-docker`, `validate-nginx`, `scan`, and `smoke` targets with help descriptions
- **`.github/workflows/ci.yml`** — update: add `smoke` job that depends on `build`
- **`CLAUDE.md`** — update: commands table (add `make lint-docker`, `make validate-nginx`, `make scan`, `make smoke`); environment variables table (add `CORS_ORIGINS` row); architecture section note on resource limits
- **`CHANGELOG.md`** — add `### Added` entry under `## [Unreleased]` at implementation time: production Docker images (multi-stage backend + frontend), Nginx security headers, compose resource limits, hadolint + trivy quality gates, CI smoke job

---

## 9. Claude Code Agents

Adapt and install agents from `presentation_helper` for price_pulse SDLC workflows.

**Note**: All eight agent files were created by prior sessions. Item 9 scope is: verify content against the spec, fix any divergences, and complete the new artifacts (architecture doc, profiling skills stub, log dir scaffolding, agent lint target) that were not pre-created.

### Design decisions (resolved)

- **Agent content source**: All eight agent files already exist on disk from prior sessions. Tasks are reframed from "copy and adapt" to "verify content and fix divergences". Rationale: files were created during earlier SDLC sessions; item 9 gates them formally with a lint check.
- **Architecture doc scope**: `docs/architecture/repository-architecture.md` is expanded from a stub (C1+C2 only) to a full three-level C4 doc: C1 (system context), C2 (container — corrected to Postgres 16), C3 (backend components — API layer, service layer, scraping layer, models, schemas, core). Frontend stays at container level (C2). A `## Module domain-grouping convention` section is required because `module-grouping-reviewer.agent.md` references it by name. Rationale: the module-grouping agent will silently fail to find its reference anchor without this section.
- **Data model section**: ASCII ER diagram of the four ORM tables (Product, PriceRecord, PriceAlert, NotificationLog) with FK arrows and key field names added to `repository-architecture.md`. Rationale: the data model is the most important orientation aid for new contributors; no external tooling required.
- **ADR index**: `## Architecture Decision Records` table appended at the bottom of `repository-architecture.md` — columns: ADR, Date, Status, Summary; one row per file in `docs/decisions/`. Rationale: centralises ADR discoverability in the canonical architecture doc without duplicating content.
- **Postgres version in arch doc**: C2 table corrects `Postgres 15` → `Postgres 16-alpine` (aligned with Item 8 upgrade decision). Rationale: item 9 owns the doc; stale version references cause confusion during capacity planning.
- **Profiling skills stub**: `.github/skills/profiling/findings.md` created as an empty stub (same header pattern as `plan-review/findings.md`). Both `profiling-reviewer` agents reference this file as their append target. Rationale: pre-creating the file prevents the first profiling run from needing to handle file-creation logic in its output.
- **Log directory scaffolding**: `make init-logs` target creates the full log tree with `.gitkeep` stubs: `logs/quality/`, `logs/profiling/backend/`, `logs/profiling/tasks/`, `logs/profiling/frontend/`, `logs/profiling/test-timing/`. `make install` calls `make init-logs`. `.gitignore` excludes log data but tracks `.gitkeep` files. Rationale: `make lint-agents` checks ALL referenced paths (including runtime log dirs) — those dirs must exist before the check can pass.
- **Agent frontmatter validation (`make lint-agents`)**: Validates two things — (1) frontmatter completeness: every `.claude/agents/*.md` has `name`, `description`, and `tools` fields; every `.github/agents/*.agent.md` has a `description` field; (2) referenced paths: all static config/doc paths and runtime log directories referenced in Quick Commands blocks exist on disk. Implemented as a shell script in the Makefile; no external linter dependency. Rationale: frontmatter completeness is required for Claude Code agent discovery; broken path references silently fail the first time an agent is run.
- **CI integration**: `make lint-agents` runs in a new dedicated `agent-quality` job in `.github/workflows/ci.yml` (separate from the existing `lint` job which covers ruff and eslint). Rationale: a distinct job label makes it clear in CI reports what failed and why; agent validation is not code lint.
- **Agent pair sync**: For each `.claude/agents/X.md` / `.github/agents/X.agent.md` pair, a manual diff identifies divergences. Acceptable divergences: `.claude` agents have `name:` and `tools:` frontmatter fields that `.github` agents do not (different runner requirements). All other paths, rules, and Quick Commands must match. Intentional divergences documented with an inline comment. Rationale: unintended drift creates inconsistent SDLC behaviour between local Claude Code and GitHub Copilot execution contexts.
- **Definition of done**: All existing agent files verified against spec; all new tasks completed; `make lint-agents` exits 0 after `make init-logs`. Rationale: a passing lint gate is the only objective, automatable acceptance criterion for a docs-only item.
- **CHANGELOG entry**: Add `### Added` entry under `## [Unreleased]` at implementation time — SDLC agent suite, C4 architecture doc, agent frontmatter validation. Rationale: agents establish SDLC infrastructure; recording them in CHANGELOG makes the tooling history visible.

### Tasks

**Verification of existing agent files**
- [x] Verify `.claude/agents/quality.md` — confirm commands reference `backend/`, `frontend/`, `uv run pytest`, `npm run test:coverage`, `config/quality-thresholds.toml`; confirm four gate thresholds (coverage ≥90% backend, ≥80% frontend, CC P95 < 7, MI P5 > 10, Halstead P95 < 500)
- [x] Verify `.claude/agents/architecture-maintainer.md` — fix `tests/` → `backend/tests/` and `frontend/tests/` to align with `.github` version; confirm C4 scope matches three levels defined in this item
- [x] Verify `.claude/agents/profiling-reviewer.md` — confirm backend log paths (`logs/profiling/backend/`), Celery task hotspot patterns (`scrape_product`), Lighthouse path (`logs/profiling/frontend/`), and findings file path (`.github/skills/profiling/findings.md`) are correct for this stack
- [x] Verify `.github/agents/plan-review.agent.md` — confirm frontend test layers (vitest unit, MSW integration) appear in both the Phase 3 rewrite rules and the ambiguity taxonomy; confirm findings log path (`.github/skills/plan-review/findings.md`)
- [x] Verify `.github/agents/module-grouping-reviewer.agent.md` — confirm scope is `backend/app/`; confirm the architecture doc reference reads `docs/architecture/repository-architecture.md → ## Module domain-grouping convention` (this section is created in this item)
- [x] Verify `.github/agents/quality.agent.md` — confirm all commands match this stack: `uv run pytest -m "not live_api" --cov=app`, `uv run mypy app/ --ignore-missing-imports`, `uv run radon`, `cd frontend && npm run test:coverage`
- [x] Verify `.github/agents/profiling-reviewer.agent.md` — confirm all profile log paths, Celery task names, and findings file path (`.github/skills/profiling/findings.md`) are correct; confirm delegation section matches this repo's agent model
- [x] Verify `.github/agents/architecture-maintainer.agent.md` — confirm C4 scope matches three levels; confirm directory scope lists `backend/tests/` and `frontend/tests/` explicitly
- [x] Sync agent pairs — for each pair (quality, architecture-maintainer, profiling-reviewer): diff `.claude/agents/X.md` against `.github/agents/X.agent.md`; align all paths and rules where no intentional divergence exists; add inline comment for each intentional divergence (acceptable: `name:` + `tools:` frontmatter in `.claude` version; `$ARGUMENTS` + User Input block in `.github` version); confirm no unintended divergence remains

**New artifacts**
- [x] Complete `docs/architecture/repository-architecture.md` — rewrite stub into full C4 doc with these sections in order:
  - `## C1 — System Context`: ASCII diagram showing User → React SPA → FastAPI backend → Postgres + Redis + external retail sites
  - `## C2 — Container Diagram`: table updated to Postgres `16-alpine`; add `celery-playwright` container (Microsoft Playwright image, `playwright` queue)
  - `## C3 — Backend Component Diagram`: one paragraph per layer — API layer (`api/v1/`: thin route handlers, no business logic), service layer (`services/`: sole writer to DB — `price_service`, `alert_service`, `notifications`), scraping layer (`scrapers/`: `BaseScraper`, `GenericScraper`, `AmazonScraper`, `registry`, `http_client`, `exceptions`), ORM models (`models/`: `Product`, `PriceRecord`, `PriceAlert`, `NotificationLog`, `enums`), Pydantic schemas (`schemas/`: `Base/Create/Read/Update` per domain + `scraper.py` + `common.py`), core (`core/`: `config`, `database`, `logging`, `exceptions`)
  - `## Module domain-grouping convention`: naming rules — modules sharing a domain noun and importing each other's types are candidates for subpackage promotion; standalone utilities with high fan-in (> 3 unrelated callers) stay flat; convention enforced by `module-grouping-reviewer.agent.md`
  - `## Data Model`: ASCII ER diagram showing four tables with FK relationships and key field names (Product → PriceRecord via `product_id`; Product → PriceAlert via `product_id`; PriceAlert → NotificationLog via `alert_id`)
  - `## Architecture Decision Records`: markdown table with columns ADR | Date | Status | Summary; one row for `docs/decisions/whatsapp-provider.md` (2026-05-26, Accepted)
- [x] Create `.github/skills/profiling/findings.md` — stub with header
- [x] Add `make init-logs` Makefile target — `mkdir -p logs/quality logs/profiling/backend logs/profiling/tasks logs/profiling/frontend logs/profiling/test-timing && touch logs/quality/.gitkeep logs/profiling/backend/.gitkeep logs/profiling/tasks/.gitkeep logs/profiling/frontend/.gitkeep logs/profiling/test-timing/.gitkeep`; idempotent
- [x] Update `make install` to call `make init-logs` as a final step (after `uv sync`, `npm install`, `playwright install chromium`, `pre-commit install`)
- [x] Update `.gitignore` — add `logs/**` with `!logs/**/.gitkeep` exception so log data is excluded but `.gitkeep` stubs are tracked
- [x] Add `make lint-agents` Makefile target — shell script that: (1) for each `.claude/agents/*.md`, greps YAML frontmatter block (`---` delimiters) for `name:`, `description:`, `tools:` fields; exits 1 with file name and missing field if any are absent; (2) for each `.github/agents/*.agent.md`, greps frontmatter for `description:` field; exits 1 if absent; (3) extracts path tokens from all Quick Commands code blocks in all agent files (lines matching `^[a-z]|cd |logs/|config/|docs/|backend/|frontend/|.github/`); for each extracted path, checks `[ -e "$path" ]` and exits 1 with the missing path and agent file name if absent; exits 0 if all checks pass
- [x] Add `agent-quality` job to `.github/workflows/ci.yml` — steps: checkout, `make install`, `make lint-agents`; triggers on pull_request and push to `main`; job does not depend on other jobs (runs in parallel with `lint`, `test-backend`, `test-frontend`)

**CHANGELOG**
- [x] Add `### Added` entry to `CHANGELOG.md` under `## [Unreleased]`: SDLC agent suite (`.claude/agents/` × 3: quality, architecture-maintainer, profiling-reviewer; `.github/agents/` × 5: plan-review, module-grouping-reviewer, quality, profiling-reviewer, architecture-maintainer), C4 repository architecture doc (`docs/architecture/repository-architecture.md`) with data model ER diagram and ADR index, agent frontmatter validation (`make lint-agents`) in new CI `agent-quality` job, log directory scaffolding (`make init-logs`)

### Test strategy

- **Unit**: N/A — agent files are markdown; no unit-testable logic.
- **Integration** (Arrange-Act-Assert):
  - `make init-logs` → verify all five `.gitkeep` files exist at expected paths; assert idempotent (run twice, exits 0 both times)
  - `make lint-agents` (after `make init-logs`) → exits 0; all eight agent frontmatter blocks valid; all referenced paths exist
- **Negative** (Arrange-Act-Assert):
  - Remove `name:` from `.claude/agents/quality.md` → `make lint-agents` exits 1; error message names the file and missing field; restore afterwards
  - Remove `description:` from `.github/agents/quality.agent.md` → `make lint-agents` exits 1; restore afterwards
  - Add a Quick Commands path reference to a non-existent directory in any agent file → `make lint-agents` exits 1 with the missing path; restore afterwards
  - Run `make lint-agents` on a fresh checkout before `make install` (no `init-logs` run) → exits 1 on missing `logs/profiling/backend/`; confirms install order requirement
- **Live E2E**: Manually invoke each agent once with a minimal prompt; verify output matches the `## Expected Output Shape` section in each respective agent file. No automated assertion — human review. Not run in CI.

### Documentation

- `docs/architecture/repository-architecture.md` — rewrite: full C4 doc (C1+C2+C3+module convention+ER+ADR index), Postgres 16, celery-playwright container
- `.github/skills/profiling/findings.md` — create: empty stub with header
- `Makefile` — update: add `lint-agents` and `init-logs` targets; add `init-logs` call in `install`
- `.github/workflows/ci.yml` — update: add `agent-quality` job
- `.gitignore` — update: add `logs/**` + `!logs/**/.gitkeep` exception
- `CLAUDE.md` — update: commands table to add `make lint-agents` and `make init-logs`
- `CHANGELOG.md` — add `### Added` entry at implementation time

---

## 10. CI/CD & Quality Gates

Wire the complete GitHub Actions pipeline, enforce quality thresholds locally and in CI, add security scanning, and document branch protection.

**Note on cross-item scope**: `lint`, `test-backend`, `test-frontend`, and `build` CI jobs were created in item 1. The `smoke` and `scan` jobs are added in item 8; the `agent-quality` job is added in item 9. Item 10 adds only what those items did not cover: the `security` job, coverage threshold enforcement, quality gate scripting, and the `GITHUB_STEP_SUMMARY` coverage table.

### Design decisions (resolved)

- **Pre-existing CI jobs**: `lint`, `test-backend`, `test-frontend`, and `build` jobs already exist from item 1. `.pre-commit-config.yaml`, `config/quality-thresholds.toml`, `make lint`, `make format`, and the frontend vitest 80% coverage threshold are all complete. Item 10 does not re-implement them; it builds on them.
- **Quality threshold enforcement script**: `backend/scripts/check_quality.py` — a standalone Python script (not a package; no `__init__.py`) invoked by `make quality` as `cd backend && uv run python scripts/check_quality.py`. Reads `config/quality-thresholds.toml` from the repo root, parses radon CC/MI/Halstead JSON outputs from the most recent `logs/quality/<timestamp>/` directory, reads `backend/coverage.xml` (Cobertura), and exits 1 if any threshold is breached. Emits a human-readable violation table on failure. Rationale: centralises all threshold logic in one testable place; avoids brittle shell arithmetic.
- **`make quality` updated to enforce**: The existing `make quality` target is updated to: (1) run pytest with `--cov-report=xml:coverage.xml` to generate the coverage file, (2) run radon CC/MI/Halstead, (3) run `npm run test:coverage` (vitest — already enforces 80% threshold internally), (4) run `check_quality.py`. The `|| true` guards removed. Exit code propagates from `check_quality.py`. Rationale: single command for both local and CI quality gates.
- **`--cov-fail-under=90` belt-and-suspenders**: Added to `addopts` in `backend/pyproject.toml` so that running `uv run pytest` directly (without `make quality`) also fails if backend coverage drops below 90%. Rationale: catches regressions in ad-hoc test runs before the developer reaches `make quality`.
- **`check_quality.py` GitHub Step Summary**: When `GITHUB_ACTIONS=true`, the script appends a markdown table to `$GITHUB_STEP_SUMMARY` showing backend coverage % vs the ≥90% threshold and the three radon metric P95/P5 values vs their thresholds, each with a ✅ or ❌ indicator. Rationale: visible in the PR Actions tab without needing Codecov or a separate service.
- **Security CI job**: New `security` job runs in parallel with `lint`, `test-backend`, `test-frontend`, and `build`. Steps: (1) `uv run pip-audit --fail-on CRITICAL` — Python dependency CVE scan; (2) `npm audit --audit-level=critical` — all frontend dependencies (dev + prod). Fails the build only on CRITICAL severity. Rationale: CRITICAL-only threshold avoids false-positive failures from transitive dev-dep CVEs while catching exploitable vulnerabilities.
- **`pip-audit` as a dev dependency**: Added to `[dependency-groups] dev` in `backend/pyproject.toml`. Installed automatically via `uv sync --group dev` in both local checkout and CI. Rationale: consistent with how all other dev tools are managed; no inline `pip install` in CI.
- **Postgres version in CI**: `test-backend` job updated from `postgres:15-alpine` to `postgres:16-alpine` to match `docker-compose.yml` (item 8 decision) and the `testcontainers[postgres]` version used in integration tests. Rationale: item 10 owns `ci.yml` holistically; leaving a dialect mismatch between CI and compose creates subtle query-plan divergences.
- **Branch protection**: GitHub repository Settings → Branches → Branch protection rule for `main`. Required status checks: `lint`, `test-backend`, `test-frontend`, `build`, `security` (and `smoke`, `agent-quality` once items 8/9 are complete). Not automatable via CI — documented as a manual prerequisite. Rationale: GitHub branch protection rules can only be set via the UI or GitHub API; documenting them here ensures the setting is applied before any team members begin contributing.
- **`npm audit` scope**: All deps (dev + prod), `--audit-level=critical`. Dev tools such as Playwright and vitest are included; CRITICAL threshold filters genuine noise. Rationale: dev deps are installed on CI runners; a compromised dev tool can compromise build artefacts.

### Tasks

**Pre-existing — verify complete**
- [x] `.pre-commit-config.yaml` — ruff (Python), eslint + prettier (JS/TS), trailing-whitespace, end-of-file-fixer, check-yaml, check-toml, detect-private-key (created in item 1)
- [x] `config/quality-thresholds.toml` — CC P95 < 7, MI P5 > 10, Halstead P95 < 500, backend coverage ≥ 90%, frontend coverage ≥ 80% (already complete)
- [x] `make lint` — ruff check (backend) + eslint (frontend) (already complete)
- [x] `make format` — ruff format (backend) + prettier (frontend) (already complete)
- [x] Frontend vitest coverage thresholds — 80% branches/functions/lines/statements enforced via `vite.config.ts` `coverage.thresholds.global` (already complete)

**Quality gate script**
- [ ] Create `backend/scripts/` directory (non-package — no `__init__.py`)
- [ ] Create `backend/scripts/check_quality.py` — reads `config/quality-thresholds.toml` (via `tomllib`; path resolved as `Path(__file__).resolve().parents[2] / "config/quality-thresholds.toml"`); loads radon CC JSON from the most recent `logs/quality/<timestamp>/cc.json` and computes P95 of all function scores; loads MI JSON and computes P5 of all module scores; loads Halstead JSON and computes P95 of all function effort scores; loads `backend/coverage.xml` (path `Path(__file__).resolve().parent.parent / "coverage.xml"`) via `xml.etree.ElementTree` and extracts `line-rate` attribute; exits 0 if all thresholds pass; exits 1 and prints a table listing each failing metric (actual value, threshold, delta); when `os.environ.get("GITHUB_ACTIONS") == "true"`, appends a markdown `| Check | Value | Threshold | Status |` table to `$GITHUB_STEP_SUMMARY` covering all four checks

**Backend pytest enforcement**
- [ ] Add `--cov-fail-under=90` to `addopts` in `[tool.pytest.ini_options]` in `backend/pyproject.toml` so that any `uv run pytest --cov=app` run fails when backend line coverage drops below 90%

**`make quality` update**
- [ ] Update `make quality` Makefile target: (1) run `cd backend && uv run pytest --cov=app --cov-report=xml:coverage.xml --cov-report=term-missing -m "not live_api" -q` to generate coverage data; (2) run radon CC/MI/Halstead JSON reports into `logs/quality/$$TIMESTAMP/` as before; (3) run `cd frontend && npm run test:coverage`; (4) run `cd backend && uv run python scripts/check_quality.py`; remove all `|| true` guards; exit code from final step propagates; update `## help` description in Makefile to read "Run full quality gate: pytest + radon + vitest; exits 1 on threshold violation"

**Security scanning**
- [ ] Add `pip-audit>=2.7` to `[dependency-groups] dev` in `backend/pyproject.toml`
- [ ] Add `security` job to `.github/workflows/ci.yml` — runs in parallel with existing jobs (no `needs:` dependency); steps: (1) `actions/checkout@v4`, (2) `astral-sh/setup-uv@v3`, (3) `uv sync --group dev` in `backend/`, (4) `uv run pip-audit --fail-on CRITICAL` — exits 1 on any CRITICAL Python CVE; (5) `actions/setup-node@v4` (Node 20), (6) `npm ci` in `frontend/`, (7) `npm audit --audit-level=critical` — exits 1 on any CRITICAL JS CVE

**CI corrections**
- [ ] Update `test-backend` job in `.github/workflows/ci.yml`: change postgres service image from `postgres:15-alpine` to `postgres:16-alpine` to match `docker-compose.yml` and testcontainers version

**Branch protection (manual prerequisite)**
- [ ] Document in `CONTRIBUTING.md` under a new `## Repository Settings` section: enable branch protection for `main` in GitHub → Settings → Branches → Add rule; required status checks: `Lint`, `Test — Backend`, `Test — Frontend`, `Build — Docker images`, `Security`; enable "Require branches to be up to date before merging"; enable "Require status checks to pass before merging"; add `smoke`, `agent-quality` to required checks once items 8 and 9 are complete

### Test strategy

- **Unit** (isolated, no external processes — Arrange-Act-Assert pattern):
  - `check_quality.py`: `tomllib.loads(valid_toml)` → `Settings` dataclass populated correctly; `P95([1,2,3,4,5,6,7,8,9,10])` → 9.55 (computed correctly); P5 MI computation on synthetic scores; coverage threshold: `line_rate=0.89`, `threshold=0.90` → exit 1 with message containing "backend coverage 89.0% < 90.0%"; coverage threshold: `line_rate=0.92`, `threshold=0.90` → exit 0; all thresholds pass → exit 0; any threshold fails → exit 1 with violation table; `GITHUB_ACTIONS=true` and threshold pass → `$GITHUB_STEP_SUMMARY` receives markdown table with all ✅
  - `check_quality.py` GITHUB_STEP_SUMMARY: `GITHUB_ACTIONS=true`, one failing metric → Step Summary table contains ❌ row for that metric

- **Integration** (runs real subprocesses — Arrange-Act-Assert pattern):
  - `make quality` exits 0 against the clean codebase (end-to-end run; requires `uv sync` and `npm ci` first)
  - `--cov-fail-under=90` enforcement: run `cd backend && uv run pytest --cov=app tests/unit/test_config.py` against a minimal test subset that produces < 90% coverage → assert exit code is non-zero

- **Negative** (Arrange-Act-Assert pattern):
  - Missing `config/quality-thresholds.toml` → `check_quality.py` exits 1 with message "quality-thresholds.toml not found at <path>"; not a silent pass or `FileNotFoundError` traceback
  - Malformed TOML in `config/quality-thresholds.toml` → `check_quality.py` exits 1 with message identifying the bad file and parse error; no unhandled exception
  - Missing `logs/quality/` directory → `check_quality.py` exits 1 with message "No quality report found; run make quality first"
  - Missing `backend/coverage.xml` → `check_quality.py` exits 1 with message "coverage.xml not found; run make quality first"
  - `uv run pip-audit --fail-on CRITICAL` with a pinned known-vulnerable package → exits non-zero (verify using a fixture `requirements.txt` with a CRITICAL CVE package in a scratch test; not against the real codebase)

- **Live E2E**: Not required — `make quality` executed against the real codebase on a clean PR is the acceptance test; passing CI `security` job on the first PR validates the scanning pipeline end-to-end.

### Documentation

- **`backend/pyproject.toml`** — update: add `pip-audit>=2.7` to `[dependency-groups] dev`; add `--cov-fail-under=90` to `addopts`
- **`backend/scripts/check_quality.py`** — create: threshold enforcement script
- **`Makefile`** — update: `make quality` target body (add pytest step, remove `|| true`, add check_quality.py call, update help text)
- **`.github/workflows/ci.yml`** — update: add `security` job; change `test-backend` postgres image to `postgres:16-alpine`
- **`CONTRIBUTING.md`** — update: add `## Repository Settings` section documenting branch protection configuration
- **`CLAUDE.md`** — update: commands table to note `make quality` now exits 1 on threshold violation; quality thresholds section to reference `check_quality.py` and GitHub Step Summary
- **`CHANGELOG.md`** — add `### Added` entry under `## [Unreleased]` at implementation time: security CI job (pip-audit + npm audit CRITICAL gate), quality threshold enforcement script (`check_quality.py`, `--cov-fail-under=90`), GitHub Actions Step Summary coverage table, Postgres 16 in CI test job

---

## 11. Test Suite Health & Coverage Deduplication

Prevent test suite bloat by detecting and eliminating intra-tier coverage duplication — where two test functions in the same tier (both unit, or both integration) exercise the same source line without adding distinct assertions. Uncontrolled duplication inflates run time, makes refactors expensive, and creates false assurance that a line is "well-tested" when it is only visited redundantly.

Cross-tier overlap (a unit test and an integration test covering the same line) is intentional and excluded from this check — unit and integration tests serve different verification purposes.

**Depends on**: Item 10 (CI/CD & Quality Gates) — `backend/scripts/` directory, `make quality` infrastructure, and `logs/quality/` scaffolding must be in place.

### Design decisions (resolved)

- **Definition of duplication**: Two test functions within the same tier (`tests/unit/` or `tests/integration/`) that cover the same source line. Cross-tier overlap is acceptable and not flagged. Rationale: identical behaviour tested at two levels of isolation is a quality multiplier; identical behaviour tested twice at the same level is waste.

- **Backend detection — pytest-cov context tracking**: `pytest-cov` passes `--cov-context=test` to `coverage.py` (supported since v5.x), tagging each `.coverage` database entry with the test node ID that executed it. `coverage json` then produces a JSON file whose `"contexts"` dict maps each covered line to a list of test IDs. A script classifies each test ID by tier (unit or integration by directory path) and flags any line with two or more context entries from the same tier. Rationale: no new dependencies — `coverage.py` is already a transitive dep of `pytest-cov`; the data is already collected after any `--cov` run; context tagging adds negligible overhead.

- **Frontend detection — per-test-file vitest runs**: vitest's V8 and Istanbul coverage providers aggregate coverage across all tests in a single run; neither attributes lines to individual test functions. The practical approach is to run each test file in isolation (`vitest run <file> --coverage`) and save a `coverage-summary.json` per file into a staging directory. A Node.js script then loads all per-file summaries and flags any source line appearing as covered in two or more test-file reports from the same tier. Rationale: per-file runs are the only way to achieve test-function-level attribution in vitest without a custom reporter; the frontend test suite is small (currently ~5 files), so N separate vitest processes is acceptable overhead for a local quality gate.

- **Reporting format — informational first**: Both scripts print a table of (source-file, line, tier, [test-ids]) tuples and a summary line ("N intra-tier duplicate lines across M source files"). Both exit 0 — the initial goal is visibility and baseline establishment, not hard enforcement. When the baseline is understood, a threshold can be added to `config/quality-thresholds.toml` to promote it to a gate. Rationale: enforcing zero tolerance on day one would require remediating unknown scope; track first, enforce later.

- **Correction strategy**: When duplication is flagged, determine whether the two tests assert the same behaviour (merge or delete the weaker test) or different behaviours that share an execution path (extract the shared path to a fixture or helper). No structural changes to test file organisation are required.

- **Backend `coverage json` output location**: Written to `logs/quality/coverage-contexts.json`. Added to `.gitignore` alongside other `logs/` data. Rationale: co-located with other quality artefacts; does not conflict with `coverage.xml` used by `check_quality.py`.

- **Frontend per-file staging directory**: `logs/quality/frontend-coverage-per-file/<test-file-slug>/coverage-summary.json`. Created and deleted on each run of `make check-coverage-overlap-frontend`. Rationale: ephemeral; the comparison script reads from this directory and the result is printed to stdout.

- **`make quality` integration**: Both overlap scripts are called at the end of `make quality` as informational steps and do not change its exit code. Rationale: quality gate exit code is already owned by `check_quality.py` and `--cov-fail-under=90`; adding a new exit-1 condition without calibration would cause spurious CI failures.

### Tasks

**Backend detection**
- [ ] Append `--cov-context=test` to the pytest invocation in the `make quality` Makefile target (on the same `uv run pytest --cov=app ...` line)
- [ ] Add `coverage json -o logs/quality/coverage-contexts.json` step to the `make quality` Makefile target, run immediately after pytest (requires `cd backend` prefix; the `.coverage` database is written by pytest-cov in the backend directory)
- [ ] Create `backend/scripts/check_coverage_overlap.py`:
  - Load `logs/quality/coverage-contexts.json` (path resolved relative to repo root); exit 1 with "Run make quality first to generate coverage data" if absent
  - For each source file in the JSON, iterate the `"contexts"` dict (maps line-number string → list of test node ID strings)
  - Classify each node ID as `unit` (contains `/tests/unit/`) or `integration` (contains `/tests/integration/`); skip `e2e` and unrecognised paths
  - Flag any line where two or more node IDs share the same tier classification
  - Print a table: `source_file | line | tier | test_a | test_b`; truncate test IDs to the function name for readability
  - Print summary: `N intra-tier duplicate lines found across M source files (unit: X, integration: Y)`
  - Exit 0 always
- [ ] Add `make check-coverage-overlap` Makefile target: `cd backend && uv run python scripts/check_coverage_overlap.py`
- [ ] Call `make check-coverage-overlap` at the end of the `make quality` target (after `check_quality.py`)

**Frontend detection**
- [ ] Create `scripts/check_coverage_overlap_frontend.sh` — for each `*.test.ts` / `*.test.tsx` file found under `frontend/tests/unit/` and `frontend/tests/integration/`, run `npx vitest run --coverage --coverage.reportsDirectory=../../logs/quality/frontend-coverage-per-file/<slug> <file>` where slug is the test file basename without extension; skip `e2e/` files
- [ ] Create `scripts/check_coverage_overlap_frontend.js` (Node.js, no external deps):
  - Scan `logs/quality/frontend-coverage-per-file/` for `coverage-summary.json` files; exit 0 with a warning if none found ("Run make check-coverage-overlap-frontend to generate per-file data")
  - For each source file, collect the set of line numbers reported as covered in each per-file report; classify by tier from the test file's directory path; flag any source line covered by two or more reports from the same tier
  - Print a table: `source_file | line | tier | test_file_a | test_file_b`
  - Print summary: `N intra-tier duplicate lines found across M source files`
  - Exit 0 always
- [ ] Add `make check-coverage-overlap-frontend` Makefile target: `bash scripts/check_coverage_overlap_frontend.sh && node scripts/check_coverage_overlap_frontend.js`
- [ ] Call `make check-coverage-overlap-frontend` at the end of the `make quality` target (after the vitest step)

**Baseline**
- [ ] Run `make check-coverage-overlap` and `make check-coverage-overlap-frontend` on the current codebase; add a `[test-health]` section to `config/quality-thresholds.toml` recording `baseline_backend_duplicate_lines = N` and `baseline_frontend_duplicate_lines = N` with a comment noting the date

**Gitignore**
- [ ] Verify that `logs/quality/coverage-contexts.json` and `logs/quality/frontend-coverage-per-file/` are excluded by the existing `logs/**` rule in `.gitignore`; add explicit entries only if not already covered

### Test strategy

- **Unit** (isolated, no external processes — Arrange-Act-Assert):
  - `check_coverage_overlap.py`: fixture `coverage-contexts.json` with two unit test IDs covering the same line in the same file → reports 1 duplicate at tier `unit`; fixture where a unit test and integration test cover the same line → reports 0 duplicates (cross-tier excluded); no duplication at all → "0 intra-tier duplicate lines found"; missing `coverage-contexts.json` → exits 1 with "Run make quality first"; malformed JSON → exits 1 with descriptive parse error, not an unhandled traceback
  - `check_coverage_overlap_frontend.js`: two `tests/unit/` coverage summaries sharing a line in a source file → 1 duplicate reported; `tests/unit/` and `tests/integration/` covering the same line → 0 duplicates (cross-tier excluded); empty staging directory → exits 0 with warning

- **Integration** (real filesystem — Arrange-Act-Assert):
  - `make check-coverage-overlap` runs against the real codebase (after `make quality`) → exits 0; summary line printed to stdout
  - `make check-coverage-overlap-frontend` runs against the real codebase → exits 0; summary line printed to stdout

- **Negative** (Arrange-Act-Assert):
  - Missing `logs/quality/coverage-contexts.json` → `check_coverage_overlap.py` exits 1 with message containing "Run make quality first"; no unhandled `FileNotFoundError`
  - Missing `logs/quality/frontend-coverage-per-file/` → `check_coverage_overlap_frontend.js` exits 0 with warning (non-blocking)
  - Test node ID that matches neither `tests/unit/` nor `tests/integration/` (e.g. `tests/e2e/`) → skipped without error; summary reflects only classified tiers

- **Live E2E**: Not required — passing `make quality` on a clean checkout with both overlap scripts exiting 0 is the acceptance criterion.

### Documentation

- **`Makefile`** — update: add `check-coverage-overlap`, `check-coverage-overlap-frontend` targets; update `make quality` to append `--cov-context=test`, add `coverage json` step, and call both overlap scripts
- **`backend/scripts/check_coverage_overlap.py`** — create
- **`scripts/check_coverage_overlap_frontend.sh`** — create
- **`scripts/check_coverage_overlap_frontend.js`** — create
- **`config/quality-thresholds.toml`** — update: add `[test-health]` section with baseline counts
- **`.gitignore`** — update: verify `logs/quality/coverage-contexts.json` and `logs/quality/frontend-coverage-per-file/` are excluded
- **`CLAUDE.md`** — update: commands table to add `make check-coverage-overlap` and `make check-coverage-overlap-frontend`
- **`CHANGELOG.md`** — add `### Added` entry under `## [Unreleased]` at implementation time: test suite health tooling (intra-tier coverage deduplication detection via `coverage.py` context tracking for pytest and per-test-file vitest runs)

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
