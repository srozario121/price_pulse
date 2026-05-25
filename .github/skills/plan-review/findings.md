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
