# Plan Review Findings

This file logs the output of the `plan-review` agent for each TODO.md item reviewed. Entries are appended chronologically.

---

<!-- Entries are appended below by the plan-review agent -->

## TODO item 1 — Repository Scaffolding (2026-05-24)

**Ambiguities found**: 8

| Category | Finding | Resolution |
|---|---|---|
| Scope gaps | `.pre-commit-config.yaml` not listed in item 1 (only item 10) but needed to enforce Conventional Commits from day one | Moved to item 1; `make install` runs `pre-commit install` |
| Scope gaps | No root-level `pyproject.toml` / uv workspace mentioned despite uv being the chosen package manager | Root `pyproject.toml` with `[tool.uv.workspace]` added as first task |
| Model/data design | `VITE_*` frontend env vars absent from `.env.example` task | Root `.env.example` is single source of truth covering both backend and frontend vars |
| Error & edge-case handling | CI `test-backend` job unspecified — SQLite vs real Postgres; affects whether Postgres-specific queries can be validated | Postgres service container in GitHub Actions |
| Integration wiring | CI `build` job undefined: every PR or main only; push or no-push | Docker images built on every PR, pushed on main only; `--cache-from` for speed |
| Scope gaps | Flower + pgAdmin absent from `docker-compose.dev.yml` task description | Both added to dev compose (ports 5555, 5050) |
| Documentation | Commit convention unspecified despite CONTRIBUTING.md being listed | Conventional Commits mandated; `commitlint` in CI + pre-commit |
| Conflict / overwrite policy | `LICENCE` (British) vs `LICENSE` (American) — affects GitHub auto-detection and SPDX tooling | Use `LICENSE` (American, OSS standard) |

**Tasks added**: 3 — root `pyproject.toml` workspace creation; `.pre-commit-config.yaml` creation; `make install` expanded to include `pre-commit install`
**Tasks removed/changed**: 1 — `LICENCE` renamed to `LICENSE`; `.env.example` task expanded to name all variables including `VITE_API_URL`; CI task expanded to specify Postgres service + build scope
**Documentation changes**: `CLAUDE.md` (update — install + dev commands + env table); `CONTRIBUTING.md` (create); `CHANGELOG.md` (create)
**Key design constraint**: Docker Compose is the sole dev environment strategy — no hybrid native processes; `docker-compose.dev.yml` is the canonical hot-reload environment.

---

## TODO item 2 — Backend Foundation (2026-05-24)

**Ambiguities found**: 9

| Category | Finding | Resolution |
|---|---|---|
| Scope gaps | `psycopg2-binary` listed in pyproject.toml but architecture uses `postgresql+asyncpg://` — wrong driver for async SQLAlchemy | Use `asyncpg` only; remove `psycopg2-binary`; Alembic `env.py` uses `run_sync` pattern over asyncpg |
| Scope gaps | `LOG_LEVEL` and `SCRAPE_INTERVAL_MINUTES` present in `.env.example` but absent from the `config.py` task spec | All app vars added to single `Settings` class in item 2; later items import `settings` without re-touching `Settings` |
| Scope gaps | No `backend/tests/conftest.py` task or async fixture setup (`asyncio_mode`, `async_client`, `db_session`) | `conftest.py` created in item 2; all subsequent items inherit fixtures |
| Scope gaps | `backend/` directory tree and `__init__.py` package files not listed as a task | Explicit scaffold task added covering all sub-packages with `__init__.py` |
| Error & edge-case handling | `GET /health` depth unspecified — always 200 vs. DB probe | Deep probe: executes `SELECT 1`; returns 200 `{"status": "ok"}` or 503 `{"status": "error", "detail": "db unavailable"}` |
| Integration wiring | Alembic `env.py` for async SQLAlchemy requires `run_sync` pattern — not mentioned in task description | `env.py` task explicitly specifies `run_async_engine` + `run_sync` pattern |
| Model/data design | `CORS_ORIGINS` env var absent from Settings task and CLAUDE.md env table | Added to `Settings` class (defaults to `["*"]` when DEBUG, required in prod); `CLAUDE.md` env table updated |
| Documentation | Structlog format (JSON vs. pretty-print) unspecified | DEBUG-aware: `ConsoleRenderer` when `DEBUG=true`, `JSONRenderer` otherwise; configured at module import time |
| Test coverage | Live E2E marked "not required" but user requested all four layers | Live E2E defined: `@pytest.mark.live_api` hits `http://localhost:8000/health` against running `make dev` stack |

**Tasks added**: 3 — directory scaffold with `__init__.py` files; `backend/tests/conftest.py` with async fixtures; `backend/tests/unit/` and `backend/tests/integration/` stubs
**Tasks removed/changed**: 2 — `psycopg2-binary` replaced with `asyncpg` + `aiosqlite` in pyproject.toml; `config.py` task expanded to include all app vars (`CORS_ORIGINS`, `LOG_LEVEL`, `SCRAPE_INTERVAL_MINUTES`) plus `SECRET_KEY` min-length validator
**Documentation changes**: `CLAUDE.md` (update — env table adds `CORS_ORIGINS`, updates `SECRET_KEY` description, clarifies `DEBUG`); `CHANGELOG.md` (update at implementation time — add `### Added` entry)
**Key design constraint**: `asyncpg` is the sole Postgres driver for both the async app and Alembic migrations (via `run_sync` pattern) — no `psycopg2-binary` anywhere in the project.

---

## TODO item 3 — Data Models & Migrations (2026-05-25)

**Ambiguities found**: 12

