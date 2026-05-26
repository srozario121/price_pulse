# Changelog

All notable changes to Price Pulse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
