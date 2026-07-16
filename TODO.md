# TODO — Price Pulse

Price monitoring platform: track retail product prices across external web sources and alert users when it's a good time to buy.

---

## 11. Test Suite Health & Coverage Deduplication ✅ COMPLETE

Prevent test suite bloat by detecting and eliminating intra-tier coverage duplication — where two test functions in the same tier (both unit, or both integration) exercise the same source line without adding distinct assertions. Uncontrolled duplication inflates run time, makes refactors expensive, and creates false assurance that a line is "well-tested" when it is only visited redundantly.

Cross-tier overlap (a unit test and an integration test covering the same line) is intentional and excluded from this check — unit and integration tests serve different verification purposes.

**Depends on**: Item 10 (CI/CD & Quality Gates) — `backend/scripts/` directory, `make quality` infrastructure, and `logs/quality/` scaffolding must be in place.

### Design decisions (resolved)

- **Definition of duplication**: Two test functions within the same tier (`tests/unit/` or `tests/integration/`) that cover the same source line. Cross-tier overlap is acceptable and not flagged. Rationale: identical behaviour tested at two levels of isolation is a quality multiplier; identical behaviour tested twice at the same level is waste.

- **Backend detection — pytest-cov context tracking**: `pytest-cov` passes `--cov-context=test` to `coverage.py` (supported since v5.x), tagging each `.coverage` database entry with the test node ID that executed it. `coverage json` then produces a JSON file whose `"contexts"` dict maps each covered line to a list of test IDs. A script classifies each test ID by tier (unit or integration by directory path) and flags any line with two or more context entries from the same tier. Rationale: no new dependencies — `coverage.py` is already a transitive dep of `pytest-cov`; the data is already collected after any `--cov` run; context tagging adds negligible overhead.

- **Frontend detection — per-test-file vitest runs**: vitest's V8 and Istanbul coverage providers aggregate coverage across all tests in a single run; neither attributes lines to individual test functions. The practical approach is to run each test file in isolation (`vitest run <file> --coverage`) and save a `coverage-summary.json` per file into a staging directory. A Node.js script then loads all per-file summaries and flags any source line appearing as covered in two or more test-file reports from the same tier. Rationale: per-file runs are the only way to achieve test-function-level attribution in vitest without a custom reporter; the frontend test suite is small (currently ~5 files), so N separate vitest processes is acceptable overhead for a local quality gate.

- **`scripts/` directory location**: Both frontend overlap scripts (`check_coverage_overlap_frontend.sh` and `check_coverage_overlap_frontend.js`) live in `scripts/` at the repo root. Rationale: keeps frontend quality tooling separate from `backend/scripts/` Python scripts; a single top-level `scripts/` directory follows common monorepo convention.

- **Frontend script working directory**: `check_coverage_overlap_frontend.sh` `cd`s into `frontend/` before invoking vitest, so `--coverage.reportsDirectory` uses `../logs/quality/frontend-coverage-per-file/<slug>` (one level up from `frontend/`). Rationale: corrects a potential path error — `../../` from within `frontend/` would resolve outside the repo root.

- **Reporting format — informational first, enforcement after baseline**: Both scripts print a table of (source-file, line, tier, [test-ids]) tuples and a summary line. After the baseline task establishes actual counts, both scripts are updated to read `max_intra_tier_duplicate_lines_backend` / `max_intra_tier_duplicate_lines_frontend` from `[test-health]` in `config/quality-thresholds.toml`. If the field is absent, the script exits 0 with "No enforcement threshold set — run baseline task first". When present and the actual count exceeds the threshold, the script exits 1. Rationale: gate is active as soon as the baseline is known without requiring a separate follow-up item; exit-0-on-absent-field avoids CI failures before the baseline run completes.

- **Correction strategy**: When duplication is flagged, determine whether the two tests assert the same behaviour (merge or delete the weaker test) or different behaviours that share an execution path (extract the shared path to a fixture or helper). No structural changes to test file organisation are required.

- **Backend `coverage json` output location**: Written to `logs/quality/coverage-contexts.json`. Added to `.gitignore` alongside other `logs/` data. Rationale: co-located with other quality artefacts; does not conflict with `coverage.xml` used by `check_quality.py`.

- **Frontend per-file staging directory**: `logs/quality/frontend-coverage-per-file/<test-file-slug>/coverage-summary.json`. Created and deleted on each run of `make check-coverage-overlap-frontend`. Rationale: ephemeral; the comparison script reads from this directory and the result is printed to stdout.

- **`make quality` integration**: Both overlap scripts are called at the end of `make quality`. They are informational-only until enforcement thresholds are set in `[test-health]`, at which point they may exit 1. Rationale: quality gate exit code is already owned by `check_quality.py` and `--cov-fail-under=90`; enforcement is additive and calibrated before activation.

- **Top-level `tests/*.test.*` files**: `frontend/tests/smoke.test.ts` (and any future top-level test files) are intentionally excluded from per-file vitest runs. The shell script only iterates files under `tests/unit/` and `tests/integration/`. Rationale: smoke tests serve a different verification purpose and are not subject to intra-tier duplication analysis.

### Tasks

**Setup**
- [x] Create `scripts/` directory at repo root (non-package — no `__init__.py` or `package.json`)

**Backend detection**
- [x] Append `--cov-context=test` to the pytest invocation in the `make quality` Makefile target (on the same `uv run pytest --cov=app ...` line added by Item 10)
- [x] Add `coverage json -o logs/quality/coverage-contexts.json` step to the `make quality` Makefile target, run immediately after pytest (requires `cd backend` prefix; the `.coverage` database is written by pytest-cov in the backend directory)
- [x] Create `backend/scripts/check_coverage_overlap.py`:
  - Load `logs/quality/coverage-contexts.json` (path resolved relative to repo root); exit 1 with "Run make quality first to generate coverage data" if absent
  - For each source file in the JSON, iterate the `"contexts"` dict (maps line-number string → list of test node ID strings)
  - Classify each node ID as `unit` (contains `/tests/unit/`) or `integration` (contains `/tests/integration/`); skip `e2e` and unrecognised paths
  - Flag any line where two or more node IDs share the same tier classification
  - Print a table: `source_file | line | tier | test_a | test_b`; truncate test IDs to the function name for readability
  - Print summary: `N intra-tier duplicate lines found across M source files (unit: X, integration: Y)`
  - Read `max_intra_tier_duplicate_lines_backend` from `[test-health]` in `config/quality-thresholds.toml`; if absent, print "No enforcement threshold set — run baseline task first" and exit 0; if present and actual count exceeds threshold, exit 1 with "Backend intra-tier duplicate lines (N) exceeds threshold (M)"
