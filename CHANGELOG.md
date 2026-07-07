# Changelog

All notable changes to Price Pulse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added (Item 11 — Test Suite Health & Coverage Deduplication)

- Intra-tier coverage overlap detection — flags any source line covered by two or more test functions in the *same* tier (both `tests/unit/` or both `tests/integration/`); cross-tier overlap is intentional and excluded.
- Backend: `make quality` now tags coverage with `--cov-context=test` and emits `logs/quality/coverage-contexts.json` (`coverage json --show-contexts`); `backend/scripts/check_coverage_overlap.py` reads it and reports/enforces duplicates. `make check-coverage-overlap` runs it standalone.
- Frontend: `scripts/check_coverage_overlap_frontend.sh` runs each `tests/unit/` + `tests/integration/` file in isolation to stage per-file Istanbul coverage, and `scripts/check_coverage_overlap_frontend.js` reports/enforces same-tier overlap. `make check-coverage-overlap-frontend` runs both.
- Enforcement thresholds and baselines recorded in a new `[test-health]` section of `config/quality-thresholds.toml` (baseline captured 2026-07-07: backend 8, frontend 1112); both checks run at the end of `make quality` and exit 1 on net-new duplicates beyond the ceiling.

### Fixed (Item 11)

- `check_quality.py` crashed (`TypeError: string indices must be integers`) when any module had measured functions: radon 6.x emits `hal --json` `functions` as a `{name: metrics}` dict, but the parser iterated it as a list of dicts. It now handles both shapes, so `make quality` completes instead of aborting before threshold evaluation.

### Added (Items 13 & 14 — E2E Harness + Executed Behaviour Specification)

- `docs/behaviour/`: standardised, **executed** Gherkin behaviour catalogue (single source of truth) — `product_tracking`, `scraping`, `alerts`, `notification_channels`, and `ui_journeys` features with stable `@PP-E2E-NNN` IDs and a `@smoke` subset; `README.md` documents the ID convention and feature→step traceability
- Backend E2E runs under `pytest-bdd` (`backend/tests/e2e/steps/`); frontend UI journeys under `playwright-bdd` (`frontend/tests/e2e/steps/`); both runners point at `docs/behaviour/`. Assertions go through the public REST API / UI only
- `GET /api/v1/alerts/{alert_id}/notifications`: paginated `NotificationLogRead` endpoint so notification deliveries are assertable via the public API
- E2E harness (Item 13): `docker-compose.e2e.yml` overlay adds a custom `fixture-server` (canned HTML + `PUT /fixtures/{slug}/price` price mutation) and an off-the-shelf `webhook-sink`; sets `E2E_TEST_HOOKS=true`, `SCRAPE_INTERVAL_MINUTES=1`, and a small `ALERT_COOLDOWN_HOURS`
- Gated test-control hooks mounted only when `E2E_TEST_HOOKS=true` (absent otherwise, verified by unit test): `POST /api/v1/_test/products/{id}/scrape-sync` (inline scrape) and `POST /api/v1/_test/alerts/{id}/reset-cooldown`
- `make test-e2e` (up → pytest-bdd + playwright-bdd → down), `make test-e2e-smoke` (@smoke subset), `make e2e-up`, `make e2e-down`; CI `e2e` job runs `@smoke` on every PR/push and the full catalogue nightly + on `workflow_dispatch`
- `docs/decisions/e2e-behaviour-spec.md`: ADR for the executed-BDD approach; `pytest-bdd` (backend) and `playwright-bdd` (frontend) added as dev dependencies

### Security

- Bumped dependencies flagged by `pip-audit` to their fix versions: `python-multipart` ≥0.0.31 (CVE-2026-53538/53539/53540), `pydantic-settings` ≥2.14.2 (GHSA-4xgf-cpjx-pc3j), and — via `[tool.uv] constraint-dependencies` — `starlette` ≥1.3.1 (PYSEC-2026-248/249), `msgpack` ≥1.2.1 (GHSA-6v7p-g79w-8964), `pip` ≥26.1.2 (PYSEC-2026-196). `pip-audit` now reports no known vulnerabilities.

### Fixed

