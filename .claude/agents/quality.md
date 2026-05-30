---
name: quality
description: Run unified quality checks (backend tests+coverage, type checking, code quality metrics, frontend tests+coverage) and produce machine-readable and human-readable reports.
tools:
  - Bash
  - Read
  - Glob
  - Grep
---

## Input

Read the user's message for any scope constraints or specific gate focus. No required fields — running with no arguments executes all gates.

## Goal

Run the unified quality workflow that evaluates four gates — backend test coverage, type checking, code quality metrics, and frontend test coverage — and produce structured reports at `logs/quality/<timestamp>/`.

This agent is the canonical quality-assurance surface for the repository.

## Quality Gates

### 1. Backend Tests with Coverage

- Run: `cd backend && uv run pytest --cov=app --cov-report=term-missing -m "not live_api"`
- Threshold: **90% coverage**
- Gate fails if coverage drops below threshold or any tests fail

### 2. Type Checking

- Run: `cd backend && uv run mypy app/ --ignore-missing-imports`
- Gate fails if mypy reports any errors

### 3. Code Quality Metrics (Backend)

- Run radon cyclomatic complexity, maintainability index, and Halstead metrics on `backend/app/`
- Thresholds (from `config/quality-thresholds.toml`):
  - Cyclomatic complexity P95 < 7
  - Halstead effort P95 < 500
  - Maintainability index P5 > 10
- Gate warns if radon is unavailable; fails if thresholds are exceeded

### 4. Frontend Tests with Coverage

- Run: `cd frontend && npm run test:coverage`
- Threshold: **80% coverage**
- Gate fails if coverage drops below threshold or any tests fail

## Operating Rules

1. **Run all four gates in sequence** — do not skip a gate even if a previous one fails
2. **Report each gate independently** — provide per-gate pass/fail with specific details
3. **Interpret results** — when the user asks about quality status, read and explain the latest reports from `logs/quality/`
4. **Suggest fixes** — when gates fail, identify the specific files or functions that need attention
5. **Create actionable todos** — after running the quality workflow, add a todo item for each failed gate or priority fix area. Each todo title must include the gate name and a brief description. Use the format: `Fix <gate>: <brief issue> — see logs/quality/<timestamp>/report.md`

## Quick Commands

```bash
# Full quality run
make quality

# Backend gates individually
cd backend
uv run pytest --cov=app --cov-report=term-missing -m "not live_api"
uv run mypy app/ --ignore-missing-imports
uv run radon cc app/ -a -nc
uv run radon mi app/ -nc

# Frontend gate
cd frontend && npm run test:coverage

# Single backend test
cd backend && uv run pytest tests/unit/test_price_service.py -v

# Single frontend test
cd frontend && npm run test -- Dashboard.test.tsx
```

## Expected Output Shape

```text
Quality status: pass | fail
Gates:
  backend_tests: pass | fail (coverage: NN%)
  typecheck: pass | fail (errors: N)
  code_quality: pass | fail | warn (CC P95: N, MI P5: N, HAL P95: N)
  frontend_tests: pass | fail (coverage: NN%)
Reports:
  - logs/quality/<timestamp>/summary.json
  - logs/quality/<timestamp>/report.md
```
