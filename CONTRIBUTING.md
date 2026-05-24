# Contributing to Price Pulse

Thank you for taking the time to contribute! This document describes the workflow, commit conventions, and quality gates for the project.

---

## Branch Strategy — GitHub Flow

We use [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow):

1. `main` is **always deployable**. Never commit directly to `main`.
2. All work happens on **short-lived feature branches** cut from `main`.
3. Open a Pull Request early — even as a draft — to get feedback.
4. Once CI is green and at least one reviewer has approved, merge via **Squash and Merge**.
5. Delete the branch after merging.

### Branch naming

```
<type>/<short-description>
```

Examples:

```
feat/price-history-chart
fix/alert-threshold-validation
chore/bump-fastapi-version
docs/update-architecture-diagram
```

---

## Conventional Commits

All commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) and are enforced by `commitlint` on every commit.

### Format

```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### Types

| Type | Use |
|------|-----|
| `feat` | A new feature |
| `fix` | A bug fix |
| `chore` | Build, tooling, or dependency change |
| `docs` | Documentation only |
| `refactor` | Code change that doesn't fix a bug or add a feature |
| `test` | Adding or updating tests |
| `ci` | CI configuration change |
| `perf` | Performance improvement |

### Scopes

`backend`, `frontend`, `docker`, `ci`, `deps`, `config`, `docs`, `agents`, `scraper`, `api`, `db`, `celery`, `auth`, `alerts`

### Subject rules

- Start with lowercase
- No trailing period
- Max 100 characters total header length
- Use imperative mood ("add endpoint" not "added endpoint")

### Examples

```
feat(api): add paginated price history endpoint
fix(scraper): handle 404 responses without crashing
chore(deps): bump fastapi to 0.112
docs(backend): document price_service deduplication logic
test(api): add integration tests for alert CRUD endpoints
ci: add docker build job to pr workflow
refactor(scraper): extract http retry logic to shared client
```

### Breaking changes

Append `!` to the type and add a `BREAKING CHANGE:` footer:

```
feat(api)!: rename /products/{id}/history to /products/{id}/prices

BREAKING CHANGE: clients must update their URL references.
```

---

## Pull Request Checklist

Before requesting a review, verify:

- [ ] **Tests pass**: `make test` exits 0
- [ ] **Lint passes**: `make lint` exits 0
- [ ] **Quality gate**: `make quality` passes all thresholds
- [ ] **No `.env` committed**: `.env` must never appear in the diff
- [ ] **Migrations included**: if models changed, the Alembic migration is in the PR
- [ ] **CHANGELOG updated**: new entry under `## [Unreleased]` in `CHANGELOG.md`
- [ ] **PR description** explains _what_ changed and _why_
- [ ] **Scope is small**: a PR should do one thing; split if needed

### `make quality` requirement

Run this before every PR:

```bash
make quality
```

It checks:
- Backend cyclomatic complexity (CC P95 < 7)
- Backend maintainability index (MI P5 > 10)
- Backend test coverage (≥ 90%)
- Frontend test coverage (≥ 80%)

A PR may not be merged if `make quality` exits non-zero.

---

## Setting Up Your Development Environment

```bash
# Clone
git clone <repo-url> price_pulse
cd price_pulse

# Copy env config
cp .env.example .env

# Install deps + pre-commit hooks
make install

# Start the dev stack
make dev
```

---

## Running Tests

```bash
make test           # all tests
make test-backend   # pytest only
make test-frontend  # vitest only
```

Backend tests in `backend/tests/`:
- `unit/` — fast, no DB, mock everything external
- `integration/` — real DB (Postgres in Docker or test container)
- `e2e/` — `@pytest.mark.live_api` — skip by default; run manually

---

## Code Style

### Backend (Python)

- Formatter: `ruff format` (via `make format`)
- Linter: `ruff check` (via `make lint`)
- Line length: 100 characters
- Type annotations required on all public functions

### Frontend (TypeScript)

- Formatter: `prettier` (via `make format`)
- Linter: `eslint` (via `make lint`)
- No `any` types without a `// eslint-disable` comment and justification

---

## Questions?

Open an issue or ping in the project discussion board.