- **Newly-added products were never scheduled for scraping** (surfaced by the full E2E catalogue's beat-cadence scenario): `create_product` did not register a RedBeat schedule and there is no global sweep task, so a product added via the API was only ever picked up after a worker restart ran `startup_sync_schedules`. `create_product`/`delete_product` now register/deregister the per-product schedule (best-effort: a Redis error is logged, never fails the request; the worker's startup sync still reconciles on restart).
- **Celery never executed its `async def` tasks** (surfaced by the new executed E2E suite): the `solo`/prefork pools do not await coroutines, so `scrape_product`, `send_notification`, and schedule tasks failed with "coroutine is not JSON serializable" and never ran (notifications and scheduled scrapes were silently broken in the deployed stack). Fixed by adopting `celery-aio-pool`'s `AsyncIOPool` (`worker_pool="custom"` + `patch_celery_tracer()`).
- **Notification/scrape tasks were routed to an unconsumed queue**: `task_routes` targeted a `default` queue while the worker (no `-Q`) consumed Celery's built-in `celery` queue. Set `task_default_queue="default"` so routed tasks are actually consumed.
- **Celery worker could be permanently broken by a startup DB hiccup**: `on_worker_ready` let `startup_sync_schedules()` raise out of the signal handler, corrupting the async worker's event loop. It is now best-effort (logged, non-fatal).
- `docker/backend.Dockerfile`, `docker/celery-playwright.Dockerfile`: replaced `uv sync --no-install-workspace` with `uv export --package price-pulse-backend | uv pip install` to fix empty virtualenv — `--no-install-workspace` from the workspace root resolves only the root package (no deps) and produces an empty `.venv`, leaving celery and all other runtime dependencies uninstalled

### Changed

- `make down` now runs `docker image prune -f` after `docker compose down`, automatically removing dangling images left behind by rebuilds



### Added (Item 10 — CI/CD & Quality Gates)

- `backend/scripts/check_quality.py`: quality threshold enforcement script — reads radon CC/MI/Halstead JSON from the most recent `logs/quality/<timestamp>/` directory and `backend/coverage.xml`; exits 1 with a violation table when any threshold in `config/quality-thresholds.toml` is breached; when `GITHUB_ACTIONS=true`, appends a markdown `| Check | Value | Threshold | Status |` table with ✅/❌ indicators to `$GITHUB_STEP_SUMMARY`
- `backend/pyproject.toml`: added `pip-audit>=2.7` to `[dependency-groups] dev`; added `--cov-fail-under=90` to `addopts` so any direct `uv run pytest --cov=app` run fails when backend coverage drops below 90%
- `make quality` updated: now runs `pytest --cov=app --cov-report=xml:coverage.xml` first, then radon CC/MI/Halstead, then `npm run test:coverage`, then `check_quality.py`; all `|| true` guards removed; exits 1 on any threshold violation
- CI `security` job: runs in parallel with all other jobs; scans Python deps with `uv run pip-audit --fail-on CRITICAL` and Node.js deps with `npm audit --audit-level=critical`; fails the build on any CRITICAL CVE
- CI `test-backend` job: postgres service image updated from `postgres:15-alpine` to `postgres:16-alpine` to match `docker-compose.yml` and `testcontainers[postgres]` version
- `CONTRIBUTING.md`: added `## Repository Settings` section documenting required branch protection configuration for `main` (status checks: `Lint`, `Test — Backend`, `Test — Frontend`, `Build — Docker images`, `Security`, `Smoke`, `Agent quality`)

### Added (Item 9 — Claude Code Agents)

- `docs/architecture/repository-architecture.md`: rewritten from scaffold stub to full C4 doc — C1 system context, C2 container diagram (Postgres 16, celery-playwright container), C3 backend component diagram (all six layers), module domain-grouping convention, ASCII ER diagram for all four ORM tables, ADR index table
- `.github/skills/profiling/findings.md`: stub file for durable profiling findings appended by `profiling-reviewer` agent
- `make init-logs`: creates `logs/quality/`, `logs/profiling/backend/`, `logs/profiling/tasks/`, `logs/profiling/frontend/`, `logs/profiling/test-timing/` with `.gitkeep` stubs; idempotent; called by `make install`
- `make lint-agents`: validates frontmatter completeness (`name`, `description`, `tools` in `.claude/agents/`; `description` in `.github/agents/`) and checks Quick Commands referenced paths exist on disk; exits 1 on any failure
- CI `agent-quality` job: runs in parallel with other CI jobs; calls `make init-logs` then `make lint-agents`; gates PRs on agent file correctness
- `.gitignore`: updated `logs/` rule to `logs/**` + `!logs/**/.gitkeep` so log data is excluded but directory stubs are tracked
- Agent sync: aligned `.claude/agents/` and `.github/agents/` pairs — architecture-maintainer now references `backend/tests/` and `frontend/tests/` consistently; quality agent default run includes `-m "not live_api"`; profiling-reviewer Quick Commands use timestamped output paths and include pyinstrument command