| Category | Finding | Resolution |
|---|---|---|
| Model/data design | `direction` field on `PriceAlert` storage unspecified | Native Postgres ENUM type (`alert_direction_enum`); `native_enum=True` in SQLAlchemy |
| Model/data design | `source_type` on `Product` — type and valid values unspecified | Native PG ENUM `source_type_enum` with values `generic`, `amazon`, `ebay`, `currys` |
| Model/data design | `channel` and `status` on `NotificationLog` — type and values unspecified | Both native PG ENUMs: `notification_channel_enum` (`email`, `webhook`); `notification_status_enum` (`pending`, `sent`, `failed`) |
| Integration wiring | Native PG ENUM types are incompatible with SQLite in-memory test DB from item 2 | Integration tests switch to Postgres via `testcontainers[postgres]` (`pg_engine` fixture in `conftest.py`); unit tests keep SQLite |
| Model/data design | `price` column type unspecified — `Float` loses precision for monetary values | `NUMERIC(12, 4)` — exact decimal, no floating-point drift |
| Model/data design | `raw_html_hash` algorithm and column length unspecified | SHA-256 hex digest, `VARCHAR(64)`, non-unique index on `raw_html_hash` |
| Scope gaps | No database indexes mentioned despite hot query paths on price history and alert evaluation | Four named indexes added: `ix_price_record_product_captured`, `ix_price_record_html_hash`, `ix_price_alert_product_active`, `ix_notification_log_alert_sent` |
| Scope gaps | Schema file organisation undefined — no Create/Read/Update split mentioned | One file per domain with `Base/Create/Read/Update` variants; `schemas/product.py`, `schemas/price.py`, `schemas/alert.py`, `schemas/notification.py` |
| Error & edge-case handling | Cascade delete policy for `Product` deletion unspecified | Full `cascade="all, delete-orphan"`: Product → PriceRecord + PriceAlert → NotificationLog |
| Model/data design | `updated_at` auto-update mechanism unspecified | ORM-level `onupdate=func.now()` on Column; no DB trigger required |
| Model/data design | `PriceAlert.notified_at` vs `NotificationLog.sent_at` — potential redundancy | Both retained: `notified_at` is a denormalized quick-check flag; `sent_at` is the per-delivery audit timestamp |
| Scope gaps | `Product.url` uniqueness not specified | Unique constraint on `Product.url`; 409 Conflict returned by API on duplicate |

**Tasks added**: 4 — `testcontainers[postgres]` dev dependency; `pg_engine` testcontainer fixture in `conftest.py`; `css_selector` field on `Product` (used by generic scraper in item 4); explicit Alembic migration verification task
**Tasks removed/changed**: 2 — generic "Pydantic v2 schemas mirroring models" replaced with four explicit schema files with named variants; "Generate and apply migration" expanded to specify four PG ENUM types, four tables, four named indexes in one combined revision
**Documentation changes**: `backend/pyproject.toml` (update — add testcontainers dep); `backend/tests/conftest.py` (update — add pg_engine fixture); `backend/alembic/env.py` (update — uncomment model imports stub); `CLAUDE.md` (update — models architecture and test structure sections); `CHANGELOG.md` (update at implementation time)
**Key design constraint**: Native Postgres ENUM types require a split test strategy — unit tests use SQLite in-memory (schema round-trips only), integration tests use a real Postgres testcontainer (`pg_engine` fixture). This `pg_engine` fixture is the canonical test DB for all items from item 3 onwards that touch ENUM columns.

---

## TODO item 4 — Price Scraping Engine (2026-05-25)

**Ambiguities found**: 22

| Category | Finding | Resolution |
|---|---|---|
| Scope gaps | `playwright`, `parsel` missing from `pyproject.toml`; no task to add them | Added as explicit tasks; `celery[redis]` replaced with `celery[redis,asyncio]` |
| Scope gaps | `ScrapedResult` return type of `BaseScraper.fetch()` undefined (no fields, no location) | Rich Pydantic model in `schemas/scraper.py`: `url`, `html`, `html_hash`, `price`, `currency`, `scraped_at`, `extraction_status` |
| Scope gaps | `ScraperError` and `UnknownSourceError` referenced in test strategy but no task to define them | New file `scrapers/exceptions.py` with both classes |
| Scope gaps | `ExtractionStatus` enum undefined — needed by both `ScrapedResult` and `PriceRecord.extraction_status` column | New file `models/enums.py`; values `ok`, `extraction_failed`, `http_error` |
| Model/data design | `css_selector_currency` for currency extraction not in item 3 spec | Item 4 adds Alembic migration: `css_selector_currency VARCHAR NULL` on `products` |
| Model/data design | Item 3 defined `PriceRecord.price` as `NOT NULL` but item 4 must store `price=NULL` for failed scrapes | Item 4 adds migration to make `price` and `currency` nullable; adds `extraction_status` column |
| Model/data design | `SourceType` Python enum values must match the `source_type_enum` PG ENUM from item 3 (`generic`, `amazon`, `ebay`, `currys`) | `SourceType(str, Enum)` in `registry.py` has all four values; only `GENERIC` and `AMAZON` scrapers implemented in item 4 |
| External service calls | Amazon pages are JS-rendered; httpx cannot reliably extract prices | Playwright headless browser (`playwright.async_api`) for `AmazonScraper` |
| External service calls | Playwright is async; Celery workers are sync by default — async/sync boundary | `celery[asyncio]` pool; item 4 documents requirement; item 5 configures `workers/celery_app.py` |
| External service calls | Amazon extraction selector strategy unspecified (CSS selectors change frequently) | `page.evaluate()` JS snippet targeting `ld+json schema.org/Product` or `/Offer`; no CSS fallback — fail cleanly if absent |
| External service calls | Playwright browser lifecycle: per-task vs. singleton per worker | Per-task: open fresh browser context → extract → close; simple isolation at 30-min polling interval |
| Error & edge-case handling | HTTP error handling: raise `ScraperError` vs. encode in return value | `fetch()` never raises for HTTP errors; encodes failure as `ScrapedResult(extraction_status='http_error')` |
| Error & edge-case handling | Which HTTP status codes trigger retry vs. immediate failure | Retry 5xx + 429 + 403 with exponential back-off (1s/2s/4s); 429 honours `Retry-After`; `http_error` after retries exhausted |
| Error & edge-case handling | `price=None` from failed extraction — skip storing or persist? | Always store `PriceRecord` for all outcomes; `extraction_status` encodes the result |
| Error & edge-case handling | Alert evaluation on failed scrape records | Skip evaluation (structlog WARNING) when latest `PriceRecord.extraction_status != 'ok'` |
| Error & edge-case handling | Alert lifecycle after triggering — one-shot, persistent, or cooldown? | Cooldown: 24h hardcoded constant in `alert_service.py`; item 5 promotes to `Settings.ALERT_COOLDOWN_HOURS` |
| Integration wiring | `alert_service.evaluate_alerts()` must dispatch Celery `send_notification` task (item 5) which doesn't exist yet | Stub: `services/notifications.py` — `notify_alert(alert_id) -> None` no-ops; item 5 replaces with `send_notification.delay()` |
| Integration wiring | Celery queue routing for Amazon tasks — item 4 or item 5 owns it? | Item 4 documents requirement (`'playwright'` queue for Amazon tasks); item 5 implements `CELERY_TASK_ROUTES` |
| External service calls | robots.txt compliance — actual `robotparser` parsing or polite delays? | Log-and-proceed: fetch per domain, Redis-cache 1h, warn on disallowed paths, proceed |
| External service calls | Per-domain rate limiting — per-worker (in-memory) or shared (Redis)? | Redis-backed; key `rate_limit:{domain}`, TTL = `SCRAPE_MIN_DELAY_SECONDS` (default 2s, configurable) |
| Architecture & data model | Playwright Docker image strategy — keep backend lean or add Playwright layer? | Separate `celery-playwright` Docker service using `mcr.microsoft.com/playwright/python`; both `docker-compose.yml` and `docker-compose.dev.yml` |
| Test coverage | Live E2E for Amazon unreliable due to bot detection; single `live_api` marker insufficient | Two markers: `@pytest.mark.live_api` for `books.toscrape.com` (generic); `@pytest.mark.live_amazon` for Amazon (separate, documented as flaky) |

