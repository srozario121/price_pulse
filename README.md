# Price Pulse 📈

A retail product price monitoring platform. Add product URLs; Price Pulse scrapes prices on a schedule and alerts you when the price drops.

## Features

- Track products from any retail site (generic CSS-selector) or Amazon
- Configurable price alerts (above / below threshold)
- Price history charts with date-range filtering
- Background scraping via Celery Beat (default: every 30 minutes)
- REST API (`/api/v1`) with OpenAPI docs
- React SPA with real-time polling

## Architecture

```
price_pulse/
├── backend/          # FastAPI app + Celery workers (Python, uv)
├── frontend/         # React + Vite SPA (TypeScript)
├── docker/           # Multi-stage Dockerfiles + Nginx config
├── docs/architecture/  # C4 architecture documentation
├── config/           # Quality thresholds (TOML)
└── .claude/agents/   # Claude Code SDLC agents
```

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| [Docker](https://docs.docker.com/get-docker/) | ≥ 24 | Dev + production stack |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | ≥ 0.4 | Python package manager |
| [Node.js](https://nodejs.org/) | ≥ 20 | Frontend + commitlint |
| [Git](https://git-scm.com/) | ≥ 2.39 | Version control |

## Quick Start

```bash
# 1. Clone and copy environment config
git clone <repo-url> price_pulse
cd price_pulse
cp .env.example .env   # edit values as needed

# 2. Install all dependencies and wire pre-commit hooks
make install

# 3. Start the full dev stack (hot-reload, Flower :5555, pgAdmin :5050)
make dev
```

The API will be available at `http://localhost:8000` and the UI at `http://localhost:80`.

## Make Target Reference

| Target | Description |
|--------|-------------|
| `make install` | Install all deps (uv sync + npm install) and wire pre-commit hooks |
| `make dev` | Start dev stack with Docker Compose (hot-reload) |
| `make up` | Start production-like stack (detached) |
| `make down` | Stop and remove containers |
| `make logs` | Tail all logs (`make logs SERVICE=backend` for one service) |
| `make build` | Build Docker images (`make build SERVICE=backend` for one) |
| `make test` | Run backend (pytest) + frontend (vitest) tests |
| `make test-backend` | Run backend pytest suite only |
| `make test-frontend` | Run frontend vitest suite only |
| `make lint` | Lint backend (ruff) + frontend (eslint) |
| `make format` | Format backend (ruff format) + frontend (prettier) |
| `make quality` | Run full quality report (radon + vitest coverage) |
| `make migrate` | Apply Alembic migrations (`make migrate MSG="add_x"` to generate) |
| `make shell-backend` | Open bash inside the running backend container |
| `make shell-db` | Open psql inside the running postgres container |
| `make worker` | Start Celery worker locally (no Docker) |
| `make beat` | Start Celery Beat scheduler locally (no Docker) |
| `make structure` | Show backend package tree with module counts |

## Development Workflow

1. Create a feature branch: `git checkout -b feat/my-feature`
2. Make changes with tests
3. Run `make lint` and `make test` before committing
4. Commit with [Conventional Commits](https://www.conventionalcommits.org/): `feat(api): add price history endpoint`
5. Push and open a PR — CI must be green before merging

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow.

## Environment Variables

Copy `.env.example` to `.env`. Key variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async Postgres connection |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker + result backend |
| `CELERY_BROKER_URL` | same as `REDIS_URL` | Explicit broker override |
| `SECRET_KEY` | *(required)* | FastAPI security signing |
| `DEBUG` | `false` | FastAPI debug mode |
| `SCRAPE_INTERVAL_MINUTES` | `30` | Default Celery Beat interval |
| `LOG_LEVEL` | `INFO` | structlog log level |
| `VITE_API_URL` | `http://localhost:8000` | Frontend API base URL (build-time) |

## Quality Thresholds

Defined in `config/quality-thresholds.toml`:

- Backend test coverage: ≥ 90%
- Frontend test coverage: ≥ 80%
- Cyclomatic complexity P95: < 7
- Maintainability Index P5: > 10

Run `make quality` to check all gates.

## Licence

[MIT](LICENSE)
