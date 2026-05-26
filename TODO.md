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
- [ ] Create `backend/app/models/enums.py` — define `ExtractionStatus(str, Enum)` with `OK = 'ok'`, `EXTRACTION_FAILED = 'extraction_failed'`, `HTTP_ERROR = 'http_error'`
- [ ] Create `backend/app/schemas/scraper.py` — define `ScrapedResult` Pydantic model: `url: str`, `html: str`, `html_hash: str`, `price: Decimal | None`, `currency: str | None`, `scraped_at: datetime`, `extraction_status: ExtractionStatus`

**Scraper layer**
- [ ] Create `backend/app/scrapers/exceptions.py` — `ScraperError(Exception)` and `UnknownSourceError(ScraperError)`
- [ ] Define `backend/app/scrapers/base.py` — abstract `BaseScraper` with abstract `fetch(url: str) -> ScrapedResult`; protected `_compute_hash(html: str) -> str` (SHA-256 hex)
- [ ] Implement `backend/app/scrapers/http_client.py` — async httpx client: 8-UA string pool (random selection per request); per-domain Redis rate limit (key `rate_limit:{domain}`, TTL = `settings.SCRAPE_MIN_DELAY_SECONDS`); robots.txt Redis cache (key `robots:{domain}`, TTL 1 hour, log-and-proceed for disallowed paths); retry on 5xx / 429 / 403 with 1s/2s/4s back-off; 429 honours `Retry-After`; returns `ScrapedResult(extraction_status='http_error')` after retries exhausted
- [ ] Implement `backend/app/scrapers/generic.py` — `GenericScraper(BaseScraper)`: fetches via `http_client`; uses `parsel.Selector` with `Product.css_selector` (raises `ScraperError` if `None`); extracts currency via `Product.css_selector_currency` mapping symbol → ISO code; returns fully populated `ScrapedResult`
- [ ] Implement `backend/app/scrapers/amazon.py` — `AmazonScraper(BaseScraper)`: per-task Playwright browser (async with `async_playwright()` → launch → new_context → new_page → `goto(url, timeout=30_000)` → `evaluate(js_snippet)` → close); JS snippet targets `ld+json` `schema.org/Product` or `/Offer` for `price` + `priceCurrency`; returns `ScrapedResult(extraction_status='extraction_failed')` if ld+json absent; raises `ScraperError` for unexpected Playwright exceptions
- [ ] Create `backend/app/scrapers/registry.py` — `SourceType(str, Enum)` with `GENERIC='generic'`, `AMAZON='amazon'`, `EBAY='ebay'`, `CURRYS='currys'`; `_REGISTRY: dict[SourceType, type[BaseScraper]]` (maps only `GENERIC` and `AMAZON`); `get_scraper(source_type: str) -> BaseScraper` — raises `UnknownSourceError` for unregistered strings (including `ebay` and `currys` until their items)

**Service layer**
- [ ] Create `backend/app/services/notifications.py` — `notify_alert(alert_id: int) -> None` stub: logs `{"event": "notify_alert_stub", "alert_id": alert_id}` via structlog and returns `None`. Item 5 replaces with `send_notification.delay(alert_id)`.
- [ ] Implement `backend/app/services/price_service.py` — `record_price(product_id: int, scraped_result: ScrapedResult) -> PriceRecord`: (1) fetch most recent `PriceRecord` for product; (2) if `raw_html_hash` matches, return existing record (no insert); (3) otherwise insert new `PriceRecord` (propagates `price`, `currency`, `extraction_status` from `ScrapedResult`); (4) call `alert_service.evaluate_alerts(product_id)` only when `extraction_status == ExtractionStatus.OK`
- [ ] Implement `backend/app/services/alert_service.py` — `evaluate_alerts(product_id: int) -> None`: (1) fetch latest `PriceRecord`; (2) return early (structlog WARNING) if `extraction_status != ExtractionStatus.OK`; (3) load all `is_active=True` alerts for product; (4) for each: skip if `now() < notified_at + timedelta(hours=24)`; compare `price` against `threshold_price` by `direction`; if triggered, set `notified_at = now()` and call `notifications.notify_alert(alert.id)`