- [x] Add `make check-coverage-overlap` Makefile target: `cd backend && uv run python scripts/check_coverage_overlap.py`
- [x] Call `make check-coverage-overlap` at the end of the `make quality` target (after `check_quality.py`)

**Frontend detection**
- [x] Create `scripts/check_coverage_overlap_frontend.sh` — for each `*.test.ts` / `*.test.tsx` file found under `frontend/tests/unit/` and `frontend/tests/integration/`, `cd` into `frontend/` then run `npx vitest run --coverage --coverage.reportsDirectory=../logs/quality/frontend-coverage-per-file/<slug> <file>` where slug is the test file basename without extension; skip `e2e/` files and top-level `tests/*.test.*` files (e.g. `smoke.test.ts`)
- [x] Create `scripts/check_coverage_overlap_frontend.js` (Node.js, no external deps):
  - Scan `logs/quality/frontend-coverage-per-file/` for `coverage-summary.json` files; exit 0 with a warning if none found ("Run make check-coverage-overlap-frontend to generate per-file data")
  - For each source file, collect the set of line numbers reported as covered in each per-file report; classify by tier from the test file's directory path; flag any source line covered by two or more reports from the same tier
  - Print a table: `source_file | line | tier | test_file_a | test_file_b`
  - Print summary: `N intra-tier duplicate lines found across M source files`
  - Read `max_intra_tier_duplicate_lines_frontend` from `[test-health]` in `config/quality-thresholds.toml`; if absent, print "No enforcement threshold set — run baseline task first" and exit 0; if present and actual count exceeds threshold, exit 1 with "Frontend intra-tier duplicate lines (N) exceeds threshold (M)"
- [x] Add `make check-coverage-overlap-frontend` Makefile target: `bash scripts/check_coverage_overlap_frontend.sh && node scripts/check_coverage_overlap_frontend.js`
- [x] Call `make check-coverage-overlap-frontend` at the end of the `make quality` target (after the vitest step)

**Baseline and enforcement**
- [x] Run `make check-coverage-overlap` and `make check-coverage-overlap-frontend` on the current codebase; add a `[test-health]` section to `config/quality-thresholds.toml` recording `baseline_backend_duplicate_lines = N` and `baseline_frontend_duplicate_lines = N` with a comment noting the date
- [x] Set enforcement thresholds: update `[test-health]` to add `max_intra_tier_duplicate_lines_backend = N` and `max_intra_tier_duplicate_lines_frontend = N` (set to the baseline values — zero tolerance for net new duplicates from this point forward)
- [x] Verify `make quality` exits cleanly with enforcement thresholds set (no duplicate violations in the current codebase, or remediate any found before merging)

**Gitignore**
- [x] Verify that `logs/quality/coverage-contexts.json` and `logs/quality/frontend-coverage-per-file/` are excluded by the existing `logs/**` rule in `.gitignore`; add explicit entries only if not already covered

### Test strategy

- **Unit** (isolated, no external processes — Arrange-Act-Assert):
  - `check_coverage_overlap.py`: fixture `coverage-contexts.json` with two unit test IDs covering the same line in the same file → reports 1 duplicate at tier `unit`; fixture where a unit test and integration test cover the same line → reports 0 duplicates (cross-tier excluded); no duplication at all → "0 intra-tier duplicate lines found"; missing `coverage-contexts.json` → exits 1 with "Run make quality first"; malformed JSON → exits 1 with descriptive parse error, not an unhandled traceback; `max_intra_tier_duplicate_lines_backend` absent from `[test-health]` → exits 0 with "No enforcement threshold set"; actual count equals threshold → exits 0 (threshold is a ceiling; N ≤ threshold passes); actual count exceeds threshold → exits 1 with "Backend intra-tier duplicate lines (N) exceeds threshold (M)"
  - `check_coverage_overlap_frontend.js`: two `tests/unit/` coverage summaries sharing a line in a source file → 1 duplicate reported; `tests/unit/` and `tests/integration/` covering the same line → 0 duplicates (cross-tier excluded); empty staging directory → exits 0 with warning; threshold absent → exits 0 with info; count exceeds threshold → exits 1

- **Integration** (real filesystem — Arrange-Act-Assert):
  - `make check-coverage-overlap` runs against the real codebase (after `make quality`) → exits 0; summary line printed to stdout
  - `make check-coverage-overlap-frontend` runs against the real codebase → exits 0; summary line printed to stdout

- **Negative** (Arrange-Act-Assert):
  - Missing `logs/quality/coverage-contexts.json` → `check_coverage_overlap.py` exits 1 with message containing "Run make quality first"; no unhandled `FileNotFoundError`
  - Missing `logs/quality/frontend-coverage-per-file/` → `check_coverage_overlap_frontend.js` exits 0 with warning (non-blocking)
  - Test node ID that matches neither `tests/unit/` nor `tests/integration/` (e.g. `tests/e2e/`) → skipped without error; summary reflects only classified tiers

- **Live E2E** (manual acceptance test — run after Item 10 is complete):
  - Run `make quality` on a clean checkout; assert both `check-coverage-overlap` and `check-coverage-overlap-frontend` exit 0 and each prints a summary line to stdout
  - After enforcement thresholds are set, re-run `make quality`; assert both scripts still exit 0 (no violations in the current codebase); if violations are found, remediate before merging

### Documentation