**Tasks added**: 15 — `models/enums.py`; `schemas/scraper.py`; `scrapers/exceptions.py`; `services/notifications.py`; `pyproject.toml` deps update; `SCRAPE_MIN_DELAY_SECONDS` config field; `Makefile` playwright install step; `live_amazon` marker registration; `.env.example` update; migration for `css_selector_currency`; migration for `extraction_status` + nullable price; `docker/celery-playwright.Dockerfile`; `docker-compose.yml` service; `docker-compose.dev.yml` override; explicit `celery-playwright` queue routing design note for item 5
**Tasks removed/changed**: 1 — `amazon.py` description updated from "httpx + selective parsing" to "Playwright per-task browser + ld+json JS extraction"
**Documentation changes**: `backend/pyproject.toml` (update); `backend/app/core/config.py` (update); `.env.example` (update); `Makefile` (update); `docker/celery-playwright.Dockerfile` (create); `docker-compose.yml` (update); `docker-compose.dev.yml` (update); `CLAUDE.md` (update); `CHANGELOG.md` (update at implementation time)
**Key design constraint**: `BaseScraper.fetch()` never raises for HTTP errors — all outcomes (success, extraction failure, HTTP error) are encoded in `ScrapedResult.extraction_status`. This uniform return type is the contract that `price_service.record_price()` depends on; violating it breaks the deduplication and alert evaluation flow.

---

## TODO item 5 — Celery Task Infrastructure (2026-05-26)

**Ambiguities found**: 19

| Category | Finding | Resolution |
|---|---|---|
| Scope gaps | `django_celery_beat.schedulers:DatabaseScheduler` in `docker-compose.yml` is a Django-specific package incompatible with FastAPI | Replace with `celery-redbeat` and `--scheduler redbeat.RedBeatScheduler` in both compose files |
| Scope gaps | `celery-redbeat` not listed as a dependency despite dynamic per-product schedule being required | Add `celery-redbeat>=0.13` to `backend/pyproject.toml` runtime deps |
| Scope gaps | `docker-compose.dev.yml` celery-beat runs without `--scheduler` flag (defaults to file-based), inconsistent with production | Add `--scheduler redbeat.RedBeatScheduler` to dev compose celery-beat command |
| Scope gaps | `CELERY_RESULT_BACKEND` present in `.env.example` but absent from `Settings` class in `config.py` | Add `CELERY_RESULT_BACKEND: str` to `Settings`; Celery `result_backend` reads from it |
| Scope gaps | Celery queue routing for Amazon tasks (`'playwright'` queue) documented in item 4 but absent from item 5 task list | Amazon tasks dispatched with `queue='playwright'` at call site in `scrape_product`; `CELERY_TASK_ROUTES` wired in `celery_app.py` |
| Scope gaps | `ALERT_COOLDOWN_HOURS` promotion from hardcoded `24` in `alert_service.py` to `Settings` — item 4 deferred this to item 5, but item 5 had no task for it | Add `ALERT_COOLDOWN_HOURS: int = 24` to `Settings`; `alert_service.py` reads `settings.ALERT_COOLDOWN_HOURS` |
| Scope gaps | `services/notifications.py` stub replacement with `send_notification.delay()` not listed in item 5 tasks | Explicit task added: replace stub body with `send_notification.delay(alert_id)` |
| Scope gaps | Flower monitoring service listed as a task but already wired in `docker-compose.dev.yml` from item 1 | Removed as duplicate; no re-implementation needed |
| Model/data design | `NotificationLog.channel` is NOT NULL but `PriceAlert` has no channel field — `send_notification` cannot determine delivery channel | Add `channel` (`notification_channel_enum`, NOT NULL, default `'email'`) and `webhook_url` (`VARCHAR(512)`, nullable) to `PriceAlert`; Alembic migration in item 5 |
| Model/data design | `AlertCreate`/`AlertRead`/`AlertUpdate` schemas not updated to reflect new `channel` and `webhook_url` fields | `AlertBase` updated with both fields; propagated to all schema variants |
| Model/data design | Notification payload content undefined — `NotificationLog.payload` is JSON but schema not specified | `{"product_id", "product_name", "product_url", "current_price", "threshold_price", "direction"}` — resolved by task from alert + product + latest price record |
| Integration wiring | Celery worker pool unspecified — item 4 introduced `celery[asyncio]` but `celery_app.py` creation in item 5 never named the pool setting | `worker_pool = 'celery.concurrency.aio:TaskPool'` configured in `celery_app.py`; all tasks as native `async def` |
| Integration wiring | DB session access pattern inside async Celery tasks undefined | Each task opens `async with AsyncSessionLocal() as session:` directly — no custom base class |
| Error & edge-case handling | `scrape_product` retry count and backoff unspecified ("N times" in original) | `max_retries=3`, exponential countdown `2 ** task.request.retries` seconds; structlog ERROR on exhaustion |
| Error & edge-case handling | "DLQ logging" vague — actual Redis dead-letter queue or just structured logging? | No Redis DLQ in item 5; "DLQ" means structlog ERROR on max-retries exhaustion; true DLQ deferred |
| Error & edge-case handling | `send_notification` retry policy and failure handling unspecified | `max_retries=3`, `default_retry_delay=5`; on exhaustion set `NotificationLog.status='failed'` and log ERROR |
| Error & edge-case handling | Email delivery undefined — real SMTP or stub | Structlog INFO stub (no SMTP); sets `status='sent'`; SMTP deferred to auth/user item |
| Error & edge-case handling | Webhook delivery undefined — how is the URL resolved and what status codes trigger retry | `httpx.AsyncClient().post(alert.webhook_url, timeout=10.0)`; `status='sent'` on 2xx; `status='failed'` on error; retry on `TimeoutException` |
| Error & edge-case handling | Task time limits unspecified — scrape tasks could hang indefinitely | `task_soft_time_limit=120`, `task_time_limit=150` seconds set globally in `celery_app.py` |