### Added (Item 8 — Docker Containerisation)

- `docker/backend.Dockerfile` production-grade multi-stage build: builder stage now copies root `pyproject.toml` + `uv.lock*` before `backend/pyproject.toml` so `uv sync --frozen --no-dev` resolves the full locked dependency tree; production stage installs `curl` (required for the `HEALTHCHECK CMD`) via `apt-get`
- `docker/celery-playwright.Dockerfile`: `--pool=gevent` corrected to `--pool=asyncio`; `uv sync` upgraded to `--frozen` for reproducible installs
- `docker/nginx.conf`: four browser security headers added — `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-XSS-Protection: 0`
- `docker-compose.yml`: `celery-worker` command fixed from `--concurrency=4` (pre-fork) to `--pool=asyncio`; postgres upgraded from `15-alpine` to `16-alpine`; `deploy.resources.limits` added for all seven services (backend 512m/0.50CPU, celery-worker 512m/1.00, celery-beat 256m/0.25, celery-playwright 1g/1.00, postgres 512m/0.50, redis 128m/0.25, frontend 128m/0.25)
- `.env.example`: `CORS_ORIGINS=http://localhost` added with inline comment (required when `DEBUG=false`)
- `make lint-docker`: hadolint linting of all three Dockerfiles via Docker; fails on ERROR or WARN
- `make validate-nginx`: `nginx -t` syntax check against `docker/nginx.conf` via Docker; asserts exit 0
- `make scan`: Trivy image scan of built backend + frontend images; fails on any CRITICAL CVE
- `make smoke`: `docker compose up -d` → poll `GET http://localhost:8000/health` every 5s (12 attempts) → `curl http://localhost/nginx-health` → `docker compose down`; exits 1 on timeout or bad status
- CI `smoke` job: runs after `build`; spins up full compose stack from `.env.example`, waits for backend health via polling, asserts nginx health endpoint and SPA shell, tears down

### Added

- Price Scraping Engine: pluggable scraper layer with `BaseScraper` abstract class, `GenericScraper` (CSS-selector-driven), and `AmazonScraper` (Playwright headless browser with ld+json extraction)
- `ExtractionStatus` enum (`ok`, `extraction_failed`, `http_error`) in `app.models.enums`
- `ScrapedResult` Pydantic schema in `app.schemas.scraper` capturing URL, HTML, hash, price, currency, and extraction status
- `app.scrapers.http_client.fetch_page`: shared async httpx client with User-Agent rotation (8 agents), rate-limiting (Redis-backed per-domain TTL), robots.txt checking (log-and-proceed), retry on 5xx/429/403 with exponential back-off [1, 2, 4]s, and Retry-After header support
- `app.scrapers.registry.get_scraper`: maps `source_type` string to scraper class; raises `UnknownSourceError` for unregistered types (ebay, currys, unknown)
- `app.services.price_service.record_price`: HTML-hash deduplication, PriceRecord persistence, conditional alert evaluation
- `app.services.alert_service.evaluate_alerts`: threshold comparison (above/below), 24h cooldown, notification dispatch
- `app.services.notifications.notify_alert`: stub dispatcher (replaced by Celery task in Item 5)
- `Product.css_selector_currency` nullable column for per-product currency selector
- `PriceRecord.price` and `PriceRecord.currency` made nullable; `PriceRecord.extraction_status` VARCHAR(20) column added
- Alembic migrations 0003 (css_selector_currency) and 0004 (nullable price/currency + extraction_status)
- `docker/celery-playwright.Dockerfile`: Playwright-capable Celery worker image for Amazon scraping
- `celery-playwright` service added to `docker-compose.yml` and `docker-compose.dev.yml`
- `SCRAPE_MIN_DELAY_SECONDS` setting (default 2) added to `app.core.config.Settings`
- `playwright>=1.44` and `parsel>=1.9` added to backend runtime dependencies
- `celery[redis,asyncio]` replaces `celery[redis]` in backend dependencies
- `live_amazon` pytest marker for Amazon live-scrape tests

