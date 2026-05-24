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