**Tasks added**: 9 — `celery-redbeat` dep; `CELERY_RESULT_BACKEND` + `ALERT_COOLDOWN_HOURS` in `Settings`; `.env.example` update; `alert_service.py` cooldown from Settings; `PriceAlert.channel` + `webhook_url` fields + migration; `AlertBase` schema update; `notifications.py` stub replacement; `make worker` + `make beat` Makefile targets; docker-compose celery-beat command fix (both files)
**Tasks removed/changed**: 2 — "Implement Flower monitoring service" removed (already done in item 1); "Wire celery-worker and celery-beat Docker services" narrowed to fixing the `django_celery_beat` scheduler reference; `schedule.py` respecified from static `beat_schedule` dict to `register_product_schedule` / `deregister_product_schedule` / `startup_sync_schedules` helpers
**Documentation changes**: `backend/pyproject.toml` (update); `backend/app/core/config.py` (update); `.env.example` (update); `backend/app/models/alert.py` (update); `backend/app/schemas/alert.py` (update); `backend/alembic/versions/` (new migration file); `backend/app/services/alert_service.py` (update); `backend/app/services/notifications.py` (update); `docker-compose.yml` (update); `docker-compose.dev.yml` (update); `Makefile` (update); `CLAUDE.md` (update); `CHANGELOG.md` (update at implementation time)
**Key design constraint**: `celery-redbeat` is the beat scheduler — `django_celery_beat` (already in `docker-compose.yml`) must be removed entirely. Per-product schedules are stored in Redis as `RedBeatSchedulerEntry` objects; the `startup_sync_schedules()` worker-ready signal handler bootstraps entries for all active products on first start, so no product is silently unscheduled after a Redis flush.

### Amendment — WhatsApp notification channel (2026-05-26)

Added WhatsApp as a third notification channel alongside email and webhook. Provider selection deferred to a spike rather than committing to Twilio.

**Changes to TODO item 5**:

| Area | Change |
|---|---|
| `notification_channel_enum` (item 3 schema) | Extended via `ALTER TYPE notification_channel_enum ADD VALUE 'whatsapp'` in the item 5 migration; must be emitted manually before `op.add_column()` calls as Alembic autogenerate does not detect ENUM value additions |
| `NotificationChannel` Python enum | `whatsapp = 'whatsapp'` added to `backend/app/models/notification_log.py` |
| `PriceAlert` model | `whatsapp_number VARCHAR(20) NULL` (E.164 format) added alongside `channel` and `webhook_url` |
| `AlertBase` schema | `whatsapp_number: str \| None = None` added; propagated to Create/Read/Update variants |
| Alembic migration renamed | `add_alert_channel_whatsapp` — covers `ALTER TYPE` extension + three new `price_alert` columns |
| WhatsApp provider | **Not decided in item 5.** Spike sub-task added: evaluate Meta Cloud API (direct), Twilio, Vonage, MessageBird/Bird on pricing, Python SDK maturity, sandbox availability, rate limits; produce ADR at `docs/decisions/whatsapp-provider.md` |
| `send_notification` task | WhatsApp branch: structlog WARNING stub + `status='sent'`; no provider SDK; real delivery implemented in follow-on item after ADR approval |
| Tests added | Unit: WhatsApp stub → WARNING event emitted, `status='sent'`, no external call; Integration: WhatsApp channel → `NotificationLog.status='sent'`; Negative: `whatsapp_number=None` → `status='failed'` |
| `docs/decisions/whatsapp-provider.md` | New ADR document created as output of the spike |

---

## TODO item 6 — REST API Endpoints (2026-05-26)

**Ambiguities found**: 13

| Category | Finding | Resolution |
|---|---|---|
| Scope gap | `POST /products/{id}/scrape` returned no response schema and the async/sync mode was unspecified | 202 Accepted; `ScrapeJobResponse` in `schemas/common.py` with `task_id`, `status: "queued"`, `product: ProductRead` |
| Model/data design | Pagination response shape was unspecified (`limit`/`offset` mentioned but no envelope) | Typed `PaginatedResponse[T]` in `schemas/common.py` with `items`, `total`, `limit`, `offset`; `limit` max 100 |
| Scope gap | `GET /alerts` had no filter param despite `product_id` FK on every alert | Added optional `?product_id=X` query param |
| Scope gap | `GET /products` and `GET /alerts` had no active-status filter | Added optional `?is_active=true/false` to both list endpoints; returns all records by default |
| Test coverage | `async_client` fixture uses SQLite; native Postgres ENUMs from item 3 are incompatible with SQLite | New `pg_async_client` fixture (Postgres testcontainer) added to `conftest.py`; route integration tests use `pg_async_client` |
| Test coverage | Live E2E layer marked "not required" despite all-four-layer requirement | Full CRUD smoke `@pytest.mark.live_api`: POST product → GET → PATCH → DELETE; POST alert → GET /alerts?product_id=X |
| Scope gap | No HTTP success codes specified for POST and DELETE | 201 Created for POST; 204 No Content for DELETE; 200 for GET and PATCH |
| Error & edge-case handling | `PATCH /products/{id}` with a conflicting URL and `AlertUpdate.product_id` both unaddressed | 409 on duplicate URL in POST/PATCH products; `product_id` removed from `AlertUpdate`; PATCH /alerts returns 422 if `product_id` supplied |
| Scope gap | `GET /products/{id}/prices` had no date-range filtering | Added optional `?from_dt` / `?to_dt` ISO 8601 params |
| Integration wiring | `main.py` router mount was commented out with no task to activate it | Explicit task to uncomment the stub at lines 109–111 |
| Scope gap | Celery task dependency: `scrape_product` from item 5 is not yet implemented | `tasks/scrape.py` stub created in item 6 (raises `NotImplementedError`); item 5 replaces with Celery task |
| Documentation | `openapi.json` generation command/tooling was unspecified | `make generate-openapi` Makefile target using `app.openapi()` directly |
| Scope gap | Default sort order for all list endpoints was unspecified | Products: `created_at DESC`; prices: `captured_at DESC`; alerts: `id ASC` |

