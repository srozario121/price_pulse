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