**Dependencies and configuration**
- [ ] Add to `backend/pyproject.toml` runtime deps: `playwright>=1.44`, `parsel>=1.9`; replace `celery[redis]` with `celery[redis,asyncio]>=5.4`
- [ ] Add `SCRAPE_MIN_DELAY_SECONDS: int = 2` to `backend/app/core/config.py` `Settings`
- [ ] Update `Makefile` `install` target: after `uv sync`, add `cd backend && uv run playwright install chromium`
- [ ] Register `live_amazon` pytest marker in `backend/pyproject.toml`: `"live_amazon: marks Amazon live-scrape tests; requires celery-playwright service running; flaky in CI due to bot detection — run manually only"`
- [ ] Update `.env.example`: add `SCRAPE_MIN_DELAY_SECONDS=2`

**Migrations**
- [ ] Generate Alembic migration: add `css_selector_currency VARCHAR NULL` to `products` table (`alembic revision --autogenerate -m "add_css_selector_currency"`)
- [ ] Generate Alembic migration: make `price_records.price` and `price_records.currency` nullable; add `extraction_status VARCHAR(20) NOT NULL DEFAULT 'ok'` with `CHECK` constraint (`alembic revision --autogenerate -m "add_extraction_status_nullable_price"`)

**Docker**
- [ ] Create `docker/celery-playwright.Dockerfile` — base: `mcr.microsoft.com/playwright/python:latest`; copies `backend/`; runs `uv sync --no-dev`; CMD: `celery -A app.workers.celery_app worker --pool=asyncio -Q playwright --loglevel=info`
- [ ] Add `celery-playwright` service to `docker-compose.yml`: built from `celery-playwright.Dockerfile`; env `CELERY_QUEUES=playwright`; `depends_on: [redis, postgres]`
- [ ] Add `celery-playwright` service override to `docker-compose.dev.yml`: volume mount for hot-reload; `DEBUG=true`

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
- [ ] Add `celery-redbeat>=0.13` to `backend/pyproject.toml` runtime dependencies (no WhatsApp provider SDK until spike ADR is approved)
- [ ] Add `CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"` to `Settings` in `backend/app/core/config.py`
- [ ] Add `ALERT_COOLDOWN_HOURS: int = 24` to `Settings` in `backend/app/core/config.py`
- [ ] Update `.env.example`: add `ALERT_COOLDOWN_HOURS=24` (note: `CELERY_RESULT_BACKEND` already present; no WhatsApp provider vars until spike ADR is approved)
- [ ] Update `backend/app/services/alert_service.py`: replace hardcoded `timedelta(hours=24)` with `timedelta(hours=settings.ALERT_COOLDOWN_HOURS)`

**Model and schema amendments (cross-item)**
- [ ] Add `whatsapp = 'whatsapp'` to `NotificationChannel(str, enum.Enum)` in `backend/app/models/notification_log.py`
- [ ] Add `channel` (`notification_channel_enum`, NOT NULL, default `'email'`), `webhook_url` (`VARCHAR(512)`, nullable), and `whatsapp_number` (`VARCHAR(20)`, nullable, E.164) columns to `PriceAlert` model in `backend/app/models/alert.py`
- [ ] Update `backend/app/schemas/alert.py`: add `channel: NotificationChannel = NotificationChannel.email`, `webhook_url: str | None = None`, and `whatsapp_number: str | None = None` to `AlertBase`; propagates to `AlertCreate`, `AlertRead`, `AlertUpdate`
- [ ] Generate Alembic migration: `alembic revision --autogenerate -m "add_alert_channel_whatsapp"`; verify the generated file includes: `ALTER TYPE notification_channel_enum ADD VALUE 'whatsapp'` (before the table alteration); adds `channel notification_channel_enum NOT NULL DEFAULT 'email'`, `webhook_url VARCHAR(512) NULL`, and `whatsapp_number VARCHAR(20) NULL` columns to `price_alert` table. Note: autogenerate does not emit `ALTER TYPE … ADD VALUE` automatically — add it manually in `upgrade()` before `op.add_column()` calls