### Added (Item 7 — Frontend React Application)

- React SPA scaffold fully implemented with Vite + TypeScript + shadcn/ui (Radix UI primitives + Tailwind CSS)
- `src/pages/Dashboard`: infinite-scroll product list via `useInfiniteQuery` + IntersectionObserver; is_active filter buttons; per-row DropdownMenu (Edit, Activate/Deactivate, Delete); `ProductFormDialog` and `ConfirmDialog` integration; Skeleton + empty-state
- `src/pages/ProductDetail`: product header with name, URL, source type Badge, Scrape Now button (202 + sonner toast); `PriceChart` with Recharts `LineChart`; active alert count + "Manage alerts" link
- `src/pages/AlertManager`: alert table with direction/channel/status Badges; create/edit via `AlertFormDialog`; delete via `ConfirmDialog`; breadcrumb back to product; is_active filter
- `src/components/PriceChart`: date-range picker (shadcn/ui Popover + Calendar, react-day-picker); filters null-price records; custom Recharts tooltip with formatted price + date; Skeleton + empty-state
- `src/components/ProductFormDialog`: zod schema validation; conditional `css_selector` field (generic source type only); create/edit modes; sonner toast on success
- `src/components/AlertFormDialog`: conditional `webhook_url` / `whatsapp_number` fields driven by `watch('channel')`; `superRefine` makes per-channel fields required; create/edit modes
- `src/components/ConfirmDialog`: shadcn/ui `AlertDialog`; `isLoading` prop shows spinner; destructive action button
- `src/components/Layout`: sticky top-nav with "Price Pulse" brand link and light/dark theme toggle; `useEffect` syncs Zustand `colorScheme` to `document.documentElement.classList`
- `src/components/ErrorBoundary`: class-based error boundary wrapping all routes; renders error Card with "Try again" button
- `src/hooks/useProducts`: `useInfiniteProducts`, `useProduct`, `useCreateProduct`, `useUpdateProduct`, `useDeleteProduct`
- `src/hooks/usePrices`: `usePrices` with 60s `refetchInterval`
- `src/hooks/useAlerts`: `useAlerts`, `useCreateAlert`, `useUpdateAlert`, `useDeleteAlert`
- `src/hooks/useScrape`: `useScrapeProduct` mutation with sonner success/error toasts
- `src/api/client.ts`: typed axios wrapper with error interceptor normalising to `{detail: string}`; `productsApi`, `pricesApi`, `alertsApi`
- `src/api/types.ts`: hand-written TypeScript interfaces for all backend entities (`ProductRead`, `PriceRecordRead`, `AlertRead`, `PaginatedResponse<T>`, `ScrapeJobResponse`)
- `src/store/uiStore.ts`: Zustand store for `selectedProductId`, `colorScheme`, `activeProductFilter`, `activeAlertFilter`
- `src/lib/formatPrice.ts`: `Intl.NumberFormat` price formatter; returns `'—'` for null/undefined/NaN
- shadcn/ui component suite: `Button`, `Card`, `Badge`, `Skeleton`, `Input`, `Label`, `Select`, `Dialog`, `DropdownMenu`, `AlertDialog`, `Popover`, `Calendar`, `Form`
- Tailwind CSS with `darkMode: 'class'`; full CSS variable palette (light + dark) in `globals.css`
- `tests/mocks/handlers.ts` + `tests/mocks/server.ts`: MSW v2 handlers for all API endpoints
- vitest setup: jsdom Pointer Events polyfills for Radix UI compatibility; MSW server lifecycle hooks
- Unit tests: `formatPrice` (7 cases), `uiStore` (5 cases), `ConfirmDialog` (3), `ProductFormDialog` (2), `AlertFormDialog` (3) — 22 tests total, all passing
- `frontend/playwright.config.ts` and `tests/e2e/smoke.spec.ts`: Playwright smoke test (Dashboard → ProductDetail → AlertManager)
- `make test-e2e` and `make generate-types` Makefile targets added
- `npx playwright install chromium` added to `make install`

### Added (Item 6 — REST API Endpoints)