**Tasks added**:
- `backend/app/schemas/common.py` — create `PaginatedResponse[T]` and `ScrapeJobResponse`
- `backend/app/tasks/scrape.py` — create `scrape_product` stub
- `pg_async_client` fixture in `backend/tests/conftest.py`
- `make generate-openapi` Makefile target
- Explicit task to uncomment router mount in `main.py`

**Tasks removed/changed**:
- Original bare `GET /products/{id}/prices` task expanded with `from_dt`/`to_dt` params
- `POST /products/{id}/scrape` changed from unspecified to async 202 with `ScrapeJobResponse`
- `AlertUpdate.product_id` field removed from schema
- Pagination task expanded from a note to a concrete schema task

**Documentation changes**:
- `backend/app/schemas/common.py` (create)
- `backend/app/schemas/alert.py` (update — remove `product_id` from `AlertUpdate`)
- `backend/app/tasks/scrape.py` (create — stub)
- `backend/app/api/v1/products.py`, `prices.py`, `alerts.py`, `router.py` (create)
- `backend/app/main.py` (update — uncomment router mount)
- `backend/tests/conftest.py` (update — add `pg_async_client`)
- `Makefile` (update — add `generate-openapi`)
- `backend/openapi.json` (create — generated snapshot)
- `CLAUDE.md` (update — commands table, API layer architecture)
- `CHANGELOG.md` (update at implementation time)

**Key design constraint**: Route integration tests must use the Postgres testcontainer (`pg_async_client`) rather than SQLite because item 3 native ENUMs are DB-dialect-specific; this means every API-layer integration test spins the testcontainer and the test suite must not assume SQLite compatibility.

---

## TODO item 7 — Frontend React Application (2026-05-26)

**Ambiguities found**: 26

| Category | Finding | Resolution |
|---|---|---|
| Scope gap | `react-router-dom` v6 already installed in `package.json` but no routing setup tasks (`App.tsx`, `BrowserRouter`, `Routes`, route definitions) | Explicit tasks added for `App.tsx`, routing structure (`/`, `/products/:id`, `/products/:id/alerts`), and `main.tsx` rewrite |
| Scope gap | No `QueryClientProvider` / `App.tsx` entrypoint task | `App.tsx` with `QueryClientProvider` + `BrowserRouter` + `ErrorBoundary` + `<Routes>` added as explicit task |
| Scope gap | `tailwindcss`, `postcss`, `autoprefixer` not in `package.json`; no task to add them | Added to runtime deps task; `npx shadcn-ui@latest init` scaffolds `tailwind.config.ts` and `globals.css` |
| Scope gap | shadcn/ui not mentioned; no `@radix-ui/*`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `tailwindcss-animate` deps | User selected shadcn/ui as component library; all deps added to package.json task |
| Scope gap | No path alias config (`@/*` → `./src/*`) in `tsconfig.app.json` or `vite.config.ts` — required by shadcn/ui | Explicit tasks for both tsconfig and vite.config path alias updates |
| Scope gap | `src/globals.css` (CSS variable tokens) and `src/lib/utils.ts` (`cn()` helper) not listed — shadcn/ui prerequisites | Explicit tasks added; generated via `npx shadcn-ui@latest init` and committed |
| Scope gap | TypeScript API types management unspecified (types must mirror backend Pydantic schemas) | `openapi-typescript` added as devDep; `make generate-types` target added; placeholder hand-written `src/api/types.ts` for item 7 development |
| Scope gap | No MSW handler location specified (v2 requires handlers.ts + server.ts) | `tests/mocks/handlers.ts` + `tests/mocks/server.ts`; imported in `tests/setup.ts` |
| Scope gap | No `ErrorBoundary` component task (mentioned in test strategy but not in implementation) | `src/components/ErrorBoundary.tsx` class component added; wraps `<Routes>` in `App.tsx` |
| Scope gap | No shared Layout / top nav component | `src/components/Layout.tsx` with top nav + theme toggle added |
| Scope gap | Date range filter UI for PriceChart unspecified | shadcn/ui Popover + Calendar (react-day-picker `mode="range"`) + `date-fns`; `react-day-picker` and `date-fns` added as deps |
| Scope gap | `POST /products/{id}/scrape` trigger UI not mentioned | "Scrape Now" button on `ProductDetail` header; `useScrape.ts` hook; `sonner` toast on 202 |
| Scope gap | Loading state components not listed | shadcn/ui `Skeleton` rows in Dashboard; skeleton chart area in ProductDetail |
| Scope gap | Pagination UI unspecified (API returns `PaginatedResponse`) | Infinite scroll via `useInfiniteQuery` + `react-intersection-observer` `useInView` sentinel div |
| Scope gap | Alert form conditional channel fields not mentioned (`webhook_url`, `whatsapp_number` from item 5) | `AlertFormDialog` renders `webhook_url` only when `channel=webhook`; `whatsapp_number` only when `channel=whatsapp`; zod `superRefine` makes conditional fields required |
| Scope gap | Form validation library unspecified | `react-hook-form` + `zod` + `@hookform/resolvers` added as deps |
| Scope gap | `src/main.tsx` is a placeholder; no rewrite task | Explicit task to rewrite `main.tsx` with `QueryClientProvider`, `BrowserRouter`, `<Toaster />` |
| Scope gap | Product management actions (edit/delete/deactivate) UI location not specified | Kebab DropdownMenu on Dashboard rows — Edit modal, Activate/Deactivate PATCH, Delete confirmation dialog |
| Test coverage | Live E2E marked "not required" but all four layers requested | Playwright (`@playwright/test`) smoke test in `frontend/tests/e2e/`; `make test-e2e` target; `npx playwright install chromium` in `make install` |
| Test coverage | Zustand store unit tests not listed | Unit tests for `setColorScheme`, `setSelectedProductId`, `setActiveProductFilter` mutations added to test strategy |
| Test coverage | MSW handlers for specific API endpoints not listed | Explicit MSW handler task covering all 11 API endpoints (products CRUD + prices + scrape + alerts CRUD) |
| Architecture | Zustand store scope undefined (server state vs UI state boundary) | Zustand: `selectedProductId`, `colorScheme`, `activeProductFilter`, `activeAlertFilter` only; all server state in react-query |
| Architecture | Dark mode implementation unspecified (`prefers-color-scheme` CSS vs Tailwind class) | Tailwind `darkMode: 'class'`; Zustand `colorScheme` drives `document.documentElement.classList`; system default reads `matchMedia` on init |
| Architecture | Toast library unspecified | `sonner` added as runtime dep; `<Toaster />` in `App.tsx` |
| Architecture | Price formatting utility unspecified | `src/lib/formatPrice.ts` — `Intl.NumberFormat('en-GB', { style: 'currency', currency })` |
| Architecture | AlertManager routing and access path unspecified | `/products/:id/alerts` sub-route; pre-filters `GET /alerts?product_id=:id`; "Manage alerts" button from ProductDetail |

