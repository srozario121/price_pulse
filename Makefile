# =============================================================================
# Price Pulse — Makefile
# =============================================================================
# Usage: make <target>
# Pass SERVICE=<name> to scope docker targets to one service, e.g.:
#   make logs SERVICE=backend
#   make build SERVICE=frontend

.DEFAULT_GOAL := help

# Optional service filter for docker-compose targets
SERVICE ?=

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
BOLD  := \033[1m
RESET := \033[0m
GREEN := \033[32m
CYAN  := \033[36m

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
.PHONY: help
help:           ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\n$(BOLD)Price Pulse — available targets$(RESET)\n\n"} \
	  /^[a-zA-Z_-]+:.*##/ { printf "  $(CYAN)%-22s$(RESET) %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------
.PHONY: install
install:        ## Install all deps: uv sync (workspace) + npm install + pre-commit hooks
	uv sync
	cd backend && uv run playwright install chromium
	cd frontend && npm install
	cd frontend && npx playwright install chromium
	cd / && npm install --prefix $(CURDIR)
	pre-commit install --hook-type commit-msg --hook-type pre-commit
	$(MAKE) init-logs

# ---------------------------------------------------------------------------
# Log directory scaffolding
# ---------------------------------------------------------------------------
.PHONY: init-logs
init-logs:      ## Create log directory tree with .gitkeep stubs (idempotent)
	mkdir -p logs/quality logs/profiling/backend logs/profiling/tasks logs/profiling/frontend logs/profiling/test-timing
	touch logs/quality/.gitkeep logs/profiling/backend/.gitkeep logs/profiling/tasks/.gitkeep logs/profiling/frontend/.gitkeep logs/profiling/test-timing/.gitkeep

# ---------------------------------------------------------------------------
# Development stack (Docker Compose with hot-reload)
# ---------------------------------------------------------------------------
.PHONY: dev
dev:            ## Start full dev stack with hot-reload (Flower :5555, pgAdmin :5050)
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# ---------------------------------------------------------------------------
# Production-like stack
# ---------------------------------------------------------------------------
.PHONY: up
up:             ## Start production-like stack (detached)
	docker compose up -d $(SERVICE)

.PHONY: down
down:           ## Stop and remove containers and prune dangling images (preserves volumes)
	docker compose down $(SERVICE)
	docker image prune -f

.PHONY: logs
logs:           ## Tail logs; pass SERVICE=<name> to filter, e.g. make logs SERVICE=backend
	docker compose logs --follow $(SERVICE)

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
.PHONY: build
build:          ## Build Docker images; pass SERVICE=<name> to build one, e.g. make build SERVICE=backend
	docker compose build $(SERVICE)

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------
.PHONY: test
test: test-backend test-frontend  ## Run all tests (backend + frontend)

.PHONY: test-backend
test-backend:   ## Run backend pytest suite
	cd backend && uv run pytest --tb=short -q

.PHONY: test-frontend
test-frontend:  ## Run frontend vitest suite (single run)
	cd frontend && npm run test:run

E2E_COMPOSE = docker compose -f docker-compose.yml -f docker-compose.e2e.yml

.PHONY: e2e-up
e2e-up:         ## Bring up the e2e overlay stack (fixture-server + webhook-sink + test hooks) and wait for backend health
	$(E2E_COMPOSE) up -d --build
	@echo "Waiting for backend health (up to 90s)..."
	@success=false; \
	for i in $$(seq 1 18); do \
	  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then \
	    echo "Backend healthy after $$(( i * 5 ))s"; success=true; break; \
	  fi; \
	  echo "Attempt $$i/18 — not ready yet, sleeping 5s..."; sleep 5; \
	done; \
	if [ "$$success" = "false" ]; then \
	  echo "ERROR: backend did not become healthy within 90s"; \
	  $(E2E_COMPOSE) logs backend; $(E2E_COMPOSE) down -v; exit 1; \
	fi
	@echo "Applying database migrations..."
	@if ! $(E2E_COMPOSE) exec -T backend /app/.venv/bin/alembic upgrade head; then \
	  echo "ERROR: alembic migrations failed"; \
	  $(E2E_COMPOSE) logs backend; $(E2E_COMPOSE) down -v; exit 1; \
	fi

.PHONY: e2e-down
e2e-down:       ## Tear down the e2e overlay stack and remove its volumes
	$(E2E_COMPOSE) down -v

.PHONY: test-e2e
test-e2e:       ## Full executed E2E: up e2e stack → run backend pytest-bdd + frontend playwright-bdd → down
	$(MAKE) e2e-up
	@echo "--- Backend BDD (pytest-bdd) ---"; \
	( cd backend && uv run pytest tests/e2e -o addopts="" -m live_api ); backend_rc=$$?; \
	echo "--- Frontend BDD (playwright-bdd) ---"; \
	( cd frontend && E2E_BASE_URL=http://localhost npm run test:e2e:bdd ); frontend_rc=$$?; \
	$(MAKE) e2e-down; \
	if [ $$backend_rc -ne 0 ] || [ $$frontend_rc -ne 0 ]; then \
	  echo "E2E FAILED (backend=$$backend_rc frontend=$$frontend_rc)"; exit 1; \
	fi; \
	echo "E2E passed."

.PHONY: test-e2e-smoke
test-e2e-smoke: ## Fast E2E: up e2e stack → run only @smoke-tagged scenarios → down
	$(MAKE) e2e-up
	@echo "--- Backend @smoke BDD ---"; \
	( cd backend && uv run pytest tests/e2e -o addopts="" -m "live_api and smoke" ); backend_rc=$$?; \
	echo "--- Frontend @smoke BDD ---"; \
	( cd frontend && E2E_BASE_URL=http://localhost npm run test:e2e:bdd -- --grep @smoke ); frontend_rc=$$?; \
	$(MAKE) e2e-down; \
	if [ $$backend_rc -ne 0 ] || [ $$frontend_rc -ne 0 ]; then \
	  echo "E2E smoke FAILED (backend=$$backend_rc frontend=$$frontend_rc)"; exit 1; \
	fi; \
	echo "E2E smoke passed."

.PHONY: generate-types
generate-types: ## Generate TypeScript types from backend/openapi.json
	cd frontend && npm run generate-types

# ---------------------------------------------------------------------------
# Linting & formatting
# ---------------------------------------------------------------------------
.PHONY: lint
lint:           ## Lint backend (ruff) and frontend (eslint)
	cd backend && uv run ruff check .
	cd frontend && npm run lint

.PHONY: format
format:         ## Format backend (ruff format) and frontend (prettier)
	cd backend && uv run ruff format .
	cd frontend && npm run format

# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------
.PHONY: quality
quality:        ## Run full quality gate: pytest + radon + vitest; exits 1 on threshold violation
	@mkdir -p logs/quality
	@TIMESTAMP=$$(date +%Y%m%dT%H%M%S); \
	  REPORT_DIR=logs/quality/$$TIMESTAMP; \
	  mkdir -p $$REPORT_DIR; \
	  echo "=== Backend tests + coverage ==="; \
	  cd backend && uv run pytest --cov=app --cov-report=xml:coverage.xml --cov-report=term-missing -m "not live_api" -q; \
	  echo "=== Backend complexity ==="; \
	  uv run radon cc app -a -s --json > ../$$REPORT_DIR/cc.json 2>&1; \
	  uv run radon mi app -s --json > ../$$REPORT_DIR/mi.json 2>&1; \
	  uv run radon hal app --json > ../$$REPORT_DIR/hal.json 2>&1; \
	  echo "Quality report saved to $$REPORT_DIR"; \
	  echo "=== Frontend coverage ==="; \
	  cd ../frontend && npm run test:coverage; \
	  cd ../backend && uv run python scripts/check_quality.py

# ---------------------------------------------------------------------------
# Database migrations
# ---------------------------------------------------------------------------
.PHONY: migrate
migrate:        ## Apply pending Alembic migrations (or generate: make migrate MSG="add_alerts")
ifdef MSG
	cd backend && uv run alembic revision --autogenerate -m "$(MSG)"
else
	cd backend && uv run alembic upgrade head
endif

.PHONY: shell-db
shell-db:       ## Open psql shell inside the running postgres container
	docker compose exec postgres psql -U $${POSTGRES_USER:-price_pulse} $${POSTGRES_DB:-price_pulse}

# ---------------------------------------------------------------------------
# Interactive shells
# ---------------------------------------------------------------------------
.PHONY: shell-backend
shell-backend:  ## Open bash shell inside the running backend container
	docker compose exec backend bash

# ---------------------------------------------------------------------------
# Celery workers (local, no Docker)
# ---------------------------------------------------------------------------
.PHONY: worker
worker:         ## Start Celery worker locally (no Docker); pool set in celery_app.py
	cd backend && uv run celery -A app.workers.celery_app worker --loglevel=debug

.PHONY: beat
beat:           ## Start Celery Beat scheduler locally (no Docker)
	cd backend && uv run celery -A app.workers.celery_app beat --scheduler redbeat.RedBeatScheduler --loglevel=debug

# ---------------------------------------------------------------------------
# OpenAPI spec
# ---------------------------------------------------------------------------
.PHONY: generate-openapi
generate-openapi:  ## Generate backend/openapi.json from the live FastAPI app (run before each PR)
	cd backend && \
	  SECRET_KEY=openapi-generation-dummy-key-min32chars \
	  DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db \
	  DEBUG=true \
	  uv run python -c \
	  "import json; from app.main import app; open('openapi.json','w').write(json.dumps(app.openapi(), indent=2))"

# ---------------------------------------------------------------------------
# Docker quality gates
# ---------------------------------------------------------------------------
.PHONY: lint-docker
lint-docker:    ## Lint all Dockerfiles with hadolint (fails on ERROR or WARN; INFO is shown but non-fatal)
	docker run --rm -i hadolint/hadolint hadolint --failure-threshold warning - < docker/backend.Dockerfile
	docker run --rm -i hadolint/hadolint hadolint --failure-threshold warning - < docker/frontend.Dockerfile
	docker run --rm -i hadolint/hadolint hadolint --failure-threshold warning - < docker/celery-playwright.Dockerfile

.PHONY: validate-nginx
validate-nginx: ## Validate nginx.conf syntax via Docker (asserts exit 0)
	docker run --rm \
	  --add-host=backend:127.0.0.1 \
	  -v $(shell pwd)/docker/nginx.conf:/etc/nginx/conf.d/default.conf:ro \
	  nginx:1.27-alpine nginx -t

.PHONY: scan
scan:           ## Scan built images for CRITICAL CVEs via Trivy (must run make build first)
	docker run --rm \
	  -v /var/run/docker.sock:/var/run/docker.sock \
	  aquasec/trivy:latest image \
	  --exit-code 1 \
	  --severity CRITICAL \
	  price-pulse-backend:latest price-pulse-frontend:latest

.PHONY: smoke
smoke:          ## Full-stack smoke test: up → health-check → nginx-check → down (exits 1 on failure)
	@echo "Starting stack..."
	docker compose up -d
	@echo "Waiting for backend health (up to 60s)..."
	@success=false; \
	for i in $$(seq 1 12); do \
	  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then \
	    echo "Backend healthy after $$(( i * 5 ))s"; \
	    success=true; \
	    break; \
	  fi; \
	  echo "Attempt $$i/12 — not ready yet, sleeping 5s..."; \
	  sleep 5; \
	done; \
	if [ "$$success" = "false" ]; then \
	  echo "ERROR: backend did not become healthy within 60s"; \
	  docker compose down; \
	  exit 1; \
	fi
	@echo "Checking nginx health endpoint..."
	@if ! curl -sf http://localhost/nginx-health > /dev/null 2>&1; then \
	  echo "ERROR: nginx-health endpoint did not return 200"; \
	  docker compose down; \
	  exit 1; \
	fi
	@echo "Smoke test passed."
	docker compose down

# ---------------------------------------------------------------------------
# Agent quality
# ---------------------------------------------------------------------------
.PHONY: lint-agents
lint-agents:    ## Validate agent frontmatter completeness and referenced paths; exits 1 on failure
	@FAIL=0; \
	echo "--- Checking .claude/agents/ frontmatter ---"; \
	for f in .claude/agents/*.md; do \
	  fm=$$(awk '/^---/{n++; if(n==2) exit; next} n==1{print}' "$$f"); \
	  for field in name description tools; do \
	    echo "$$fm" | grep -q "^$$field:" || { echo "FAIL $$f: missing '$$field' in frontmatter"; FAIL=1; }; \
	  done; \
	done; \
	echo "--- Checking .github/agents/ frontmatter ---"; \
	for f in .github/agents/*.agent.md; do \
	  fm=$$(awk '/^---/{n++; if(n==2) exit; next} n==1{print}' "$$f"); \
	  echo "$$fm" | grep -q "^description:" || { echo "FAIL $$f: missing 'description' in frontmatter"; FAIL=1; }; \
	done; \
	echo "--- Checking referenced paths in Quick Commands ---"; \
	for f in .claude/agents/*.md .github/agents/*.agent.md; do \
	  paths=$$(awk '/^```/{in_block=!in_block; next} in_block{print}' "$$f" | \
	    grep -oE '(logs|config|docs|backend|frontend|\.github/skills)/[a-zA-Z0-9_./-]+' | \
	    grep -v '[<>]' | sort -u); \
	  for p in $$paths; do \
	    base=$$(echo "$$p" | cut -d/ -f1-3); \
	    [ -e "$$base" ] || { echo "FAIL $$f: referenced path not found: $$p (checked: $$base)"; FAIL=1; }; \
	  done; \
	done; \
	[ "$$FAIL" = "0" ] && echo "All agent checks passed." || exit 1

# ---------------------------------------------------------------------------
# Code analysis
# ---------------------------------------------------------------------------
.PHONY: structure
structure:      ## Show backend package tree with module counts
	@echo "=== Backend package structure ==="
	@find backend/app -name "*.py" | sort | \
	  awk -F/ '{dir=$$1"/"$$2"/"$$3; count[dir]++} END {for (d in count) print count[d], d}' | \
	  sort -rn | head -30
	@echo ""
	@echo "=== Module count by package ==="
	@find backend/app -name "*.py" -not -name "__init__.py" | \
	  sed 's|/[^/]*\.py||' | sort | uniq -c | sort -rn

.PHONY: cloc
cloc:           ## Count lines of code (requires cloc; brew install cloc)
	cloc . \
	  --exclude-dir=node_modules,.venv,.git,__pycache__,.mypy_cache,.ruff_cache,dist,build,htmlcov,logs \
	  --exclude-ext=json,lock,toml \
	  --not-match-f='coverage\.xml|\.min\.(js|css)'