- `app.api.v1.products`: full product CRUD (`POST/GET/PATCH/DELETE /api/v1/products`); duplicate-URL 409 guard; `?is_active` filter; `created_at DESC` ordering; max page size 100
- `app.api.v1.prices`: `GET /api/v1/products/{id}/prices` with `from_dt`/`to_dt` ISO 8601 window filters; `POST /api/v1/products/{id}/scrape` dispatching `scrape_product.delay()` and returning 202 `ScrapeJobResponse`
- `app.api.v1.alerts`: full alert CRUD (`POST/GET/PATCH/DELETE /api/v1/alerts`); `?product_id` and `?is_active` filters; `id ASC` ordering; `product_id` immutable after creation (returns 422 if passed on PATCH)
- `app.api.v1.router`: aggregated `APIRouter` mounted at `/api/v1` in `main.py`
- `app.schemas.common`: `PaginatedResponse[T]` generic envelope (`items`, `total`, `limit`, `offset`; `limit` capped at 100) and `ScrapeJobResponse` (`task_id`, `status: "queued"`, `product: ProductRead`)
- `PriceRecordRead` schema updated: `price` and `currency` are now nullable (matching Item 4 migration); `extraction_status: str` field exposed
- `AlertUpdate` schema: `product_id` removed; `model_config = ConfigDict(extra="forbid")` ensures 422 on any unknown field
- `pg_async_client` fixture added to `tests/conftest.py`: mirrors `async_client` but uses Postgres testcontainer, for route integration tests requiring native ENUMs
- `make generate-openapi` Makefile target: writes `backend/openapi.json` from the live FastAPI app metadata (no server required); committed to git for contract testing
- `backend/openapi.json`: generated OpenAPI 3.1.0 spec (33 KB) covering all routes, schemas, and response codes
- 58 new tests: 14 unit (schema validation), 44 integration (CRUD + negative cases via `pg_async_client`)

### Added (Item 5 — Celery Task Infrastructure)

- `app.workers.celery_app`: Celery application factory with asyncio pool, RedBeat scheduler, task time limits (120s soft / 150s hard), and queue routing
- `app.tasks.scrape.scrape_product`: async bound task; fetches product, dispatches to `'playwright'` queue for Amazon, retries with exponential back-off (1s/2s/4s, max 3)
- `app.tasks.schedule`: `register_product_schedule`, `deregister_product_schedule`, `startup_sync_schedules` (worker_ready signal); RedBeat-backed per-product intervals
- `app.tasks.notify.send_notification`: async bound task; email stub (INFO log), real webhook via httpx, WhatsApp stub (WARNING log, pending provider ADR); creates `NotificationLog` row with final status
- `celery-redbeat>=0.13` added to runtime dependencies; `fakeredis>=2.0` added to dev dependencies
- `CELERY_RESULT_BACKEND` and `ALERT_COOLDOWN_HOURS` added to `app.core.config.Settings`
- `ALERT_COOLDOWN_HOURS=24` added to `.env.example`
- `NotificationChannel.whatsapp` enum value added; `PriceAlert.channel`, `webhook_url`, `whatsapp_number` columns added
- Alembic migration 0005 (`add_alert_channel_whatsapp`): extends `notification_channel_enum` with `'whatsapp'`, adds three columns to `price_alert`
- `make worker` and `make beat` Makefile targets updated to use `--pool=asyncio` and `--scheduler redbeat.RedBeatScheduler`
- `docker-compose.yml` and `docker-compose.dev.yml` celery-beat commands updated to use `redbeat.RedBeatScheduler` (replaces incompatible `django_celery_beat.schedulers:DatabaseScheduler`)
- `docs/decisions/whatsapp-provider.md`: WhatsApp provider spike ADR (Twilio recommended; implementation deferred pending ADR approval)
- Unit tests for enums, scrapers, http_client, price_service, alert_service, notifications
- Integration tests for price_service and alert_service against Postgres testcontainer