**Tasks added**: 33 detailed tasks replacing the original 10 high-level stubs — package/tooling setup (9), types and API client (2), app shell and routing (4), Zustand store (1), utility functions (1), hooks (4), pages (3), components (5), MSW infrastructure (3), Playwright E2E (1)
**Tasks removed/changed**: All 10 original tasks replaced — "Initialise frontend/" expanded into 9 tooling tasks; each page/hook/component task expanded with explicit layout, interaction, and implementation spec; "Add polling" absorbed into `usePrices.ts` task; "Implement responsive layout with Tailwind" replaced with explicit dark mode + Layout component task
**Documentation changes**: `frontend/package.json` (update); `frontend/playwright.config.ts` (create); `frontend/tailwind.config.ts` (create); `frontend/src/globals.css` (create); `frontend/src/lib/utils.ts` (create); `frontend/src/lib/formatPrice.ts` (create); `frontend/src/api/types.ts` (create); `frontend/src/api/client.ts` (create); `frontend/src/main.tsx` (update); `frontend/src/App.tsx` (create); `frontend/src/store/uiStore.ts` (create); `frontend/src/components/` × 5 (create); `frontend/src/pages/` × 3 (create); `frontend/src/hooks/` × 4 (create); `frontend/tests/mocks/` × 2 (create); `frontend/tests/setup.ts` (update); `frontend/tests/e2e/smoke.spec.ts` (create); `Makefile` (update — `test-e2e` + playwright install); `CLAUDE.md` (update); `CHANGELOG.md` (update at implementation time)
**Key design constraint**: The frontend is built entirely on shadcn/ui (Radix + Tailwind); this requires `tailwindcss`, `postcss`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, and the shadcn/ui CLI init step before any component can render. All these prerequisites must be complete before any page or component task begins.

---

## TODO item 8 — Docker Containerisation (2026-05-26)

**Ambiguities found**: 13

