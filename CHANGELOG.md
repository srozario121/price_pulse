# Changelog

All notable changes to Price Pulse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