- Core domain models: `Product`, `PriceRecord`, `PriceAlert`, `NotificationLog` ORM models with SQLAlchemy 2.0 mapped columns and full cascade-delete relationships
- Four native Postgres ENUM types: `source_type_enum` (`generic`, `amazon`, `ebay`, `currys`), `alert_direction_enum` (`above`, `below`), `notification_channel_enum` (`email`, `webhook`), `notification_status_enum` (`pending`, `sent`, `failed`)
- Alembic migration `0002_add_core_domain_models`: creates all four tables, ENUM types, FK constraints, and four named composite indexes (`ix_price_record_product_captured`, `ix_price_record_html_hash`, `ix_price_alert_product_active`, `ix_notification_log_alert_sent`) atomically
- Pydantic v2 schemas: `ProductCreate/Read/Update`, `PriceRecordCreate/Read`, `AlertCreate/Read/Update`, `NotificationLogRead` — separate from ORM models with `from_attributes=True` on read schemas
- `testcontainers[postgres]>=4.0` added to dev dependencies for Postgres integration tests
- `pg_container`, `pg_engine`, and `pg_session` fixtures in `tests/conftest.py` for integration tests against a real Postgres container
- Backend foundation: FastAPI application factory with async lifespan, CORS middleware, and `GET /health` readiness probe
- `app.core.config` — pydantic-settings `Settings` class; validates `SECRET_KEY` (≥32 chars), `CORS_ORIGINS` (defaults to `["*"]` in debug, required in production), and `CELERY_BROKER_URL` (falls back to `REDIS_URL`)
- `app.core.logging` — structlog configured at import time; `ConsoleRenderer` in debug, `JSONRenderer` in production
- `app.core.database` — async SQLAlchemy engine (`asyncpg` for Postgres, `StaticPool` for SQLite in tests), `AsyncSessionLocal` factory, `Base` declarative class, `get_db` dependency
- `app.core.exceptions` — FastAPI exception handlers for `HTTPException`, `RequestValidationError`, and unhandled `Exception` (500 with structlog traceback)
- Alembic migration environment using async `run_sync` pattern; `env.py` reads `DATABASE_URL` from `settings`; baseline `0001_init` migration
- Backend directory tree: `app/core/`, `app/api/v1/`, `app/models/`, `app/schemas/`, `app/services/`, `app/scrapers/`, `app/workers/`, `app/tasks/` — all with `__init__.py`
- Test infrastructure: `conftest.py` with `db_engine`, `db_session`, and `async_client` fixtures using SQLite in-memory; 34 tests across unit, integration, and (skipped) live-api tiers

---

## [0.1.0] - 2026-05-24

### Added

- Repository scaffolding: monorepo structure with `backend/` and `frontend/` directories
- Root `pyproject.toml` with `uv` workspace declaring `backend` as a member
- Root `package.json` with `commitlint` and `@commitlint/config-conventional`
- `commitlint.config.js` enforcing Conventional Commits with project-specific scopes
- `Makefile` with all development targets: `install`, `dev`, `up`, `down`, `logs`, `build`, `test`, `test-backend`, `test-frontend`, `lint`, `format`, `quality`, `migrate`, `shell-backend`, `shell-db`, `worker`, `beat`, `structure`
- `docker-compose.yml`: production-like stack with backend, celery-worker, celery-beat, frontend, postgres (15-alpine), and redis (7-alpine); all services with health-checks and named volumes
- `docker-compose.dev.yml`: dev overrides with hot-reload volume mounts, Flower (port 5555), and pgAdmin (port 5050)
- `.env.example`: single source of truth for all environment variables with documentation
- `.pre-commit-config.yaml`: trailing-whitespace, end-of-file-fixer, check-yaml/toml/json, ruff (Python lint + format), commitlint (commit-msg stage), eslint + prettier (frontend)
- `README.md`: project overview, prerequisites, quick-start guide, and Makefile target reference
- `CONTRIBUTING.md`: GitHub Flow branch strategy, Conventional Commits format with examples, PR checklist, quality gate requirement
- `LICENSE`: MIT licence
- `.gitignore`: Python, Node, Docker, uv, and `.env` artefacts
- `backend/pyproject.toml`: workspace member with full dependency specification
- `backend/tests/test_smoke.py`: placeholder smoke test
- Stub Dockerfiles in `docker/` (to be replaced with multi-stage builds in v0.8.0)
- `config/quality-thresholds.toml`: quality gate configuration
- `.github/workflows/ci.yml`: CI pipeline with lint, test-backend (Postgres service), test-frontend, and build jobs

[Unreleased]: https://github.com/org/price-pulse/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/org/price-pulse/releases/tag/v0.1.0