| Category | Finding | Resolution |
|---|---|---|
| Scope gaps | Item 8 had no `### Design decisions` or `### Documentation` sub-sections — bare task list and two-line test strategy | Both sections added; all 13 ambiguities embedded as resolved decisions |
| Error & edge-case handling | `backend.Dockerfile` production stage uses `HEALTHCHECK CMD curl -f ...` but `python:3.12-slim` does not include `curl` — healthcheck silently fails | Add `apt-get install -y --no-install-recommends curl` in production stage |
| Scope gaps | `backend.Dockerfile` builder stage copies only `backend/pyproject.toml`, not root `pyproject.toml` or `uv.lock` — `uv sync` installs unpinned latest deps instead of locked versions | Fix COPY sequence to include root workspace files; add `--frozen` flag to `uv sync` |
| Integration wiring | Item 5 decided `asyncio` pool for all Celery workers; scaffold `docker-compose.yml` uses `--concurrency=4` (pre-fork) for `celery-worker` and `celery-playwright.Dockerfile` uses `--pool=gevent` | Both corrected to `--pool=asyncio` in compose and Dockerfile |
| Model/data design | `docker-compose.yml` uses `postgres:15-alpine`; integration tests target `postgres:16` (session log confirms pg16 was used during integration test fixes) | Upgrade compose to `postgres:16-alpine` for dialect consistency |
| Error & edge-case handling | Production compose does not set `CORS_ORIGINS`; `Settings` raises `ValueError` when `DEBUG=false` and env var is absent — `make up` on fresh `.env` fails at FastAPI startup | Add `CORS_ORIGINS=http://localhost` to `.env.example` with inline production warning comment |
| Scope gaps | Resource limits listed in task description but no values or services specified | Concrete `deploy.resources.limits` per all 7 services (backend 512m/0.5CPU, celery-playwright 1g/1CPU for Chromium, etc.) |
| Test coverage | Unit layer marked N/A; user requested all four test layers | Unit layer defined: `make lint-docker` (hadolint) + `make validate-nginx` (nginx -t via Docker) |
| Test coverage | Integration smoke vague ("GET /health returns 200"); no scripted form | `make smoke` target added: compose up → poll /health (5 s × 12) → /nginx-health → frontend → compose down |
| Test coverage | No CI gate for compose wiring regressions | New `smoke` job in `ci.yml` that depends on `build` job; fails PR on startup timeout |
| Scope gaps | No image scanning task | `make scan` target using `aquasec/trivy` Docker image; fails on CRITICAL CVEs; runs in CI after `build` |
| Scope gaps | No Nginx security headers | `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `X-XSS-Protection` added to `nginx.conf` |
| Scope gaps | `celery-playwright` CMD path (WORKDIR + module path) untested after pool and base image changes | Explicit verification task: `docker compose run --rm celery-playwright celery ... inspect ping` |

**Tasks added**: 14 — `backend.Dockerfile` builder COPY fix; `backend.Dockerfile` curl install; `celery-playwright.Dockerfile` pool fix; `celery-worker` compose command fix; `celery-playwright` compose command fix; postgres version upgrade; `deploy.resources.limits` for all 7 services; nginx security headers; `CORS_ORIGINS` in `.env.example`; `make lint-docker`; `make validate-nginx`; `make scan`; `make smoke`; CI `smoke` job
**Tasks removed/changed**: 1 — "Verify `make up` brings the full stack to healthy state within 60 seconds" replaced by the scripted `make smoke` target and CI `smoke` job
**Documentation changes**: `docker/backend.Dockerfile` (update — builder COPY + curl); `docker/celery-playwright.Dockerfile` (update — pool flag); `docker/nginx.conf` (update — security headers); `docker-compose.yml` (update — pool fix, postgres 16, resource limits); `.env.example` (update — CORS_ORIGINS); `Makefile` (update — 4 new targets); `.github/workflows/ci.yml` (update — smoke job); `CLAUDE.md` (update — commands table + env table + architecture); `CHANGELOG.md` (update at implementation time)
**Key design constraint**: `backend.Dockerfile` must copy the root `pyproject.toml` and `uv.lock` into the builder stage and use `uv sync --frozen --no-dev` — without the lockfile, Docker builds install unpinned dependency versions and diverge from the development environment silently. This is the most structurally significant correctness fix in item 8.

---

## TODO item 9 — Claude Code Agents (2026-05-26)

**Ambiguities found**: 13

| Category | Finding | Resolution |
|---|---|---|
| Scope gaps | All eight agent files already exist on disk from prior sessions; TODO.md still listed them as "copy and adapt" — creating a false impression of zero progress | Tasks reframed from "copy/create" to "verify content against spec + fix divergences"; definition of done requires `make lint-agents` to pass |
| Scope gaps | `docs/architecture/repository-architecture.md` marked as stub with C1+C2 only; module-grouping agent references a `## Module domain-grouping convention` section that does not exist | Task expanded: full C3 backend component view + module convention section + ER diagram + ADR index table |
| Scope gaps | `.github/skills/profiling/findings.md` does not exist; both profiling agents reference it as their append target | New task: create stub with standard header pattern before first profiling run |
| Scope gaps | No log directory scaffolding task; `make lint-agents` checks ALL referenced paths including runtime log dirs (`logs/profiling/`, `logs/quality/`) | New `make init-logs` target creates full tree with `.gitkeep` files; called from `make install`; `.gitignore` updated |
| Scope gaps | No agent frontmatter validation or referenced-path lint task | New `make lint-agents` target: frontmatter completeness + ALL path references (static + runtime); runs in CI `agent-quality` job |
| Model/data design | `docs/architecture/repository-architecture.md` stub has `Postgres 15` hardcoded; Item 8 upgraded to Postgres 16 | Fix in Item 9 (item owns the doc); C2 table corrected to `postgres:16-alpine` |
| Scope gaps | No data model section in architecture doc; contributors need table relationship orientation | ASCII ER diagram (four tables + FK arrows + key fields) added to `repository-architecture.md` |
| Scope gaps | No ADR index in architecture doc; `docs/decisions/whatsapp-provider.md` exists but is not discoverable | `## Architecture Decision Records` markdown table appended to `repository-architecture.md`; one row per ADR in `docs/decisions/` |
| Integration wiring | `.claude/agents/architecture-maintainer.md` references `tests/` generically while `.github` version explicitly lists `backend/tests/` + `frontend/tests/` — unintended divergence | Sync task added: manual diff per agent pair; fix `.claude` version to match; document intentional divergences with inline comments |
| Test coverage | Test strategy was "manually invoke and check output shape" (integration only); user requested lint/schema checks | Integration: `make lint-agents` exits 0; Negative: missing frontmatter field / broken path / missing log dir each cause exit 1; Live E2E: manual output shape check retained |
| Documentation | No `CHANGELOG.md` entry task for Item 9 | Task added: `### Added` entry covering all SDLC agents, arch doc, lint target, log scaffolding |
| Definition of done | Vague ("manually invoke") — no objective acceptance criterion | Done = all verification tasks complete + `make lint-agents` exits 0 |
| Scope gaps | No CI job for agent lint — user requested Makefile + CI | New `agent-quality` CI job (separate from existing `lint` job); runs `make lint-agents` on every PR and push to main |

**Tasks added**: 9 — complete `repository-architecture.md` (C3+module convention+ER+ADR index); fix Postgres version in C2; create `.github/skills/profiling/findings.md` stub; `make init-logs` target; `make install` update to call `init-logs`; `.gitignore` update; `make lint-agents` target; `agent-quality` CI job; CHANGELOG entry
**Tasks removed/changed**: 9 — all original "copy/create" tasks converted to "verify content and fix divergences" tasks (files already exist); agent pair sync task added
**Documentation changes**: `docs/architecture/repository-architecture.md` (rewrite — full C4); `.github/skills/profiling/findings.md` (create — stub); `Makefile` (update — 2 new targets + install update); `.github/workflows/ci.yml` (update — agent-quality job); `.gitignore` (update — logs exclusion); `CLAUDE.md` (update — commands table); `CHANGELOG.md` (update at implementation time)
**Key design constraint**: `make lint-agents` checks ALL referenced paths including runtime log dirs — log directories must be pre-created by `make init-logs` (called from `make install`) before the lint can pass. This install-order dependency must be documented in `CLAUDE.md` and enforced in the CI job via the install step.

---

## TODO item 10 — CI/CD & Quality Gates (2026-05-26)

**Ambiguities found**: 10