**Celery application factory**
- [ ] Implement `backend/app/workers/celery_app.py` — create `Celery` app with: `broker=settings.CELERY_BROKER_URL`, `backend=settings.CELERY_RESULT_BACKEND`, `worker_pool='celery.concurrency.aio:TaskPool'`, `task_soft_time_limit=120`, `task_time_limit=150`, `task_routes={'app.tasks.scrape.scrape_product': {'queue': 'default'}, 'app.tasks.notify.send_notification': {'queue': 'default'}}` (Amazon queue override applied at dispatch time, not in static routes), `redbeat_redis_url=settings.REDIS_URL`; call `app.autodiscover_tasks(['app.tasks'])`

**Tasks**
- [ ] Implement `backend/app/tasks/scrape.py` — `async def scrape_product(self, product_id: int)` bound task (`bind=True`): open `AsyncSessionLocal`, fetch `Product`, call `registry.get_scraper(product.source_type).fetch(product.url)`, call `price_service.record_price(product_id, result, session)`; dispatch to `'playwright'` queue if `source_type == SourceType.AMAZON`; on exception call `self.retry(countdown=2 ** self.request.retries, max_retries=3)`; on exhaustion log structlog ERROR with full exception
- [ ] Implement `backend/app/tasks/schedule.py` — `register_product_schedule(product_id: int, interval_minutes: int) -> None`: creates or updates a `RedBeatSchedulerEntry` for `scrape_product` with `run_every=timedelta(minutes=interval_minutes)`, key `f"scrape:{product_id}"`; `deregister_product_schedule(product_id: int) -> None`: deletes the redbeat key; `startup_sync_schedules() -> None`: queries all `is_active=True` products from DB and calls `register_product_schedule` for each — called at worker startup via the Celery `worker_ready` signal
- [ ] Implement `backend/app/tasks/notify.py` — `async def send_notification(self, alert_id: int)` bound task: open `AsyncSessionLocal`, fetch `PriceAlert` with product and latest `PriceRecord`; build payload `{"product_id", "product_name", "product_url", "current_price", "threshold_price", "direction"}`; create `NotificationLog(alert_id=..., channel=alert.channel, payload=payload, status='pending')`; dispatch based on `alert.channel`: `email` → structlog INFO stub + set `status='sent'`; `webhook` → `httpx.AsyncClient().post(alert.webhook_url, json=payload, timeout=10.0)` + set `status='sent'`/`'failed'`; `whatsapp` → structlog WARNING stub (`{"event": "whatsapp_stub", "alert_id": ..., "whatsapp_number": ...}`) + set `status='sent'` (provider wired in follow-on item after spike ADR); on any exception call `self.retry(countdown=5, max_retries=3)`; on exhaustion set `NotificationLog.status='failed'`, log structlog ERROR
- [ ] Update `backend/app/services/notifications.py` — replace `notify_alert` stub body with `from app.tasks.notify import send_notification; send_notification.delay(alert_id)` (preserving the function signature so `alert_service.py` import is unchanged)

**WhatsApp provider spike**
- [ ] Spike: evaluate WhatsApp delivery providers — compare **Meta WhatsApp Business Cloud API** (direct, no intermediary), **Twilio**, **Vonage**, and **MessageBird/Bird** across: sandbox/test number availability, Python SDK maturity and async support, per-message pricing at low volume, rate limits, webhook vs polling for delivery receipts, and setup complexity. Document findings and the chosen provider in a new ADR at `docs/decisions/whatsapp-provider.md`. Outcome feeds a follow-on task (add to backlog once ADR is approved) that replaces the `whatsapp_stub` with real delivery.

**Docker**
- [ ] Update `docker-compose.yml` celery-beat `command`: replace `django_celery_beat.schedulers:DatabaseScheduler` argument with `--scheduler redbeat.RedBeatScheduler`
- [ ] Update `docker-compose.dev.yml` celery-beat `command`: add `--scheduler redbeat.RedBeatScheduler`