- **`scripts/`** — create: top-level directory for frontend quality scripts
- **`Makefile`** — update: add `check-coverage-overlap`, `check-coverage-overlap-frontend` targets; update `make quality` to append `--cov-context=test`, add `coverage json` step, and call both overlap scripts; update `make quality` help text to note overlap checks can exit 1 when thresholds are set
- **`backend/scripts/check_coverage_overlap.py`** — create: backend intra-tier overlap detector with enforcement logic
- **`scripts/check_coverage_overlap_frontend.sh`** — create: per-file vitest runner (cd's into `frontend/`; uses `../logs/quality/` relative path)
- **`scripts/check_coverage_overlap_frontend.js`** — create: frontend intra-tier overlap detector with enforcement logic
- **`config/quality-thresholds.toml`** — update: add `[test-health]` section with baseline counts and enforcement thresholds
- **`.gitignore`** — update: verify `logs/quality/coverage-contexts.json` and `logs/quality/frontend-coverage-per-file/` are excluded
- **`CLAUDE.md`** — update: commands table to add `make check-coverage-overlap` and `make check-coverage-overlap-frontend`; quality thresholds section to reference `[test-health]` enforcement
- **`CHANGELOG.md`** — add `### Added` entry under `## [Unreleased]` at implementation time: test suite health tooling (intra-tier coverage deduplication detection via `coverage.py` context tracking for pytest and per-test-file vitest runs; enforcement thresholds in `config/quality-thresholds.toml`)

---

## 12. Quality Issue Fixes (PR #1 pre-merge) ✅ COMPLETE

Address quality gate failures surfaced when CI runs against PR #1 (`feat/item-11-plan-review`). This item tracks any lint, test, type-check, or threshold violations that must be resolved before the branch can be merged to `main`.

**Depends on**: PR #1 CI run completing and reporting failures.

**Resolution**: PR #1 merged to `main` on 2026-07-05 (squash) with all 7 CI checks green (Lint, Test — Backend, Test — Frontend, Build — Docker images, Agent quality, Security — dependency CVE scan, Smoke — Full-stack health check).

### Tasks

- [x] Review CI results for PR #1 and list all failing jobs (lint, test-backend, test-frontend, build, security, agent-quality)
- [x] Fix each failing check and push fixup commits to `feat/item-11-plan-review`
- [x] Confirm all required status checks pass before converting PR #1 from draft to ready for review

---

## 13. E2E Test Harness & CI for the Live Compose Stack ✅ COMPLETE

The repo currently has **no behavioural E2E coverage** against a running application. What exists is a liveness poll only: the CI "Smoke — Full-stack health check" job and `make smoke` bring up `docker compose` and curl `/health` + `/nginx-health`, and one backend `@pytest.mark.live_api` test hits `/health`. The Playwright specs in `frontend/tests/e2e/smoke.spec.ts` cover UI navigation only, target the Vite dev server (`localhost:5173`) rather than the composed nginx stack, are wired to **no** npm script, and are **never executed in CI** (`@playwright/test` is an unused devDependency). `make test-e2e` exists but only runs `cd frontend && npx playwright test` against the dev server.

This item delivers the **executable E2E harness and CI** that the Item 14 BDD catalogue runs inside — plus a thin self-check of its own. It does **not** author the behaviour scenarios or step definitions (those are Item 14). It provides: a dedicated e2e `docker compose` overlay, a deterministic fixture scrape target with a price-mutation hook, a webhook-sink for notification assertions, env-flag-gated test-control endpoints (force-scrape, reset-cooldown), the `make` lifecycle targets, and the CI jobs.

**Scope boundary with Item 14** (resolved): **Item 13 owns the harness + CI + a thin `@smoke` self-check**. **Item 14 owns the `.feature` catalogue + step definitions.** Item 14's executable steps depend on this harness; implement **harness (13) first**, then the catalogue (14). Item 13's own self-check reuses a `@smoke`-tagged subset of Item 14 features, so a first slice of Item 14 features must exist for the self-check to pass — sequence accordingly.

**Depends on**: existing `docker compose` stack and CI smoke job (Item 10, complete). **Blocks**: Item 14 (its steps require this harness).

### Implementation workflow (mandatory — complete in order)

1. [ ] Create an isolated git worktree before writing any code:
       `git worktree add ../pp-item-13 -b feat/item-13` — never work on `main`.
2. [ ] Implement every task below inside that worktree — never directly on `main`.
3. [ ] All quality gates must pass before opening a PR:
       `make test` exits 0 and `make quality` exits 0
       (see `CONTRIBUTING.md` → Pull Request Checklist).
4. [ ] Raise a Pull Request: `gh pr create`
       **No direct commits to the default branch (`main`) are permitted.**

### Design decisions (resolved)

- **Item 13/14 boundary — 13 owns harness + CI + thin smoke; 14 owns features + steps**: Item 13 provides everything needed to *run* executed BDD against live compose; Item 14 authors what is run. Rationale: isolates infrastructure churn from behaviour authoring while keeping each independently reviewable.

- **e2e stack layering — new `docker-compose.e2e.yml` override**: applied as `docker compose -f docker-compose.yml -f docker-compose.e2e.yml`. The override adds the `fixture-server` and `webhook-sink` services and sets test-only env on backend + celery services: `E2E_TEST_HOOKS=true`, `SCRAPE_INTERVAL_MINUTES=1`, and a tiny `ALERT_COOLDOWN_HOURS`. Rationale: the production `docker-compose.yml` stays untouched and prod-safe; no test-only service or env ever ships in the base compose. Chosen over compose `profiles:` to avoid mixing test services into the prod file.

- **Fixture scrape target — custom in-repo `fixture-server`; off-the-shelf `webhook-sink`**: a small in-repo Starlette/FastAPI app (`tests/e2e/fixture_server/`, its own image via `docker/fixture-server.Dockerfile`) serves canned product HTML through the real `generic` scraper path and exposes `PUT /fixtures/{slug}/price` to mutate the served price (and `GET /fixtures/{slug}` to serve it). The webhook-sink is an off-the-shelf request-capture image (e.g. a httpbin/request-bin-style container) polled over HTTP to confirm webhook deliveries. Rationale: price-mutation needs bespoke, versioned behaviour; webhook capture does not, so avoid custom code there.

- **Test-control hooks — env-flag gated, in-process, e2e-profile only**: a FastAPI router mounted **only when `settings.E2E_TEST_HOOKS is True`** (new `E2E_TEST_HOOKS: bool = False` field in `core/config.py`), and that flag is set **only** by `docker-compose.e2e.yml`. Endpoints (namespaced under `/api/v1/_test/`): `POST /_test/products/{id}/scrape-sync` (force a scrape) and `POST /_test/alerts/{id}/reset-cooldown`. Rationale: no separate sidecar; the hooks are absent from the app's routes in every non-e2e environment because the router is never included.

- **Force-scrape execution — synchronous inline hook, plus one real-cadence scenario**: `scrape-sync` runs the scrape task body **inline** (not via the Celery queue) and returns only after the `PriceRecord` is persisted and alerts evaluated, so steps get a definitive result with no polling. Item 14 additionally keeps **one** scenario that relies on the real 1-minute beat + bounded polling to prove the async scheduled path end-to-end. Rationale: determinism by default, with a single guarded test of the genuine async pipeline.

- **`make` lifecycle — `test-e2e` owns up→run→down; `test-e2e-smoke` for the subset**: `make test-e2e` brings up the e2e overlay, waits for health, runs backend `pytest-bdd` + frontend `playwright-bdd`, then tears down. `make test-e2e-smoke` runs only `@smoke` scenarios. `make e2e-up` / `make e2e-down` manage the overlay for local iteration against an already-running stack. The existing dev-server-only `make test-e2e` is replaced. Rationale: one command for a clean full run; a fast subset command; and helpers for the inner-loop.

- **CI — `@smoke` on every PR, full catalogue nightly + manual; liveness `smoke` job unchanged**: a new `e2e` CI job (`needs: build`) brings up the e2e overlay, waits for health, runs `make test-e2e-smoke`, and uploads the Playwright HTML report + traces as artifacts on failure. The **full** catalogue runs on a nightly `schedule:` and on `workflow_dispatch`. The existing `smoke` liveness job stays as the fast per-PR gate. Rationale: keeps PR feedback fast and low-flake while still gating the full suite regularly. Playwright browsers are installed in-job (`npx playwright install --with-deps chromium`).

- **Data isolation — ephemeral volumes per run**: the e2e overlay uses throwaway postgres/redis volumes so each `make test-e2e` / CI run starts clean; scenario-level isolation (unique fixture URLs) is Item 14's concern. Rationale: no cross-run state; deterministic CI.

### Tasks

**e2e compose overlay**
- [x] Create `docker-compose.e2e.yml` overriding the base stack: add `fixture-server` + `webhook-sink` services on `price-pulse-net`; set `E2E_TEST_HOOKS=true`, `SCRAPE_INTERVAL_MINUTES=1`, tiny `ALERT_COOLDOWN_HOURS` on backend + celery services; use ephemeral (unnamed) postgres/redis volumes
- [x] Add resource limits and healthchecks for the two new services consistent with the existing services

**Fixture server**
- [x] Create `tests/e2e/fixture_server/` — a minimal Starlette/FastAPI app serving canned product HTML at `GET /fixtures/{slug}` (price embedded so the `generic` scraper's CSS selector extracts it) and mutating it via `PUT /fixtures/{slug}/price`
- [x] Create `docker/fixture-server.Dockerfile` and wire the service into `docker-compose.e2e.yml`

**Webhook sink**
- [x] Add an off-the-shelf request-capture `webhook-sink` service to `docker-compose.e2e.yml`; document the capture-query URL step definitions will poll (Item 14 consumes)

**Test-control hooks**
- [x] Add `E2E_TEST_HOOKS: bool = False` to `core/config.py` `Settings` (+ `.env.example` note that it must stay false outside e2e)
- [x] Create a test-control router (`api/v1/_test_hooks.py`) included in `main.py` **only when `settings.E2E_TEST_HOOKS`**: `POST /api/v1/_test/products/{id}/scrape-sync` (inline scrape, returns after `PriceRecord` + alert eval) and `POST /api/v1/_test/alerts/{id}/reset-cooldown`
- [x] Assert the router is **absent** from the app's route table when the flag is false (guard against accidental prod exposure)

**Make lifecycle**
- [x] Replace the current dev-server `make test-e2e` with: `make e2e-up`, `make e2e-down`, `make test-e2e` (up → wait health → backend `pytest-bdd` + frontend `playwright-bdd` → down), and `make test-e2e-smoke` (`@smoke` subset)
- [x] Update `frontend/playwright.config.ts` default/`E2E_BASE_URL` handling for `http://localhost` (compose nginx) when run under the e2e stack

**CI**
- [x] Add an `e2e` job to `.github/workflows/ci.yml` (`needs: build`): bring up the e2e overlay, wait for health, install Playwright browsers, run `make test-e2e-smoke`, upload Playwright report + traces on failure
- [x] Add a nightly `schedule:` + `workflow_dispatch` trigger that runs the **full** catalogue (`make test-e2e`)
- [x] Leave the existing `smoke` liveness job unchanged as the fast per-PR gate

**Thin smoke self-check**
- [x] Verify `make test-e2e-smoke` (the `@smoke` subset of Item 14 features) passes against the e2e overlay as Item 13's own harness acceptance check — coordinate with Item 14 so a first `@smoke` slice of features exists

### Test strategy

All four layers (Arrange-Assert-Act for backend tests):

- **Unit** (isolated, no stack): the `fixture-server` app handlers (canned-HTML render, `PUT price` mutation) unit-tested with a test client; the test-control router mounting logic — assert the router **is** included when `E2E_TEST_HOOKS=true` and **absent** when false; the inline `scrape-sync` handler with a mocked scrape body.
- **Integration** (real DB, no full compose): `scrape-sync` and `reset-cooldown` hooks against the Postgres testcontainer (`pg_async_client`) — force a scrape writes a `PriceRecord`; reset-cooldown clears the alert's cooldown state. `docker-compose.e2e.yml` validated with `docker compose config` (parses, references real services).
- **Negative** (Arrange-Assert-Act): `scrape-sync` / `reset-cooldown` return 404 for unknown IDs; hooks return 404 (router absent) when `E2E_TEST_HOOKS` is false; `PUT /fixtures/{slug}/price` with a bad body → 422; webhook-sink unreachable → step-visible failure, not a hang.
- **Live E2E** (against the running stack): `make test-e2e-smoke` runs the `@smoke` Item 14 scenarios against the e2e overlay and passes; the CI `e2e` job is green on PRs; the nightly full run is green. Acceptance: harness brings the stack to health, both runners execute, and artifacts upload on failure.

### Documentation
- **`docker-compose.e2e.yml`** — create: e2e overlay (fixture-server + webhook-sink + test-hook env)
- **`docker/fixture-server.Dockerfile`** — create
- **`tests/e2e/fixture_server/`** — create: canned-HTML + price-mutation service
- **`backend/app/core/config.py`** — update: add `E2E_TEST_HOOKS` setting
- **`backend/app/api/v1/_test_hooks.py`** — create: gated test-control router
- **`backend/app/main.py`** — update: conditionally include the test-hook router
- **`.env.example`** — update: `E2E_TEST_HOOKS` (must be false outside e2e) note
- **`frontend/playwright.config.ts`** — update: `E2E_BASE_URL` for the compose nginx stack
- **`Makefile`** — update: replace `test-e2e`; add `e2e-up`, `e2e-down`, `test-e2e-smoke`
- **`.github/workflows/ci.yml`** — update: `e2e` job (@smoke on PR) + nightly/manual full-catalogue trigger
- **`CLAUDE.md`** — update: document the e2e overlay, `make test-e2e`/`test-e2e-smoke`/`e2e-up`/`e2e-down`, `E2E_TEST_HOOKS`, and the harness/behaviour split between Items 13 and 14
- **`CHANGELOG.md`** — add `### Added` entry: E2E test harness (e2e compose overlay, fixture server with price-mutation, webhook sink, gated test-control hooks, `make` lifecycle, CI e2e job)

---

## 14. Standardised, Executed E2E Behaviour Specification (BDD) ✅ COMPLETE

The repo has **no standardised definition of expected end-to-end behaviour**. Behaviour intent currently lives only as ad-hoc prose inside `TODO.md` "Test strategy" / "Live E2E" subsections and the tier description in `CLAUDE.md` — there is no scenario catalogue, no Gherkin format, and nothing traceable or executable.

This item defines the expected E2E behaviour of Price Pulse as a **standardised Gherkin catalogue that is executed as BDD** (`pytest-bdd` for backend journeys, `playwright-bdd` for frontend UI journeys) against the **live `docker compose` stack**. The `.feature` files are the single source of truth for behaviour; their step definitions are the executable E2E tests. The full catalogue is authored here — including non-functional scenarios (scheduling cadence, per-domain rate limiting, notification-channel variants) made deterministic via test hooks.

**Scope boundary with Item 13** (resolved): **Item 14 owns the `.feature` catalogue AND the step definitions** (the executable glue). **Item 13 owns the test harness and CI** — the e2e `docker compose` profile, the fixture HTTP server, the webhook-sink service, seed/fixture data, and the CI job that brings the stack up and invokes the runners. Item 14's executable steps therefore **depend on Item 13's harness contract** (see Design decisions); the two items should be implemented together, harness first.

**Depends on**: Item 13 (E2E harness: e2e compose profile, fixture server with price-mutation endpoint, webhook-sink service, `make test-e2e` runner, CI job). Item 14 authors features + steps that run inside that harness.

### Implementation workflow (mandatory — complete in order)

1. [ ] Create an isolated git worktree before writing any code:
       `git worktree add ../pp-item-14 -b feat/item-14` (a `feat/item-14-e2e-behaviour-spec` branch already exists from plan-review; reuse it or rebranch — never work on `main`).
2. [ ] Implement every task below inside that worktree — never directly on `main`.
3. [ ] All quality gates must pass before opening a PR:
       `make test` exits 0 and `make quality` exits 0
       (see `CONTRIBUTING.md` → Pull Request Checklist).
4. [ ] Raise a Pull Request: `gh pr create`
       **No direct commits to the default branch (`main`) are permitted.**

### Design decisions (resolved)

- **Execution model — executed BDD, not a traceable-only spec**: `.feature` files are executed directly. Backend scenarios run under `pytest-bdd`; frontend UI scenarios run under `playwright-bdd`. Rationale: the spec and its verification never drift because the Gherkin *is* the test.

- **Item 13/14 boundary — 14 owns features + step definitions; 13 owns harness + CI**: Item 14 delivers `docs/behaviour/*.feature` and their step-definition modules. Item 13 delivers the runtime the steps need (e2e compose profile, fixture server, webhook sink, seed data, `make test-e2e`, CI job). Rationale: keeps the behaviour catalogue and its glue in one reviewable unit while isolating infrastructure churn in Item 13.

- **Feature-file location — `docs/behaviour/` is canonical; runners point there**: `.feature` files live under `docs/behaviour/` as the single source of truth and remain browsable as documentation. `pytest-bdd`'s `scenarios("../../docs/behaviour/…")` (or a configured `bdd_features_base_dir`) and `playwright-bdd`'s `defineBddConfig({ features: '../docs/behaviour/**/*.feature' })` are pointed at that directory. Step definitions live beside the tests: backend in `backend/tests/e2e/steps/`, frontend in `frontend/tests/e2e/steps/`. Rationale: satisfies both "spec lives in docs/" and runner discoverability without duplicating files.

- **Scenario ID convention — `PP-E2E-NNN`**: every `Scenario`/`Scenario Outline` carries a stable `@PP-E2E-NNN` Gherkin tag. `docs/behaviour/README.md` documents the convention, ID allocation, and the tag→step-module map. Rationale: stable IDs give traceability independent of scenario wording.

- **Deterministic scrape target — fixture HTTP server with mutable price endpoint** *(harness, Item 13; contract consumed here)*: a compose service serves canned product HTML through the real `generic` scraper path; a control endpoint (e.g. `PUT /fixtures/{slug}/price`) changes the served price so a scenario can force a drop/rise and trigger an alert. Steps register products whose URL points at this fixture server. Rationale: exercises the real fetch→hash→dedup→extract path deterministically; real retail sites are non-deterministic, bot-protected, and cannot be made to drop a price on command.

- **Time/cadence hooks — dedicated e2e compose profile with tiny intervals + control endpoints** *(harness, Item 13; contract consumed here)*: the e2e profile sets `SCRAPE_INTERVAL_MINUTES=1` and a tiny `ALERT_COOLDOWN_HOURS` (both already `Settings` fields) so beat cadence and cooldown resolve in seconds. Gated test-only control endpoints (enabled only when an `E2E_TEST_HOOKS=true` flag is set) expose: force a scrape now, and reset an alert's cooldown. Rationale: makes scheduling-cadence and 24h-cooldown scenarios observable without wall-clock waits or flakiness; the flag keeps the hooks out of production behaviour.

- **Assertion & isolation — public API only, unique data per scenario**: steps assert **exclusively through the public REST API and UI** — no direct DB/Redis peeking from step definitions. Each scenario provisions its own product via a **unique fixture URL** (e.g. slug suffixed per scenario) so scenarios are independent and need no global reset. Rationale: tests verify observable contract behaviour, stay decoupled from internal storage, and avoid cross-scenario interference on the shared live stack.

- **Notification-channel assertions require a NotificationLog read surface** (scope addition): notification delivery is today only observable via `NotificationLog` rows, but **no public endpoint exposes them** (routes exist only for products/prices/alerts). Add a read endpoint `GET /api/v1/alerts/{alert_id}/notifications` (paginated, `NotificationLogRead` schema) so `email`/`whatsapp` stub deliveries (`status='sent'`) and `webhook` deliveries are assertable via the public API. The `webhook` channel additionally targets the harness **webhook-sink** service URL so the scenario can confirm the POST was received. Rationale: "public API only" assertions need a supported way to observe notifications; a real read endpoint is preferable to a test-only backdoor and is independently useful.

- **Catalogue breadth — full, including non-functional, all executed**: happy-path journeys, negative/error paths, and non-functional scenarios are all authored and all executed via the hooks above. Anything genuinely un-executable is out of scope rather than written as a skipped stub. Rationale: user selected "Execute all via test hooks" — the catalogue's value is that every documented behaviour is enforced.

### Scenario catalogue (author under `docs/behaviour/`, all executed)

Grouped into `.feature` files; every scenario gets a `@PP-E2E-NNN` tag. Indicative coverage:

- **`product_tracking.feature`** — add a tracked product (201); reject duplicate URL (409); deactivate/reactivate; delete cascades (product gone → its prices/alerts 404).
- **`scraping.feature`** — on-demand scrape (`POST /products/{id}/scrape` → 202) produces a `PriceRecord` with `extraction_status=ok`; scheduled scrape fires via 1-minute beat and produces a record (cadence, non-functional); identical fixture HTML on a second scrape is **deduplicated** (no new record); a fixture price change produces a **new** record.
- **`scraping_failures.feature`** *(negative)* — fixture returns 404/500 → `PriceRecord` with `extraction_status=http_error`, no alert; fixture HTML with no price → `extraction_failed`, alert evaluation skipped.
- **`price_history.feature`** — history is queryable and **paginated** (`limit`≤100/`offset`); `limit=101` → 422 (non-functional edge); date-range `from_dt`/`to_dt` filtering.
- **`alerts.feature`** — create `below`/`above` alerts; a fixture price crossing the threshold triggers a notification (`NotificationLog` `status=sent` via the new read endpoint); no crossing → no notification; **cooldown**: second crossing within cooldown does not re-notify, then does after cooldown reset (non-functional).
- **`notification_channels.feature`** — `email` stub → `status=sent`; `webhook` → sink service receives the POST and `status=sent`; `webhook_url` missing → `status=failed`; `whatsapp` stub → `status=sent`; `whatsapp_number` missing → `status=failed` *(negative)*.
- **`rate_limiting.feature`** *(non-functional)* — repeated scrapes of the same fixture domain honour the per-domain min-delay (observable via scrape timing/`202` throttling behaviour exposed by the harness).
- **`ui_journeys.feature`** *(playwright-bdd)* — dashboard renders a product with its latest price; product detail renders the price-history chart; alert manager creates an alert and it appears in the list.

### Tasks

**Tooling**
- [x] Add `pytest-bdd` to `backend/pyproject.toml` `[dependency-groups] dev`; register a `live_api` (or new `e2e`) marker usage for the step tests
- [x] Add `playwright-bdd` to `frontend/package.json` devDependencies; add `bddgen`/`playwright test` wiring and a `test:e2e:bdd` script
- [x] Configure `pytest-bdd` feature discovery to point at `docs/behaviour/` (`bdd_features_base_dir` in `pytest.ini`/`pyproject.toml`); configure `playwright-bdd` `defineBddConfig({ features: '../docs/behaviour/**/*.feature' })`

**Feature catalogue**
- [x] Author `docs/behaviour/*.feature` per the Scenario catalogue above (Given/When/Then), each `Scenario` tagged `@PP-E2E-NNN`
- [x] Create `docs/behaviour/README.md` documenting the Gherkin conventions, the `PP-E2E-NNN` ID scheme, ID allocation, the features→step-modules map, and how to run the suite (`make test-e2e`)

**Backend step definitions** (`backend/tests/e2e/steps/`)
- [x] Implement `pytest-bdd` step definitions covering all backend `.feature` scenarios, asserting **only via the public REST API** (httpx against the running stack), driving the fixture server's price-mutation endpoint and the gated control hooks for scrape/cooldown
- [x] Provision unique per-scenario fixture product URLs (Background/fixture) so scenarios are isolated without a global reset

**Frontend step definitions** (`frontend/tests/e2e/steps/`)
- [x] Implement `playwright-bdd` step definitions for `ui_journeys.feature` against the composed nginx stack (`E2E_BASE_URL=http://localhost`), seeding the required product via the API before UI assertions

**Notification read surface** (needed for public-API notification assertions)
- [x] Add `GET /api/v1/alerts/{alert_id}/notifications` — paginated `NotificationLogRead` list (new `NotificationLogRead` schema in `schemas/notification.py`; service method in a notification/query service; route in `api/v1/alerts.py`)

**Traceability**
- [x] Ensure every step-definition module / scenario references its `@PP-E2E-NNN` tag so the executed test maps 1:1 to the catalogue; add a short traceability table to `docs/behaviour/README.md`

**Harness dependencies (tracked in Item 13, verified here)**
- [x] Confirm the Item 13 e2e compose profile, fixture server (+ price-mutation endpoint), webhook-sink service, `E2E_TEST_HOOKS` control endpoints, `make test-e2e`, and CI job exist and satisfy the contract these steps assume; file the gaps as Item 13 tasks if not

### Test strategy

All four layers (Arrange-Assert-Act for backend tests):

- **Unit** (isolated, no stack): the new `GET /alerts/{id}/notifications` route handler and `NotificationLogRead` schema — mock the session/service; assert pagination envelope, empty list, and 404 for unknown alert. Any step-helper utilities (e.g. unique-URL generator, fixture-price client) unit-tested in isolation.
- **Integration** (real DB, no full compose): the notification-history endpoint against the Postgres testcontainer (`pg_async_client`) — seed `NotificationLog` rows, assert ordering and pagination. `pytest-bdd` feature-discovery config validated (features are collected).
- **Negative** (Arrange-Assert-Act): `scraping_failures.feature` and the missing-`webhook_url`/missing-`whatsapp_number` scenarios in `notification_channels.feature`; `limit=101` → 422; unknown `alert_id` on the notifications endpoint → 404. Feature file with an unknown `@PP-E2E-NNN`/undefined step → runner fails loudly (no silently-skipped scenarios).
- **Live E2E** (`@pytest.mark.live_api` / playwright-bdd against the running stack): the entire executed catalogue is this layer — it runs against the Item 13 e2e compose profile via `make test-e2e` and in the CI e2e job. Acceptance: every `@PP-E2E-NNN` scenario passes; on failure, Playwright HTML report + traces are uploaded as CI artifacts.

### Documentation
- **`docs/behaviour/`** — create: executed Gherkin scenario catalogue (`*.feature`) + `README.md` (conventions, `PP-E2E-NNN` scheme, features→steps map, run instructions)
- **`backend/tests/e2e/steps/`** — create: `pytest-bdd` step definitions
- **`frontend/tests/e2e/steps/`** — create: `playwright-bdd` step definitions
- **`backend/pyproject.toml`** — update: add `pytest-bdd` dev dep + feature-discovery config
- **`frontend/package.json`** — update: add `playwright-bdd` dev dep + `test:e2e:bdd` script
- **`backend/app/schemas/notification.py`** — update: add `NotificationLogRead`
- **`backend/app/api/v1/alerts.py`** — update: add `GET /alerts/{alert_id}/notifications`
- **`docs/decisions/`** — add ADR: executed-BDD approach (pytest-bdd + playwright-bdd), `docs/behaviour/` as canonical feature location, public-API-only assertion strategy, and the test-hook mechanisms
- **`CLAUDE.md`** — update: reference `docs/behaviour/` as the source of truth for expected E2E behaviour; document the `PP-E2E-NNN` convention and `make test-e2e`; note the executed-BDD tooling
- **`CHANGELOG.md`** — add `### Added` entry: executed E2E behaviour specification (Gherkin catalogue run via pytest-bdd + playwright-bdd against the live compose stack; `PP-E2E-NNN` traceability; notification-history read endpoint)

---

## 15. Anti-Blocking: Rotating Residential Proxies, Realistic UA/Headers & Stealth Context

Scheduled/at-scale scraping of real retail sites (Amazon in particular) will draw
CAPTCHAs, rate-limits, and IP bans even now that the DOM-price fallback (2026-07-12,
`amazon.py`) handles missing `ld+json`. Harden the fetch layer so real sources stay
scrapeable in production, not just for a one-off request from a fresh datacenter IP.

**Motivation**: surfaced during the 2026-07-12 Amazon E2E investigation — the current
default Playwright context (`browser.new_context()` with a stock headless UA and no
proxy) works against a cold URL but is trivially fingerprintable and single-IP.

### Design decisions (open)
- Proxy provider + rotation model: per-request vs sticky per-product sessions; managed pool vs BYO list.
- Where the UA/header pool lives (config file vs Settings vs external) and how it's kept current.
- Whether to add a dedicated `BLOCKED` / `CAPTCHA` `ExtractionStatus` (see Item 16 — `selector_miss` is a distinct signal from a block).
- `playwright-stealth` dependency vs hand-rolled init scripts (dependency risk / maintenance).

### Tasks
- [ ] Add proxy configuration to `core/config.py` `Settings` (pool source, rotation strategy, optional per-domain overrides); document in `.env.example`.
- [ ] Wire proxy into both fetch paths: shared httpx client (`scrapers/http_client.py`) and the Playwright context (`amazon.py` → `browser.new_context(proxy=…)`).
- [ ] Rotate proxy per request (or on block detection) rather than a fixed egress IP.
- [ ] Set realistic `User-Agent` + `Accept-Language`/`Sec-CH-*` headers; rotate UA from a maintained pool matched to the browser build.
- [ ] Apply stealth to the Playwright context (`navigator.webdriver`, plugins, languages, WebGL vendor, `chrome` runtime) via init scripts or `playwright-stealth`.
- [ ] Detect block/CAPTCHA responses (robot-check markers, HTTP 429/503) and classify them distinctly (feeds Item 16 + `/products/failing`), then trigger proxy rotation + bounded retry.
- [ ] Per-domain rate limiting / exponential backoff; respect `robots.txt` and ToS constraints.

### Test strategy
- **Unit**: proxy/UA rotation selection is deterministic under a seeded pool; block-marker classifier maps known robot-check HTML + 429/503 to the blocked status; stealth init script injected into the context.
- **Integration**: httpx + Playwright honour a configured proxy (assert egress via a local proxy stub); rotation advances across calls.
- **Live E2E (`live_api`, opt-in)**: a real Amazon scrape through a configured proxy records `ok` — kept out of the default run (external dependency + cost).

### Documentation
- **`core/config.py` / `.env.example`** — proxy + UA settings.
- **`scrapers/http_client.py`, `scrapers/amazon.py`** — proxy/stealth wiring.
- **`docs/decisions/`** — ADR: anti-blocking strategy (proxy model, stealth approach, block-detection taxonomy).
- **`CHANGELOG.md`** — `### Added` entry.

---

## 16. Handle Selector Drift

DOM price extraction (added 2026-07-12) depends on a hardcoded, ordered list of Amazon
CSS selectors (`amazon.py` `_DOM_PRICE_SCRIPT`). Amazon rotates its markup periodically,
so all selectors can go stale at once — silently degrading every Amazon product to
`extraction_failed` while the page itself loads fine (HTTP 200, real title). Detect and
adapt to drift instead of waiting for a user to notice missing prices.

**Motivation**: the 2026-07-12 fix works today but is brittle by construction; a markup
change is a *when*, not an *if*. A "page loaded, title present, no price matched" outcome
is diagnostic of drift specifically and should be distinguishable from a block (Item 15).

### Design decisions (open)
- Config format/location for per-`source_type` selector lists (externalise from code so they can be updated without a redeploy).
- Drift-detection thresholds (what fraction of a source's active products failing over what window constitutes drift).
- Canary product selection + expected-price-range maintenance.

### Tasks
- [ ] Externalise selector lists to config (per `source_type`), versioned and hot-updatable without a code deploy.
- [ ] Add a distinct `selector_miss` extraction outcome: HTTP 200 + a real product title but no selector matched a price — separate from `http_error` and from a block (Item 15).
- [ ] Aggregate drift monitor: flag a spike in `selector_miss`/`extraction_failed` across many products of the *same* `source_type` (extends the `monitoring_service` / `/products/failing` work).
- [ ] Periodic canary scrape of a known-stable product with an expected price range; fail loud (alert) when extraction breaks.
- [ ] Layered extraction fallback chain (ld+json → DOM selectors → embedded state JSON / `meta` tags / regex over `a-offscreen`), first plausible price wins.
- [ ] Golden-HTML regression fixtures: capture real Amazon HTML snapshots, unit-test the extractor against them, refresh on a schedule.

### Test strategy
- **Unit**: extractor against golden-HTML fixtures (current markup + a deliberately-drifted variant → `selector_miss`, not a crash); config-driven selector loading.
- **Integration**: aggregate drift monitor over seeded `PriceRecord` rows (N same-`source_type` products all `selector_miss` in-window → flagged).
- **Live E2E (`live_api`, opt-in)**: canary scrape of a stable product returns a price within the expected band.

### Documentation
- **`scrapers/amazon.py` + new selector config** — externalised selectors + fallback chain.
- **`services/monitoring_service.py`** — drift aggregation (builds on Item 11/`/products/failing`).
- **`docs/decisions/`** — ADR: selector-drift detection & extraction-fallback strategy.
- **`CHANGELOG.md`** — `### Added` entry.

---

## 17. Queued-Scrape Visibility: List Queued/Running Jobs & Their Statuses

There is no first-class, product-facing way to see what scrapes are queued, in-flight, or
failed. `POST /products/{id}/scrape` returns a `task_id` + `status: "queued"` and then the
outcome is only observable indirectly via new `PriceRecord` rows; Flower exists in the dev
stack (`:5555`) but is an ops tool, not an app surface. Give operators/users a view of
scrape-job lifecycle and status.

**Motivation**: during E2E verification the only way to confirm a queued scrape's fate was
to tail worker logs / poll `/prices`. A job-status surface makes queue depth and failures
observable directly.

### Design decisions (open)
- Source of truth: a new persisted `ScrapeJob` table (durable, queryable, survives worker restarts) vs the Celery result backend (already present, but ephemeral/TTL'd) — leaning `ScrapeJob` for durability + rich filtering.
- Retention/pruning policy for job history.
- Native app view vs simply surfacing Flower.

### Tasks
- [ ] Persist task lifecycle: on dispatch create a `ScrapeJob` (product_id, task_id, queue, status `queued`→`started`→`success`/`failure`, enqueued/started/finished timestamps, result summary/error). Update via Celery signals (`task_prerun`/`task_postrun`/`task_failure`) or the result backend.
- [ ] `GET /api/v1/scrape-jobs` — paginated, filterable by `product_id` / `status` / `queue`; and `GET /api/v1/products/{id}/scrape-jobs`.
- [ ] Optionally expose live queue depth per queue (`default`, `playwright`) via Celery `inspect` / broker introspection.
- [ ] Frontend: an activity/"Jobs" view of recent scrape jobs + statuses; a per-product last-scrape status badge on the dashboard.
- [ ] Reconcile with the existing on-demand trigger response (`task_id` + `status`) so it links to the new job record.

### Test strategy
- **Unit**: the new route handler + `ScrapeJobRead` schema (pagination envelope, empty list, filter validation, unknown-product 404); signal handlers transition job status correctly.
- **Integration** (real DB): `ScrapeJob` rows written on dispatch and updated on completion; list endpoints return correct ordering/pagination/filtering.
- **Live E2E**: trigger a scrape → the job appears as `queued`, then transitions to `success`/`failure` and is visible via the API.

### Documentation
- **`backend/app/models/`** — new `ScrapeJob` model + migration.
- **`backend/app/api/v1/`** — new scrape-jobs routes + schema.
- **`backend/app/tasks/scrape.py` / `workers/`** — Celery signal wiring.
- **`frontend/src/`** — jobs/activity view + status badge.
- **`CHANGELOG.md`** — `### Added` entry.

---

## References

- FastAPI docs: https://fastapi.tiangolo.com/
- Celery docs: https://docs.celeryq.dev/
- SQLAlchemy async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Alembic: https://alembic.sqlalchemy.org/
- Vitest: https://vitest.dev/
- React Query: https://tanstack.com/query/latest
- MSW: https://mswjs.io/
- Recharts: https://recharts.org/