| Category | Finding | Resolution |
|---|---|---|
| Scope gaps | Four of the seven item 10 tasks were already complete from earlier items: `lint`/`test-backend`/`test-frontend`/`build` CI jobs (item 1), `.pre-commit-config.yaml` (item 1), `config/quality-thresholds.toml` (already present), `make lint`/`make format` (already present), and vitest 80% coverage threshold (already in `vite.config.ts`) | Tasks marked `[x]` and removed from the active list; item 10 scoped to what is genuinely missing |
| Scope gaps | `smoke`, `scan`, and `agent-quality` CI jobs mentioned in items 8 and 9 were not yet in `ci.yml` but are NOT item 10's responsibility — they are item 8 and 9 tasks | Documented as cross-item scope note at top of item 10; item 10 does not add those jobs |
| Error & edge-case handling | `make quality` used `\|\| true` guards throughout — collects reports but never fails; `config/quality-thresholds.toml` was never actually read or enforced | New `backend/scripts/check_quality.py` parses thresholds.toml, computes P95 CC, P5 MI, P95 Halstead from radon JSON, reads coverage.xml; `make quality` calls it as final step; `|| true` guards removed |
| Scope gaps | No `--cov-fail-under=90` in pytest `addopts` — backend coverage could drop below 90% without any test run failing | `--cov-fail-under=90` added to `addopts` in `backend/pyproject.toml`; belt-and-suspenders alongside `check_quality.py` |
| Scope gaps | No `security` CI job — `pip-audit` and `npm audit` mentioned in the original task list but no job existed in `ci.yml` | New `security` job added (parallel, no `needs:` dependency): `pip-audit --fail-on CRITICAL` + `npm audit --audit-level=critical` |
| Scope gaps | `pip-audit` not in `backend/pyproject.toml` dev deps; would require ad-hoc `pip install` in CI | Added to `[dependency-groups] dev`; installed via `uv sync --group dev` in both local and CI contexts |
| Documentation | Coverage upload configured to Codecov (requires external account + secret) | Replaced with GitHub Actions `$GITHUB_STEP_SUMMARY` markdown table: backend % vs ≥90% and frontend % vs ≥80%, each with ✅/❌ indicator; posted by `check_quality.py` when `GITHUB_ACTIONS=true` |
| Integration wiring | CI `test-backend` job used `postgres:15-alpine`; item 8 upgraded `docker-compose.yml` to postgres:16-alpine; testcontainers also runs postgres:16 | `test-backend` CI job updated to `postgres:16-alpine`; item 10 owns `ci.yml` holistically |
| Test coverage | Original test strategy had only 2 of 4 required layers; unit and integration listed but no negative layer and live E2E not addressed | All four layers added: unit (check_quality.py threshold logic + P95/P5 calculations), integration (make quality exits 0 on clean codebase; --cov-fail-under enforcement), negative (missing TOML, malformed TOML, missing logs/, missing coverage.xml), live E2E (not required — infra-only item) |
| Scope gaps | Branch protection documented as a task but no guidance on required checks or how to configure it | `CONTRIBUTING.md` gets a `## Repository Settings` section listing all required status checks and the exact GitHub UI path to enable the rule |

**Tasks added**: 7 — `backend/scripts/` directory; `backend/scripts/check_quality.py`; `--cov-fail-under=90` in pytest addopts; `make quality` enforcement update; `pip-audit` dev dep; `security` CI job; `test-backend` postgres version fix
**Tasks removed/changed**: 5 — "Configure coverage upload to Codecov" replaced by GitHub Step Summary; "Add `.pre-commit-config.yaml`" marked complete (item 1 created it); "config/quality-thresholds.toml" marked complete; "Add `make lint` and `make format`" marked complete; "Wire CI jobs" narrowed to only the genuinely missing `security` job
**Documentation changes**: `backend/pyproject.toml` (update — pip-audit dep + --cov-fail-under); `backend/scripts/check_quality.py` (create); `Makefile` (update — quality target body); `.github/workflows/ci.yml` (update — security job + postgres 16); `CONTRIBUTING.md` (update — branch protection section); `CLAUDE.md` (update — quality command description + thresholds section); `CHANGELOG.md` (update at implementation time)
**Key design constraint**: `make quality` is now both a reporter and an enforcer — it exits 1 on any threshold breach. `backend/scripts/check_quality.py` is the single source of truth for threshold logic; it reads `config/quality-thresholds.toml` directly so adding or changing thresholds never requires editing the Makefile or CI workflow.

---

## TODO item 11 — Test Suite Health & Coverage Deduplication (2026-05-30)

**Ambiguities found**: 5

| Category | Finding | Resolution |
|---|---|---|
| Scope gaps | Top-level `scripts/` directory (for `.sh` and `.js` overlap scripts) not created by any item — neither Item 10 nor Item 11 had a creation task | Added task: "Create `scripts/` directory at repo root" to Item 11 Setup section |
| Error & edge-case handling | Scripts always exited 0 (informational) but user wanted enforcement promoted to a hard gate in the same sprint as Item 11 — no enforcement tasks existed | Added Baseline and enforcement task sub-section: set `max_intra_tier_duplicate_lines_*` in `[test-health]` after baseline run; scripts exit 1 when count exceeds threshold; exit 0 with info when field absent |
| Error & edge-case handling | No behaviour specified for the pre-baseline case (threshold field not yet present in TOML — first run before baseline task completes) | Exit 0 with "No enforcement threshold set — run baseline task first"; enforcement is additive once the field is present |
| Scope gaps | Shell script used `../../logs/quality/...` as the coverage reports directory, but if the script `cd`s into `frontend/` to invoke vitest, `../../` resolves one level above the repo root | Fixed to `../logs/quality/...` (one level up from `frontend/` = repo root); noted explicitly in the Frontend script working directory design decision |
| Test coverage | Test strategy marked live E2E as "Not required" but user selected all four test layers | Promoted acceptance criterion to a named live E2E task: "Run `make quality` on a clean checkout after Item 10 is complete; assert both overlap scripts exit 0 and print a summary line to stdout" |

**Tasks added**: 5 — `scripts/` directory creation; enforcement threshold reading in `check_coverage_overlap.py`; enforcement threshold reading in `check_coverage_overlap_frontend.js`; "Set enforcement thresholds" baseline task; "Verify `make quality` exits cleanly with enforcement thresholds set" task
**Tasks removed/changed**: 2 — "Exit 0 always" removed from both script task descriptions and replaced with conditional enforcement logic; `../../` path corrected to `../` in the shell script task
**Documentation changes**: `scripts/` directory (create); `backend/scripts/check_coverage_overlap.py` (create — now includes enforcement logic); `scripts/check_coverage_overlap_frontend.sh` (create — path and working-directory clarified); `scripts/check_coverage_overlap_frontend.js` (create — now includes enforcement logic); `config/quality-thresholds.toml` (update — `[test-health]` section now includes enforcement thresholds, not just baseline counts); `CLAUDE.md` (update — quality thresholds section references `[test-health]` enforcement); `CHANGELOG.md` (update at implementation time)
**Key design constraint**: Enforcement gates are installed in the same sprint as the detection scripts, not deferred. Both overlap scripts exit 0 until `max_intra_tier_duplicate_lines_*` fields appear in `[test-health]` — the threshold absence is the "informational" state, not a permanent design. Once the baseline run populates the thresholds, CI blocks on net new duplicates.