**Makefile**
- [ ] Add `make worker` target: `cd backend && uv run celery -A app.workers.celery_app worker --pool=asyncio --loglevel=debug`
- [ ] Add `make beat` target: `cd backend && uv run celery -A app.workers.celery_app beat --scheduler redbeat.RedBeatScheduler --loglevel=debug`

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
- [ ] Create `backend/app/schemas/common.py` — define generic `PaginatedResponse[T](BaseModel)` with fields `items: list[T]`, `total: int`, `limit: int`, `offset: int`; define `ScrapeJobResponse(BaseModel)` with fields `task_id: str`, `status: Literal["queued"]`, `product: ProductRead`
- [ ] Update `backend/app/schemas/alert.py` — remove `product_id` field from `AlertUpdate` (product FK is read-only after creation); retain all other optional fields

**Celery stub**
- [ ] Create `backend/app/tasks/scrape.py` stub — plain function `def scrape_product(product_id: int) -> str: raise NotImplementedError("Celery not wired — complete item 5")`; item 5 replaces this with a decorated Celery task and no API changes are needed

**Route handlers**
- [ ] Implement `backend/app/api/v1/products.py` — routes with OpenAPI tags/descriptions/response models:
  - `POST /products` → 201 `ProductRead`; raises 409 if URL already exists
  - `GET /products` → 200 `PaginatedResponse[ProductRead]`; optional `?is_active=true/false`; ordered `created_at DESC`; max page size 100
  - `GET /products/{id}` → 200 `ProductRead`; 404 if not found
  - `PATCH /products/{id}` → 200 `ProductRead`; 404 if not found; 409 if URL conflicts with another product
  - `DELETE /products/{id}` → 204 No Content; 404 if not found
- [ ] Implement `backend/app/api/v1/prices.py` — routes with OpenAPI tags/descriptions/response models:
  - `GET /products/{id}/prices` → 200 `PaginatedResponse[PriceRecordRead]`; params: `limit`, `offset`, optional `from_dt` (ISO 8601 datetime), `to_dt` (ISO 8601 datetime); ordered `captured_at DESC`; 404 if product not found
  - `POST /products/{id}/scrape` → 202 `ScrapeJobResponse`; calls `scrape_product(product_id)` stub; 400 if product `is_active=False`; 404 if product not found
- [ ] Implement `backend/app/api/v1/alerts.py` — routes with OpenAPI tags/descriptions/response models:
  - `POST /alerts` → 201 `AlertRead`; 404 if `product_id` does not exist
  - `GET /alerts` → 200 `PaginatedResponse[AlertRead]`; optional `?product_id=X`; optional `?is_active=true/false`; ordered `id ASC`; max page size 100
  - `GET /alerts/{id}` → 200 `AlertRead`; 404 if not found
  - `PATCH /alerts/{id}` → 200 `AlertRead`; 404 if not found; 422 if `product_id` supplied in body
  - `DELETE /alerts/{id}` → 204 No Content; 404 if not found

**Router and wiring**
- [ ] Create `backend/app/api/v1/router.py` — instantiate `APIRouter`; include `products_router`, `prices_router`, `alerts_router`; export `api_router`
- [ ] Update `backend/app/main.py` — uncomment the router stub (lines 109–111): `from app.api.v1.router import api_router` + `app.include_router(api_router, prefix="/api/v1")`

**Test infrastructure**
- [ ] Add `pg_async_client` fixture to `backend/tests/conftest.py` — mirrors `async_client` but uses `pg_engine` (Postgres testcontainer); overrides `get_db` with a Postgres-backed session factory; function-scoped

**Makefile and tooling**
- [ ] Add `generate-openapi` target to `Makefile`: `cd backend && uv run python -c "import json; from app.main import app; open('openapi.json','w').write(json.dumps(app.openapi()))"`; run manually before each PR
- [ ] Run `make generate-openapi` after implementation and commit `backend/openapi.json`

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
