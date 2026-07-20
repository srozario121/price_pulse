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

## 15. Anti-Blocking: Rotating Residential Proxies, Realistic UA/Headers & Stealth Context ✅ COMPLETE

Scheduled/at-scale scraping of real retail sites (Amazon in particular) will draw
CAPTCHAs, rate-limits, and IP bans even now that the DOM-price fallback (2026-07-12,
`amazon.py`) handles missing `ld+json`. Harden the fetch layer so real sources stay
scrapeable in production, not just for a one-off request from a fresh datacenter IP.

**Motivation**: surfaced during the 2026-07-12 Amazon E2E investigation — the current
default Playwright context (`browser.new_context()` with a stock headless UA and no
proxy) works against a cold URL but is trivially fingerprintable and single-IP.

### Implementation workflow (mandatory — complete in order)

1. [x] Create an isolated git worktree before writing any code:
       `git worktree add ../pp-item-15 -b feat/item-15`
2. [x] Implement every task below inside that worktree — never directly on `main`.
3. [x] All quality gates must pass before opening a PR:
       `make test` exits 0 and `make quality` exits 0
       (see `CONTRIBUTING.md` → Pull Request Checklist).
       (Ruff, complexity/MI/Halstead, and the full unit suite pass locally;
       Docker-backed integration + coverage/overlap run in CI.)
4. [x] Raise a Pull Request: `gh pr create`
       **No direct commits to the default branch (`main`) are permitted.**

### Design decisions (resolved)

- **Proxy model — BYO list + per-request rotation, rotate-on-block**: proxies are supplied as a bring-your-own list in `Settings` (comma-separated env, coerced to `list[str]` like `CORS_ORIGINS`); a fresh proxy is selected per request, and on a detected block the fetch rotates to the next proxy and retries. Rationale: simplest to implement and test deterministically; no managed-provider integration or sticky-session state; per-request diversity plus explicit rotate-on-block covers both cold and soft-banned IPs.

- **Block retry — rotate + bounded retry, then persist a distinct status**: on a block/CAPTCHA marker the fetch rotates the proxy and retries up to a configurable budget (`MAX_PROXY_ROTATIONS`, default 2); if still blocked after the budget, the scrape resolves to `BLOCKED`/`CAPTCHA` rather than looping. A **dead/unreachable** proxy (connection error, not a block) rotates to the next proxy and does **not** consume the block-retry budget. Rationale: persistence without unbounded cost; separates infrastructure failure from an actual block.

- **Two new extraction statuses — `BLOCKED` and `CAPTCHA`**: added to `ExtractionStatus` (`models/enums.py`). `BLOCKED` = HTTP 429/503 or IP-ban markers after rotations are exhausted; `CAPTCHA` = a robot-check interstitial (200-status challenge page). Rationale: a block is diagnostically distinct from `extraction_failed` (selector drift, Item 16) and `http_error` (transient).

- **⚠️ Alembic migration IS required — a CHECK constraint restricts `extraction_status` (scoping correction, 2026-07-16)**: migration `0004` added the column with `CheckConstraint("extraction_status IN ('ok', 'extraction_failed', 'http_error')", name="ck_price_record_extraction_status")` on table `price_record`. The earlier "no migration / plain string column" assumption was **wrong** — inserting `'blocked'`/`'captcha'` raises an `IntegrityError`. **Resolution: drop the CHECK constraint entirely** (rather than widen it) so `extraction_status` is a genuinely open string column and future status additions (Item 16 `selector_miss`, and any beyond) need no further DB change — which is what Items 15/16/17's "app-level `StrEnum` additions only" design already assumes. Add a migration `op.drop_constraint("ck_price_record_extraction_status", "price_record", type_="check")` (downgrade recreates it with the original three values). **Cross-item impact**: this single migration unblocks Item 16 (`selector_miss`) and Item 17 (which folds `blocked`/`captcha`/`selector_miss` into job status) too — whichever item merges first should own it; the others then depend on it.

- **Stealth — `playwright-stealth` dependency + custom init-script top-up**: add `playwright-stealth` as the base and layer a small set of versioned `add_init_script()` patches on top (`navigator.webdriver`, plugins, languages, WebGL vendor, `chrome` runtime) for anything the library misses. Rationale: broad out-of-the-box coverage plus full control over gaps; only the Amazon Playwright path consumes it.

- **Config location — `Settings`-based now, external hot-updatable file deferred**: proxy list, rotation/retry knobs, and the UA/header pool live in `core/config.py` `Settings` (env-driven) for Item 15. A mounted, hot-reloadable config file is deferred to a future item, aligned with Item 16's externalised-selector direction. Rationale: consistent with existing config patterns; ships value without file-watch/reload machinery.

- **Shared UA/header pool — one module for both fetch paths**: the existing `_USER_AGENTS` pool in `http_client.py` is consolidated into a single anti-blocking module (`scrapers/anti_blocking.py`) that both the httpx path and the Playwright context import, so UA rotation and the matched `Accept-Language`/`Sec-CH-UA*` header set are identical across paths. Rationale: removes duplication; one place to keep UAs current and matched to the browser build.

- **Block-marker detection in both paths**: a shared classifier (`html`, `status_code`) → `None | BLOCKED | CAPTCHA` runs in **both** the httpx path and the Playwright path, so a 200-status CAPTCHA page (currently mis-classified as `extraction_failed` on the Amazon path) is caught. Rationale: status codes alone miss challenge pages served with HTTP 200.

- **Proxy config normalisation — shared helper**: httpx wants `proxy="http://user:pass@host:port"`; Playwright wants `proxy={"server", "username", "password"}`. A single normaliser converts one BYO entry to both shapes. Rationale: one source of truth for proxy parsing/validation.

- **Monitoring integration — break out block counts on `/products/failing` (this item)**: `monitoring_service.find_failing_products` and `FailingProductRead` are extended to expose the latest failure **category** (blocked/captcha vs other) per product plus aggregate counts, so a block spike is visible on the existing endpoint. The aggregate same-`source_type` drift monitor remains Item 16. Rationale: makes the new signal immediately observable via the surface that already exists, without a new route.

- **robots.txt — unchanged log-and-proceed**: Item 15 does **not** change robots.txt handling; the existing `_check_robots` warning-only behaviour stays. Task 7 is reworded to "extend the existing per-domain rate-limit/back-off" rather than imply new enforcement. Rationale: keeps the item focused on anti-blocking mechanics; compliance enforcement is a separate concern with its own status/tests.

- **Per-domain overrides — out of scope (global pools only)**: one proxy pool and one UA/header pool apply to all domains this item; per-domain proxy/UA/rate overrides are deferred. Rationale: keeps the config surface and test matrix tight.

- **Reuse, not rebuild, existing back-off/rate-limit**: the httpx path already has 3× exponential back-off, `429` `Retry-After` handling, and Redis per-domain min-delay. Item 15 **extends** these (proxy rotation on block, block-marker detection) rather than adding a parallel mechanism. Rationale: avoid duplicating working code.

### Tasks

**Config (`Settings` + `.env.example`)**
- [x] Add proxy settings to `core/config.py` `Settings`: `PROXY_URLS: list[str]` (BYO, comma-separated env coerced like `CORS_ORIGINS`; empty = proxies disabled), `MAX_PROXY_ROTATIONS: int = 2`, and any UA-pool toggle needed. Document each in `.env.example` (note: empty `PROXY_URLS` disables proxying; BYO residential list expected in production).

**Shared anti-blocking module**
- [x] Create `scrapers/anti_blocking.py`: the consolidated UA pool (moved from `http_client._USER_AGENTS`), a matched `Accept-Language`/`Sec-CH-UA*` header builder keyed off the chosen UA, a proxy selector (per-request pick + `next_proxy()` rotation over `PROXY_URLS`), and a proxy-config normaliser producing both the httpx string and the Playwright dict.
- [x] Add a block/CAPTCHA classifier `classify_block(status_code, html) -> ExtractionStatus | None` recognising 429/503 and known robot-check/CAPTCHA HTML markers.

**Extraction statuses**
- [x] Add `BLOCKED = "blocked"` and `CAPTCHA = "captcha"` to `ExtractionStatus` (`models/enums.py`).
- [x] **Alembic migration** dropping the `ck_price_record_extraction_status` CHECK constraint on `price_record` (verified present in migration `0004`). `upgrade`: `op.drop_constraint("ck_price_record_extraction_status", "price_record", type_="check")`; `downgrade`: recreate it with the original three values. Register nothing else — the column stays `String(20)`. This unblocks the new `blocked`/`captcha` values (and Item 16's `selector_miss`).

**Wire the httpx path (`scrapers/http_client.py`)**
- [x] Select a proxy per request from the shared module and pass it to `httpx.AsyncClient(proxy=…)`; use the shared UA + matched headers.
- [x] Run `classify_block` on each response; on a block, rotate proxy and retry within `MAX_PROXY_ROTATIONS`; on exhaustion return a `ScrapedResult` with `BLOCKED`/`CAPTCHA`. Treat a proxy connection error as a dead-proxy rotate (does not consume the block budget).
- [x] Reuse the existing back-off / `Retry-After` / Redis rate-limit logic — do not add a parallel mechanism.

**Wire the Playwright path (`scrapers/amazon.py`)**
- [x] Build the context with `browser.new_context(proxy=…, user_agent=…, extra_http_headers=…)` from the shared module; rotate proxy on block within `MAX_PROXY_ROTATIONS`.
- [x] Apply `playwright-stealth` to the context, then layer the custom `add_init_script()` top-ups (`navigator.webdriver`, plugins, languages, WebGL vendor, `chrome` runtime).
- [x] Run `classify_block` on the loaded page (status + content) before extraction so a 200-status CAPTCHA resolves to `CAPTCHA`, not `extraction_failed`.
- [x] Add `playwright-stealth` to `backend/pyproject.toml` dependencies.

**Monitoring surface**
- [x] Extend `monitoring_service.find_failing_products` (+ `FailingProductRead` in `schemas/product.py`) to expose the latest failure category (blocked/captcha vs other) and aggregate blocked/captcha counts on `GET /products/failing`.

### Test strategy

Arrange-Assert-Act for all backend tests.

- **Unit** (`backend/tests/unit/`, isolated):
  - Proxy selection/rotation is deterministic under a seeded `PROXY_URLS` list; `next_proxy()` advances and wraps; empty list ⇒ proxying disabled (no proxy passed).
  - Proxy-config normaliser emits the correct httpx string and Playwright dict (incl. `user:pass` auth).
  - `classify_block` maps 429/503 and known robot-check/CAPTCHA HTML to `BLOCKED`/`CAPTCHA`, and normal 200 product HTML to `None`.
  - UA/header builder returns a matched `Accept-Language`/`Sec-CH-UA*` set for a given UA; custom stealth init scripts are registered on the context (mocked Playwright).
- **Integration** (`backend/tests/integration/`, real wiring):
  - In-repo **local forward-proxy stub** fixture: assert httpx requests egress **through** the stub, and that a simulated block advances rotation to the next proxy across calls.
  - Playwright context is constructed with the expected `proxy`/`user_agent`/headers (Playwright launch mocked or a lightweight stub) and rotates on block.
  - `find_failing_products` over seeded `PriceRecord` rows returns the correct blocked/captcha category + counts.
- **Negative** (Arrange-Assert-Act):
  - Block persists past `MAX_PROXY_ROTATIONS` ⇒ result is `BLOCKED`/`CAPTCHA` (no infinite loop); every proxy dead/unreachable ⇒ bounded failure with a distinct log, not a hang.
  - Malformed proxy URL in `PROXY_URLS` ⇒ Settings validation error at startup, not a runtime crash mid-scrape.
  - 200-status CAPTCHA page on the Amazon path ⇒ `CAPTCHA`, not `extraction_failed`.
- **Live E2E** (`@pytest.mark.live_api`, opt-in — excluded from the default run):
  - A real Amazon scrape through a configured proxy records `ok`; kept out of CI/default runs (external dependency + proxy cost).

### Documentation
- **`core/config.py` / `.env.example`** — update: `PROXY_URLS`, `MAX_PROXY_ROTATIONS`, UA-pool settings (note empty `PROXY_URLS` disables proxying).
- **`scrapers/anti_blocking.py`** — create: shared UA/header pool, proxy selector/rotator + normaliser, `classify_block`.
- **`scrapers/http_client.py`, `scrapers/amazon.py`** — update: proxy wiring, block detection + rotation, stealth (Amazon).
- **`models/enums.py`** — update: `BLOCKED`, `CAPTCHA` statuses.
- **`backend/alembic/versions/`** — create: migration dropping the `ck_price_record_extraction_status` CHECK constraint (unblocks new extraction-status values).
- **`services/monitoring_service.py`, `schemas/product.py`, `api/v1/products.py`** — update: block-category breakdown + counts on `/products/failing`.
- **`backend/pyproject.toml`** — update: add `playwright-stealth`.
- **`docs/decisions/`** — add ADR: anti-blocking strategy (BYO proxy + per-request rotation, rotate-on-block bounded retry, stealth = playwright-stealth + custom top-up, block-detection taxonomy incl. `BLOCKED`/`CAPTCHA`, Settings-now config).
- **`CLAUDE.md`** — update: environment-variables table (`PROXY_URLS`, `MAX_PROXY_ROTATIONS`); note the new extraction statuses.
- **`CHANGELOG.md`** — add `### Added` entry: anti-blocking fetch hardening (proxy rotation, realistic UA/headers, Playwright stealth, block/CAPTCHA detection + statuses, `/products/failing` block breakdown).

---

## 16. Handle Selector Drift — LLM-Generated Self-Healing Selectors

DOM price extraction (added 2026-07-12) depends on a hardcoded, ordered list of Amazon
CSS selectors (`amazon.py` `_DOM_PRICE_SCRIPT`). Amazon rotates its markup periodically,
so all selectors can go stale at once — silently degrading every Amazon product to
`extraction_failed` while the page itself loads fine (HTTP 200, real title). Rather than
hand-maintain selector lists, **let Claude generate the selector**: when extraction can't
find a price on a page that loaded fine, an LLM examines the (trimmed) HTML and produces a
reusable CSS selector, which is validated, persisted per host, and reused on subsequent
scrapes with **no** further LLM calls. Drift self-heals; a hardcoded list is no longer the
single point of failure.

**Motivation**: the 2026-07-12 fix works today but is brittle by construction; a markup
change is a *when*, not an *if*. A "page loaded, title present, no price matched" outcome
is diagnostic of drift specifically and should be distinguishable from a block (Item 15).
Generating and caching a selector per host turns each drift event into a one-time,
automatically-remediated blip instead of a silent, ongoing degradation.

**Depends on / interplays with**: Item 15 — the `classify_block` block/CAPTCHA classifier
must run **first**; a `BLOCKED`/`CAPTCHA` page has no price and must **never** trigger
selector generation (it would poison the generated selector). `selector_miss` is only
raised for a genuinely-loaded, non-blocked page. This item also extends the same
`/products/failing` monitoring surface Item 15 touches.

### Implementation workflow (mandatory — complete in order)

1. [ ] Create an isolated git worktree before writing any code:
       `git worktree add ../pp-item-16 -b feat/item-16`
2. [ ] Implement every task below inside that worktree — never directly on `main`.
3. [ ] All quality gates must pass before opening a PR:
       `make test` exits 0 and `make quality` exits 0
       (see `CONTRIBUTING.md` → Pull Request Checklist).
4. [ ] Raise a Pull Request: `gh pr create`
       **No direct commits to the default branch (`main`) are permitted.**

### Design decisions (resolved)

- **Approach — LLM-generated, self-healing selectors (not hand-maintained lists)**: when deterministic extraction fails on a loaded page, Claude generates a CSS selector from the page HTML; the selector is validated and cached for reuse. Rationale: markup drift is inevitable; generation-on-drift removes the ongoing maintenance burden and the single-point-of-failure of a static selector list.

- **Page representation — trimmed HTML + structured output**: the generator strips `<script>`/`<style>`/`<svg>`/comments and caps the payload (`SELECTOR_HTML_MAX_BYTES`), then sends the cleaned HTML to Claude and receives a **validated** result via structured output (`client.messages.parse()` / `output_config.format`) — a small schema `{price_selector, currency_selector?, confidence}`. Rationale: cheapest and most deterministic path; reuses HTML the scraper already fetches; no vision cost; structured output guarantees a parseable selector without prompt-scraping.

- **Selector store — DB-backed, per host, versioned, runtime-editable**: a new `SelectorProfile` table keyed by **host** (`amazon.co.uk` and `amazon.com` are distinct — the 2026-07-12 investigation showed regional markup differs), carrying `host`, `source_type`, `price_selector`, `currency_selector`, `status` (`active`/`stale`/`failed`), `version`, `confidence`, `generated_at`, `last_validated_at`, and generation metadata. Alembic migration required. Rationale: selectors are reusable across all products on a host; DB storage makes them queryable, versioned, and editable at runtime without a redeploy (supersedes the original "externalise to a config file" idea).

- **Auth — `ANTHROPIC_API_KEY` via `Settings`/env**: add `ANTHROPIC_API_KEY` (and `ANTHROPIC_MODEL`, default `claude-opus-4-8`) to `core/config.py`; inject the key via `.env`/secrets into the backend **and** the `celery-playwright` worker (which runs generation). A bare `AsyncAnthropic()` reads it from the environment. Rationale: standard for a containerised app; the key is documented in `.env.example` and never committed; `ANTHROPIC_MODEL` makes the tier swappable (e.g. to a cheaper model) without a code change.

- **Model + call shape — `claude-opus-4-8`, single structured call**: selector generation is a single `messages.parse()` call with a modest `max_tokens`, no agent loop and no tools. Generation is infrequent (once per host, then cached), so Opus-tier cost is acceptable; the `ANTHROPIC_MODEL` setting allows dropping to a cheaper model if volume grows. Rationale: the task is a one-shot extraction, the simplest LLM tier.

- **Regeneration execution — async, validate, then promote**: on a `selector_miss` (or a user report), a Celery task regenerates the host's selector **off the scrape path**; the old/hardcoded selector keeps serving meanwhile. A newly-generated selector is **validated** (must extract a plausible numeric price on the current page via the existing `_normalize_price_text`) before it is persisted and promoted to `active`. Bounded attempts (`SELECTOR_MAX_REGEN_ATTEMPTS`) + per-host cooldown (`SELECTOR_REGEN_COOLDOWN_HOURS`) prevent a permanently-broken page from hammering the API. Rationale: keeps scrape latency and correctness decoupled from Anthropic availability; only validated selectors ever go live.

- **Regeneration trigger — first `selector_miss` for a host, plus user report**: a single `selector_miss` for a host marks its profile `stale` and enqueues regeneration (subject to cooldown); a user "report issue" does the same immediately. Rationale: fastest self-heal; the cooldown + bounded attempts prevent churn, so an aggregate threshold/window isn't needed. (A periodic canary scrape is a possible future safety net but is out of scope here.)

- **Scope + graceful fallback — Amazon + generic, Anthropic optional at runtime**: both source types can use a stored LLM selector. Extraction order — Amazon: `ld+json` → stored active selector → legacy hardcoded `_DOM_PRICE_SCRIPT` list → `selector_miss`; generic: product `css_selector` (if set) → stored active host selector → `selector_miss`. If `ANTHROPIC_API_KEY` is unset or generation fails, extraction falls back to today's behaviour and records `selector_miss` — it **never crashes**. Rationale: the new capability is additive; the current working Amazon path stays as a safety net and the `anthropic` dependency is effectively optional at runtime.

- **`selector_miss` extraction status**: add `SELECTOR_MISS = "selector_miss"` to `ExtractionStatus` — HTTP 200, **not** classified as a block/CAPTCHA (Item 15), a plausible product title/content present, but no selector matched a price. No Alembic migration (string column, as in Item 15). Rationale: distinguishes drift from `http_error` (transient), `extraction_failed` (parse error), and `BLOCKED`/`CAPTCHA` (Item 15) so monitoring and the regen trigger can act on it specifically.

- **Monitoring — surface `selector_miss` on `/products/failing`**: extend `monitoring_service`/`FailingProductRead` (co-ordinating with Item 15's block-category work) to break out `selector_miss` counts per host/`source_type`, so a drift spike is visible. Rationale: reuses the existing surface; makes the new signal observable without a new route.

- **Report-issue surface — `POST /api/v1/products/{id}/report-selector-issue`**: flags the product's host profile `stale` and enqueues regeneration (respecting cooldown); returns 202. Rationale: gives users/operators a supported way to force a heal when a price looks wrong, feeding the same async pipeline.

### Tasks

**Config + dependency**
- [ ] Add `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (default `claude-opus-4-8`), `SELECTOR_HTML_MAX_BYTES`, `SELECTOR_MAX_REGEN_ATTEMPTS`, `SELECTOR_REGEN_COOLDOWN_HOURS` to `core/config.py` `Settings`; document each in `.env.example` (note the key must never be committed; empty key disables LLM generation).
- [ ] Add `anthropic` to `backend/pyproject.toml` dependencies.

**Selector store**
- [ ] Create the `SelectorProfile` model (`models/`) keyed by `host`, versioned, with `status`/`confidence`/`generated_at`/`last_validated_at`/metadata; add an Alembic migration.
- [ ] Repository/service helpers to fetch the active profile for a host, mark stale, and persist a new validated version.

**Extraction status**
- [ ] Add `SELECTOR_MISS = "selector_miss"` to `ExtractionStatus` (`models/enums.py`); no DB migration (string column). Confirm no CHECK constraint on `price_records.extraction_status`.

**Selector-generation service**
- [ ] Create `services/selector_generation.py`: trim HTML (strip scripts/styles/svg/comments, cap at `SELECTOR_HTML_MAX_BYTES`), call `AsyncAnthropic().messages.parse()` (model = `ANTHROPIC_MODEL`) with a `{price_selector, currency_selector?, confidence}` schema, and return the parsed result. No API key ⇒ return `None` (generation disabled).
- [ ] Validation: a generated selector must extract a plausible numeric price on the current page (reuse `_normalize_price_text`) before it is persisted/promoted; a failed validation counts against `SELECTOR_MAX_REGEN_ATTEMPTS`.

**Wire into extraction (both paths)**
- [ ] `amazon.py`: after `ld+json`, try the host's stored active selector; then the legacy `_DOM_PRICE_SCRIPT` list; a non-blocked loaded page with no price ⇒ `SELECTOR_MISS`. Gate on Item 15's `classify_block` — a blocked page is never a `selector_miss`.
- [ ] `generic.py`: after the product `css_selector`, try the host's stored active selector; non-blocked loaded page with no price ⇒ `SELECTOR_MISS`. Graceful fallback to existing behaviour when generation is unavailable.

**Async regeneration**
- [ ] `tasks/`: a Celery task that (re)generates a host's selector, validates it, and promotes it — enqueued on the first `selector_miss` for a host and on a user report; honours bounded attempts + per-host cooldown. Runs on the `celery-playwright` worker where the Anthropic key is injected.

**Report-issue endpoint**
- [ ] `POST /api/v1/products/{id}/report-selector-issue` → mark the host profile stale, enqueue regeneration (respecting cooldown), return 202.

**Monitoring**
- [ ] Extend `monitoring_service`/`schemas/product.py`/`api/v1/products.py` to break out `selector_miss` counts per host/`source_type` on `GET /products/failing` (co-ordinate with Item 15).

### Test strategy

Arrange-Assert-Act for all backend tests.

- **Unit** (`backend/tests/unit/`, isolated):
  - HTML-trim helper strips scripts/styles/svg and caps at `SELECTOR_HTML_MAX_BYTES`.
  - Selector-generation service with a **mocked** `AsyncAnthropic` — returns the parsed selector on a good schema; returns `None` when the key is unset; a low-`confidence`/invalid selector is rejected by validation.
  - Extraction against **golden-HTML fixtures**: current Amazon markup extracts `ok`; a deliberately-drifted variant (loaded page, title present, no price) yields `SELECTOR_MISS`, not a crash; a page classified as blocked (Item 15) yields `BLOCKED`/`CAPTCHA`, **not** `SELECTOR_MISS` and **no** regeneration enqueued.
  - Validation helper: a generated selector that extracts a plausible price passes; one that extracts nothing/garbage fails and counts against the attempt budget.
- **Integration** (`backend/tests/integration/`, real DB):
  - `SelectorProfile` lifecycle — generate (mocked LLM) → validate → persist `active` → reuse on a second scrape with **no** LLM call; a `selector_miss` marks the profile `stale` and enqueues regeneration; cooldown/bounded-attempts prevent a second enqueue within the window.
  - `report-selector-issue` marks the host profile stale and enqueues regeneration; unknown product ⇒ 404.
  - `find_failing_products` over seeded rows surfaces `selector_miss` counts per host/`source_type`.
- **Negative** (Arrange-Assert-Act):
  - No `ANTHROPIC_API_KEY` ⇒ scrape still completes with `selector_miss` and no crash; regeneration is a no-op.
  - Anthropic call raises / times out ⇒ generation task fails gracefully, attempt counted, cooldown applied, old selector still serves.
  - Generation returns an invalid/low-confidence selector, or one that fails validation ⇒ not promoted; profile stays on the previous active/hardcoded selector.
  - `report-selector-issue` within cooldown ⇒ 202 but no duplicate enqueue.
- **Live E2E** (`@pytest.mark.live_api`, opt-in — excluded from the default run):
  - A real Amazon scrape whose stored selector is cleared triggers generation through the live Anthropic API, validates, persists, and records `ok`; kept out of CI/default runs (external dependency + API cost).

### Documentation
- **`core/config.py` / `.env.example`** — update: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `SELECTOR_HTML_MAX_BYTES`, `SELECTOR_MAX_REGEN_ATTEMPTS`, `SELECTOR_REGEN_COOLDOWN_HOURS` (key never committed; empty key disables generation).
- **`backend/pyproject.toml`** — update: add `anthropic`.
- **`models/` + Alembic** — create: `SelectorProfile` model + migration.
- **`models/enums.py`** — update: `SELECTOR_MISS` status.
- **`services/selector_generation.py`** — create: trim-HTML + `messages.parse()` generator + validation.
- **`scrapers/amazon.py`, `scrapers/generic.py`** — update: stored-selector extraction layer + `selector_miss`, gated on Item 15's block classifier.
- **`tasks/`** — create: async regeneration task (bounded attempts + cooldown).
- **`api/v1/products.py`, `schemas/product.py`, `services/monitoring_service.py`** — update: `report-selector-issue` endpoint + `selector_miss` breakdown on `/products/failing`.
- **`docs/decisions/`** — add ADR: LLM-generated self-healing selectors (per-host DB store, trimmed-HTML + structured-output generation, async validate-then-promote, `ANTHROPIC_API_KEY` auth, graceful fallback, `selector_miss` taxonomy vs Item 15).
- **`CLAUDE.md`** — update: environment-variables table (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, selector-regen settings); note the new `selector_miss` status and the `report-selector-issue` endpoint.
- **`CHANGELOG.md`** — add `### Added` entry: LLM-generated self-healing price selectors (per-host DB-backed selector store, drift-triggered async regeneration with validation, `selector_miss` status, report-issue endpoint).

---

## 17. Queued-Scrape Visibility: List Queued/Running Jobs & Their Statuses ✅ COMPLETE

There is no first-class, product-facing way to see what scrapes are queued, in-flight, or
failed. `POST /products/{id}/scrape` returns a `task_id` + `status: "queued"` and then the
outcome is only observable indirectly via new `PriceRecord` rows; Flower exists in the dev
stack (`:5555`) but is an ops tool, not an app surface. Give operators/users a view of
scrape-job lifecycle and status.

**Motivation**: during E2E verification the only way to confirm a queued scrape's fate was
to tail worker logs / poll `/prices`. A job-status surface makes queue depth and failures
observable directly.

### Implementation workflow (mandatory — complete in order)

1. [ ] Create an isolated git worktree before writing any code:
       `git worktree add ../pp-item-17 -b feat/item-17`
2. [ ] Implement every task below inside that worktree — never directly on `main`.
3. [ ] All quality gates must pass before opening a PR:
       `make test` exits 0 and `make quality` exits 0
       (see `CONTRIBUTING.md` → Pull Request Checklist).
4. [ ] Raise a Pull Request: `gh pr create`
       **No direct commits to the default branch (`main`) are permitted.**

### Design decisions (resolved)

- **Source of truth — a new persisted `ScrapeJob` table**: durable, queryable, survives worker/Redis restarts, and supports rich filtering. The Celery result backend (ephemeral, TTL'd, poor at filtering) is **not** the source of truth. Rationale: the result backend loses history on a Redis flush and cannot be filtered by product/status/queue; a table is the only durable, indexable surface.

- **Tracking scope — BOTH on-demand and scheduled scrapes, wired via Celery signals**: `scrape_product` is dispatched from two independent paths — the on-demand API endpoint (`api/v1/prices.py::trigger_scrape` → `scrape_product.apply_async`) **and** the RedBeat beat scheduler (`tasks/schedule.py` `RedBeatSchedulerEntry(task="app.tasks.scrape.scrape_product")`, fired worker-side with **no** API code path). To capture both uniformly, job lifecycle is driven by Celery signals rather than endpoint code. Rationale: the 30-minute scheduled cadence is the bulk of all scrapes; recording only API-triggered scrapes would leave the Jobs view mostly empty and hide exactly the failures this item exists to surface.

- **Producer/consumer signal split**: row **creation** happens producer-side on `before_task_publish` (fires in the API process for on-demand and in the beat process for scheduled dispatch — both have the task id + args before the message hits the broker); status **transitions** happen worker-side on `task_prerun` (→ `started`) and `task_postrun` (finalise, using the `state` arg). Rationale: `before_task_publish` is the only signal that fires for *both* dispatch paths at enqueue time; `task_prerun`/`postrun` are the worker-side lifecycle hooks. This closes the producer→consumer gap where a `queued` row could otherwise never be created for scheduled scrapes.

- **Signal handlers filter to `scrape_product` and never fail dispatch/execution**: every handler ignores non-`scrape_product` senders (so `send_notification`, `schedule` tasks create no rows) and wraps all DB work in try/except that logs and continues — a `ScrapeJob` write must **never** break scraping or notification delivery (mirrors the existing "never fail the request on error" pattern in `products.py` schedule registration and the guarded `on_worker_ready` handler). Rationale: observability is additive; a bug in job tracking cannot be allowed to take down the core pipeline.

- **Signal DB writes use a dedicated *synchronous* SQLAlchemy session (not `AsyncSessionLocal` + `asyncio.run()`)**: the worker runs the `celery-aio-pool` `AsyncIOPool`, so `task_prerun`/`task_postrun` fire while an event loop is already running — calling `asyncio.run()` there raises `RuntimeError: asyncio.run() cannot be called from a running event loop`. A small sync engine/session (sync driver over the same Postgres) is used exclusively for `ScrapeJob` writes in signal handlers. Rationale: `schedule.py`'s `asyncio.run()` pattern works only because `worker_ready` fires *before* the loop is processing tasks; the per-task signals do not have that guarantee, so a sync path is required to avoid loop re-entrancy.

- **Status model — folds the extraction outcome into the job status**: `ScrapeJobStatus` (`queued` → `started` → `success` / `failure`). A task that runs to completion is `success` **only** when the scrape produced a usable price (`extraction_status == "ok"`); any non-`ok` outcome (`http_error`, `extraction_failed`, `selector_miss`, `blocked`, `captcha`) **and** a raised/timed-out task both resolve to `failure`. The raw `scrape_product` return value is preserved in `extraction_status` and any exception text in `detail`, so "task errored" vs "ran but found no price" stays distinguishable in the row even though both read as `failure`. Rationale: the user chose a single "did this scrape work" signal for the badge/list; the detail fields retain the diagnostic breakdown. Mapping is done in `task_postrun` off the `state` arg (`SUCCESS` → map by retval; `FAILURE` → `failure` + `detail`; `RETRY` → stay `started`, do not finalise).

- **`ScrapeJob` shape** (`models/scrape_job.py`, new): `id` (BigInt PK); `product_id` (BigInt FK → `product.id`, `ondelete="CASCADE"`, matching `PriceRecord`/`PriceAlert`; job history dies with the product); `task_id` (String(36), **unique**, indexed — Celery UUID and the join key to the trigger response); `queue` (String(32) — `default`/`playwright`); `trigger` (String(16) — `on_demand`/`scheduled`, set from a task header at the API call-site, defaulting to `scheduled`); `status` (String(20), plain string + `ScrapeJobStatus` StrEnum, matching the existing `extraction_status` string-column convention — no native DB enum, cheap to extend); `extraction_status` (String(20), nullable — the scrape retval); `detail` (String, nullable — error text / summary); `retries` (Integer, default 0, from `task.request.retries`); `enqueued_at` / `started_at` / `finished_at` (DateTime(tz), nullable except `enqueued_at`). Indexes: `ix_scrape_job_product_enqueued (product_id, enqueued_at)`, `ix_scrape_job_status (status)`, unique on `task_id`. **Alembic migration required** (new table). Rationale: mirrors existing model conventions (BigInt keys, tz-aware timestamps, cascade delete, string status columns).

- **Idempotent upsert keyed by `task_id`**: `scrape_product` has `acks_late=True` and `max_retries=3`, so the same `task_id` can be re-published (retry) and re-run (broker redelivery on worker crash). All handlers **upsert by `task_id`** — `before_task_publish` inserts-or-ignores, `task_prerun`/`postrun` update the existing row and bump `retries` — so a retried/redelivered task yields exactly **one** row, not duplicates. Rationale: `acks_late` + retries guarantee repeated signal firings for one logical job; the unique `task_id` constraint plus upsert keeps the record singular.

- **Product-already-deleted at publish time — best-effort, tolerated**: if `before_task_publish` fires for a `product_id` whose row is already gone (deleted between schedule fire and publish), the FK insert is caught and skipped (logged), and dispatch proceeds normally. Rationale: consistent with "never fail dispatch"; a missing product simply has no job row.

- **Retention — periodic prune task**: a Celery beat task (`prune_scrape_jobs`) deletes `ScrapeJob` rows older than `SCRAPE_JOB_RETENTION_DAYS` (new `Settings` field, default `7`), registered on the static beat schedule (daily). Rationale: at a 30-minute cadence × every active product the table grows unbounded; a configurable time-based prune bounds it with one simple, testable task.

- **Live queue depth — optional, best-effort, clearly separable**: `GET /api/v1/scrape-jobs/queue-depth` (Celery `inspect` / broker introspection for `default` + `playwright`) is an **optional** enhancement, not a gate on the item. It returns best-effort data and degrades to an empty/unknown payload if no worker responds. Rationale: `inspect` reliability under the aio pool is uncertain and worker-availability-dependent; the durable table already satisfies the core visibility goal, so introspection is additive and may be deferred without blocking the item.

- **Reconciliation with the existing trigger response — `task_id` is the join key**: the existing `ScrapeJobResponse` (`task_id` + `status: "queued"` + `product`) is unchanged in shape; because `before_task_publish` creates the `ScrapeJob` with that same `task_id`, the client maps the 202 response 1:1 to the durable job via `GET /api/v1/scrape-jobs?task_id=…`. The list endpoint therefore supports a `task_id` filter. Rationale: no breaking change to the trigger contract; the row is discoverable by the id the caller already holds.

### Tasks

**Model + migration**
- [x] Create `ScrapeJobStatus` StrEnum (`queued`/`started`/`success`/`failure`) in `models/enums.py`.
- [x] Create `models/scrape_job.py` `ScrapeJob` per the resolved shape (BigInt keys, `product_id` FK `ondelete=CASCADE`, unique `task_id`, string `status`/`extraction_status`, `trigger`, `retries`, three tz-aware timestamps, the three indexes). Add the back-reference on `Product` if a relationship is wanted (optional — endpoints query by `product_id` directly).
- [x] Alembic migration creating `scrape_job` + indexes; register the model import in `alembic/env.py` if not auto-picked-up.

**Config**
- [x] Add `SCRAPE_JOB_RETENTION_DAYS: int = 7` to `core/config.py` `Settings`; document in `.env.example`.

**Signal wiring (both dispatch paths)**
- [x] Create `workers/scrape_job_signals.py` (imported by `workers/celery_app.py` so handlers register): a dedicated **sync** SQLAlchemy engine/session for `ScrapeJob` writes; `before_task_publish` → upsert `queued` row (filter to `scrape_product`; read `product_id` from args; set `queue`, `trigger` from headers, `enqueued_at`); `task_prerun` → `started` + `started_at` + `retries`; `task_postrun` → finalise off `state` (SUCCESS → map retval to `success`/`failure` + store `extraction_status`; FAILURE → `failure` + `detail`; RETRY → leave `started`) + `finished_at`. Every handler filters to `scrape_product` and is fully guarded (log-and-continue; never raise).
- [x] Pass a `trigger="on_demand"` marker (task header/kwarg) from `api/v1/prices.py::trigger_scrape` so `before_task_publish` can distinguish it from the scheduled default.

**API**
- [x] `GET /api/v1/scrape-jobs` — `PaginatedResponse[ScrapeJobRead]`, filterable by `product_id` / `status` / `queue` / `task_id`; default sort `enqueued_at DESC`; `limit` capped at 100 (reuse `PaginatedResponse`).
- [x] `GET /api/v1/products/{id}/scrape-jobs` — same envelope scoped to one product; **404** if the product does not exist.
- [x] `ScrapeJobRead` schema in `schemas/scrape_job.py` (mirrors the model read fields).
- [x] *(optional)* `GET /api/v1/scrape-jobs/queue-depth` — best-effort Celery `inspect` per queue; degrades gracefully when no worker answers.

**Retention**
- [x] `tasks/maintenance.py` (or extend `tasks/schedule.py`) `prune_scrape_jobs` task deleting rows older than `SCRAPE_JOB_RETENTION_DAYS`; add a daily entry to the static beat schedule.

**Frontend**
- [x] `api/client.ts` methods + `ScrapeJobRead` type (`src/api/types.ts`); `useScrapeJobs` react-query hook.
- [x] A "Jobs"/activity view listing recent scrape jobs + statuses (route + page); a per-product **last-scrape status badge** on the Dashboard rows (queued/started/success/failure).
- [x] MSW handlers for the new endpoints in `tests/mocks/handlers.ts`.

### Test strategy

Arrange-Assert-Act for all backend tests.

- **Unit** (`backend/tests/unit/`, isolated — mock session/inspect):
  - `ScrapeJobRead` schema + list route handler: pagination envelope, empty list, `status`/`queue`/`task_id` filter validation, `limit=101` → 422.
  - Signal handlers (mocked sync session): `before_task_publish` for `scrape_product` inserts a `queued` row; a non-`scrape_product` sender inserts nothing; `task_postrun` maps `state=SUCCESS`+retval `"ok"` → `success`, retval `"http_error"`/`"selector_miss"` → `failure` (folded) with `extraction_status` preserved, `state=FAILURE` → `failure` + `detail`, `state=RETRY` → stays `started`; a DB error inside any handler is swallowed (no raise).
  - `prune_scrape_jobs` computes the correct cut-off from `SCRAPE_JOB_RETENTION_DAYS`.
  - Frontend (`frontend/tests/unit/`): status-badge component renders each status; `useScrapeJobs` hook parses the paginated envelope; Jobs view renders rows (MSW).
- **Integration** (`backend/tests/integration/`, real Postgres testcontainer `pg_async_client`):
  - Full lifecycle: publish → `queued` row; prerun → `started`; postrun → `success`/`failure` with correct timestamps and `extraction_status`. Both the on-demand call-site and a simulated scheduled dispatch produce a row (proving both paths are covered).
  - Idempotency: a retried task (same `task_id`, `retries` bumped) yields exactly **one** row, `retries` incremented — no duplicate.
  - List endpoints: correct ordering (`enqueued_at DESC`), pagination, and each filter (`product_id`/`status`/`queue`/`task_id`).
  - `prune_scrape_jobs` deletes only rows older than the retention window; recent rows survive.
  - Frontend (`frontend/tests/integration/`, MSW): Jobs view + badge integrate against mocked endpoints.
- **Negative** (Arrange-Assert-Act):
  - `GET /products/{id}/scrape-jobs` for an unknown product → 404; `GET /scrape-jobs?product_id=<absent>` → empty list (200, not 404); `limit=101` → 422.
  - `before_task_publish` for an already-deleted `product_id` → FK insert caught, dispatch still succeeds, no row leaked and no crash.
  - Signal-handler DB failure → logged, the scrape task still runs and persists its `PriceRecord` (job tracking never breaks the pipeline).
  - Task raises past `max_retries` / hits the soft-time-limit → row resolves to `failure` with `detail`, not stuck `started`.
  - `queue-depth` with no responsive worker → 200 with an empty/unknown payload, not a hang or 500.
- **Live E2E** (`@pytest.mark.live_api`, against the running compose stack):
  - `POST /products/{id}/scrape` → the job appears via `GET /scrape-jobs?task_id=…` as `queued`, then transitions to `started` and finally `success`/`failure`, visible through the public API.
  - A scheduled scrape (1-minute e2e cadence, Item 13 overlay) produces a `ScrapeJob` row with `trigger=scheduled` — proving the signal path covers beat-fired scrapes. *(Add a `@PP-E2E-NNN` scenario under `docs/behaviour/` if the executed-BDD catalogue is extended.)*

### Documentation
- **`backend/app/models/enums.py`** — update: `ScrapeJobStatus`.
- **`backend/app/models/scrape_job.py`** — create: `ScrapeJob` model.
- **`backend/alembic/versions/`** — create: `scrape_job` table migration.
- **`backend/app/core/config.py` / `.env.example`** — update: `SCRAPE_JOB_RETENTION_DAYS`.
- **`backend/app/workers/scrape_job_signals.py`** — create: signal handlers + dedicated sync session.
- **`backend/app/workers/celery_app.py`** — update: import the signals module so handlers register.
- **`backend/app/api/v1/prices.py`** — update: pass `trigger="on_demand"` header on the on-demand dispatch.
- **`backend/app/api/v1/scrape_jobs.py`** — create: list + per-product routes (+ optional `queue-depth`); register in `api/v1/router.py`.
- **`backend/app/schemas/scrape_job.py`** — create: `ScrapeJobRead`.
- **`backend/app/tasks/maintenance.py`** (or `tasks/schedule.py`) — create/update: `prune_scrape_jobs` + daily beat entry.
- **`frontend/src/api/client.ts`, `src/api/types.ts`, `src/hooks/useScrapeJobs.ts`, `src/pages/` (Jobs view), `src/components/` (status badge), `tests/mocks/handlers.ts`** — create/update: jobs view, badge, hook, MSW handlers.
- **`docs/decisions/`** — add ADR: scrape-job visibility (durable `ScrapeJob` table over the result backend, signal-driven lifecycle for both dispatch paths, sync-session-in-signals under the aio pool, extraction folded into status, time-based retention).
- **`CLAUDE.md`** — update: API-layer section (new `/scrape-jobs` routes); environment-variables table (`SCRAPE_JOB_RETENTION_DAYS`); note the `ScrapeJob` lifecycle and signal wiring.
- **`CHANGELOG.md`** — add `### Added` entry: queued-scrape visibility (durable `ScrapeJob` table, Celery-signal lifecycle tracking for on-demand + scheduled scrapes, `/scrape-jobs` list endpoints, retention prune task, frontend Jobs view + per-product status badge).

---

## 18. Configurable Monitoring Sources — eBay, Currys, John Lewis & Facebook Marketplace Presets (UK) ✅ COMPLETE

Price Pulse can only monitor two source types today: `amazon` (Playwright path) and
`generic` (CSS-selector path). The scraping layer already hints at more — the
`SourceType` enum in **both** `models/product.py` (native Postgres `source_type_enum`)
and `scrapers/registry.py` lists `ebay` and `currys`, but **neither has a registered
scraper**, so `get_scraper("ebay")` / `get_scraper("currys")` raise `UnknownSourceError`
and any product created with those types fails every scrape. `john_lewis` does not exist
anywhere yet.

This item (1) delivers working scrapers for **eBay UK**, **Currys**, **John Lewis**, and
**Facebook Marketplace** (UK listings), (2) makes the set of monitoring sources
**configurable from the application** — a managed registry of source presets rather than
hardcoded enum branches — shipping the four new sources plus the existing `amazon`/`generic`
as built-in presets, and (3) schedules a **deep-research task** to catalogue other major
UK-based e-commerce sites as candidate future presets. **Scope is UK-based sources only**
for this item; non-UK sources are out of scope.

**Facebook Marketplace caveat**: unlike the retailers, Marketplace is a login-walled C2C
platform with aggressive bot-protection and per-listing (not fixed-catalogue) pricing;
listings expire/vanish and there is no `ld+json` price. Treat it as the hardest source —
it almost certainly needs the Playwright path plus the Item 15 anti-blocking work, and its
feasibility (auth handling, ToS/robots posture) is itself an open question to settle in
plan-review before committing to a full scraper. Consider gating it behind its own
sub-decision rather than assuming parity with the retail scrapers.

**Motivation**: the platform's value scales with the number of retailers it can watch.
The enum already advertises `ebay`/`currys` as if supported, which is a latent trap
(products created against them silently fail). Turning source types into a configurable,
preset-driven surface — instead of an enum + `if source_type == …` ladder that needs a
code change and a DB migration for every new retailer — makes onboarding a new UK retailer
a data/config change, and makes the currently-broken `ebay`/`currys` types actually work.

**Depends on**: **Item 15 (Anti-Blocking) — must be merged first.** The Facebook
Marketplace scraper is built on Item 15's shared anti-blocking module (proxy rotation,
stealth) and its `BLOCKED`/`CAPTCHA` extraction statuses (its login wall / bot-check must
classify as `blocked`/`captcha`, never `extraction_failed`). The three retailer scrapers
(eBay UK, Currys, John Lewis) and the preset registry have **no** Item 15 dependency and
may be built in parallel; only the Marketplace scraper task is gated on Item 15 landing.
Interplays with Item 16 (`selector_miss`) and Item 17 (`ScrapeJob`) on the shared
`/products/failing` monitoring surface — coordinate if either is merged first.

### Implementation workflow (mandatory — complete in order)

1. [x] Create an isolated git worktree before writing any code:
       `git worktree add ../pp-item-18 -b feat/item-18`
2. [x] Implement every task below inside that worktree — never directly on `main`.
3. [x] All quality gates must pass before opening a PR:
       `make test` exits 0 and `make quality` exits 0
       (see `CONTRIBUTING.md` → Pull Request Checklist).
4. [x] Raise a Pull Request: `gh pr create` — merged as PR #8 (squash `5e6bd9f`).
       **No direct commits to the default branch (`main`) are permitted.**

### Design decisions (resolved)

Resolved via plan-review on 2026-07-16. All "open design questions" are now settled.

- **Config layer — DB-backed `SourcePreset` table (runtime-editable), not a config file or `Settings`**: a new table keyed by preset `key`/`source_type`, carrying `label`, `host_patterns`, extraction `strategy` (`generic`/`amazon`/dedicated scraper), `default_css_selector`/`default_css_selector_currency`, target Celery `queue`, `enabled` flag, and `version`. Seeded with six built-ins (`amazon`, `generic`, `ebay`, `currys`, `john_lewis`, `facebook_marketplace`). Alembic migration required. Rationale: mirrors Item 16's runtime-editable `SelectorProfile` direction; onboarding a new retailer becomes a data change, and the currently-broken `ebay`/`currys` types resolve to real scrapers via the registry.

- **`product.source_type` — migrate native Postgres enum → validated `String` column**: drop the `source_type_enum` native type and store `source_type` as `String`, validated at the API/schema boundary against the enabled preset registry (not a Python `Enum`). Consistent with the `extraction_status` string-column convention (Items 15–17) and a prerequisite for data-driven presets. Alembic migration converts `source_type_enum` → `String` (preserving existing values) and drops the enum type. Rationale: eliminates an `ALTER TYPE … ADD VALUE` migration per new retailer; the registry becomes the single source of truth for valid source types.

- **`source_type` stays an explicit field — presets validate, no host auto-detection**: the caller still supplies `source_type` on `POST /products`; validation rejects any value that is not a known **enabled** preset key (422). No URL-host→preset inference resolver in this item. Rationale: smallest correct scope; avoids host-matching ambiguity rules; the preset registry's job here is validation + strategy/queue resolution, not inference. (Host inference can be a later additive item.)

- **Reconcile the two `SourceType` definitions into one registry-driven source of truth**: the divergent `SourceType` enums in `models/product.py` (native-enum-backed, lowercase) and `scrapers/registry.py` (uppercase `StrEnum`) are both removed. `get_scraper` and `queue_for_source_type` resolve from the `SourcePreset` registry; schema validation resolves from the same registry. Rationale: today the two enums can drift and neither is the authority; a single DB-backed registry removes the divergence and the `_REGISTRY`/`_PLAYWRIGHT_SOURCE_TYPES` hardcoding.

- **Queue routing becomes data-driven (preset-carried), not a hardcoded `frozenset`**: each preset declares its Celery `queue`. Per-source resolution: eBay UK → `default` (httpx + `ld+json`); Currys → `playwright` (React/SPA); John Lewis → `playwright` (React/SPA); Facebook Marketplace → `playwright`; `amazon` → `playwright`; `generic` → `default`. `queue_for_source_type` reads the preset's `queue`. Rationale: adding a browser-required retailer no longer needs a code change to a `frozenset`.

- **Facebook Marketplace — FULL scraper this item, hard-gated on Item 15**: implemented as a Playwright scraper on the `playwright` queue, consuming Item 15's shared anti-blocking module (proxy rotation + stealth) and its `BLOCKED`/`CAPTCHA` statuses so a login wall / bot-check classifies correctly (never `extraction_failed`). Per-listing (expiring) price extraction; no `ld+json`. The preset ships **enabled**. The ToS / robots / auth-handling risk assessment is captured in the ADR. Rationale: user selected a full scraper; sequencing it after Item 15 avoids duplicating the anti-blocking module and gives it the block/CAPTCHA taxonomy its login wall requires.

- **Definition of done — all four test layers, with per-retailer `@pytest.mark.live_api` gated and opt-in**: unit (golden-HTML fixtures per source), integration (real-DB registry + product-creation + queue-routing), negative (disabled/unknown key → 422; FB login-wall fixture → `blocked`/`captcha`), and one live E2E scrape per retailer marked `@pytest.mark.live_api` (excluded from the default run, external + bot-protected). Rationale: matches the repo's four-layer standard; golden-HTML keeps CI deterministic while the gated live checks give real-URL acceptance.

- **Deep-research catalogue — authored during implementation, committed in-worktree**: the UK e-commerce candidate-source research (`docs/research/uk-ecommerce-sources.md`) is produced as a task inside Item 18's worktree and committed alongside the scrapers — not run before planning nor split to a follow-up. Rationale: keeps the research deliverable versioned with the feature that motivates it; it is documentation, not scraper implementation.

- **`css_selector_currency` schema gap (scope addition)**: the model already has `css_selector_currency` but `ProductBase`/`ProductCreate` expose only `css_selector`. Since presets now carry `default_css_selector_currency`, add `css_selector_currency` to the product schemas so a generic-source product can override it. Rationale: surfaced during plan-review; the field is otherwise unreachable via the API despite existing on the model and in the generic scraper.

### Tasks

**Source-preset registry (DB-backed)**
- [ ] Create the `SourcePreset` model (`models/source_preset.py`): `key`/`source_type`
      (String, unique), `label`, `host_patterns` (list — JSON/array column), `strategy`
      (`generic`/`amazon`/dedicated), `default_css_selector`,
      `default_css_selector_currency`, `queue` (String), `enabled` (Boolean), `version`,
      tz-aware `created_at`/`updated_at`. Register the import in `alembic/env.py`.
- [ ] Alembic migration creating the `source_preset` table **and** seeding the six built-in
      presets: `amazon`→playwright, `generic`→default, `ebay`→default, `currys`→playwright,
      `john_lewis`→playwright, `facebook_marketplace`→playwright (enabled). Idempotent seed.
- [ ] Repository/service helpers (`services/source_preset_service.py`): fetch enabled
      presets, resolve a preset by `source_type`/key, and validate a candidate `source_type`
      against the enabled set.

**Migrate `source_type` off the native enum**
- [ ] Alembic migration converting `product.source_type_enum` → `String` (preserve existing
      values), dropping the native `source_type_enum` type; update `models/product.py` to a
      plain `Mapped[str]` String column.
- [ ] Remove the two divergent `SourceType` enums (`models/product.py`,
      `scrapers/registry.py`); update `schemas/product.py` so `source_type` is a validated
      `str` checked against the enabled-preset registry (unknown/disabled key → 422). Add
      `css_selector_currency` to `ProductBase`/`ProductCreate`/`ProductUpdate` (model field
      exists but is unreachable via the API today).

**Registry — data-driven resolution**
- [ ] Replace the hardcoded `_REGISTRY` / `_PLAYWRIGHT_SOURCE_TYPES` / `SourceType` lookups
      in `scrapers/registry.py` so `get_scraper` resolves the scraper class from the preset's
      `strategy` and `queue_for_source_type` reads the preset's `queue` (queue routing is
      data-driven, not a `frozenset`). A disabled/unknown key raises `UnknownSourceError`.

**Sources endpoint**
- [ ] `GET /api/v1/sources` — returns the enabled preset list (`key`, `label`, `queue`) so
      the frontend "add product" form is populated from the backend registry. New
      `SourcePresetRead` schema; register the route in `api/v1/router.py`.

**New retailer scrapers (UK)**
- [ ] Implement and register an **eBay UK** scraper (`scrapers/ebay.py`) — `ld+json` /
      structured-data extraction on the httpx path (`default` queue); DOM/selector fallback.
- [ ] Implement and register a **Currys** scraper (`scrapers/currys.py`) — Playwright path
      (React/SPA, `playwright` queue); extract price + currency.
- [ ] Implement and register a **John Lewis** scraper (`scrapers/john_lewis.py`) — Playwright
      path (React/SPA, `playwright` queue); extract price + currency.
- [ ] **(Gated on Item 15 merged)** Implement and register a **Facebook Marketplace** scraper
      (`scrapers/facebook_marketplace.py`) — Playwright path (`playwright` queue), per-listing
      price extraction, built on Item 15's shared anti-blocking module (proxy rotation +
      stealth). Its login wall / bot-check must classify via Item 15's `classify_block` as
      `BLOCKED`/`CAPTCHA`, never `extraction_failed`. Ship the preset **enabled**. Capture the
      ToS / robots / auth risk assessment in the ADR.
- [ ] Each scraper reuses the shared `http_client` (and, for the Playwright scrapers, the
      Item 15 anti-blocking module) rather than adding a parallel fetch mechanism.

**Deep research — other major UK e-commerce sites**
- [ ] Perform a deep-research pass (in-worktree) on other major **UK-based** e-commerce
      retailers as candidate future presets (e.g. Argos, Very, AO, Sainsbury's/Tesco/ASDA
      groceries, ASOS, Next, Boots, B&Q, Screwfix — validate this list during research).
      For each candidate capture: primary domain(s), whether prices are exposed via
      `ld+json`/structured data or require a browser, bot-protection posture, robots.txt
      stance, and rough scraper effort. Record findings in
      `docs/research/uk-ecommerce-sources.md` and propose a prioritised shortlist (a
      research/documentation deliverable, not implementation of those scrapers).

**Monitoring / housekeeping**
- [ ] Ensure `monitoring_service.find_failing_products` and the `/products/failing` surface
      correctly attribute failures per new `source_type` (co-ordinate with Items 15/16 if
      those are merged).

### Test strategy

Arrange-Assert-Act for all backend tests.

- **Unit** (`backend/tests/unit/`, isolated):
  - Preset registry resolves `ebay`/`currys`/`john_lewis`/`facebook_marketplace`/`amazon`/
    `generic` to the correct scraper class and Celery queue; an unknown/disabled key raises
    `UnknownSourceError`.
  - `source_preset_service` validation: a known-enabled key passes; a disabled or unknown
    key is rejected.
  - Each new scraper extracts price + currency from a **golden-HTML fixture** of that
    source's product/listing page; a fixture with no price yields the correct non-`ok`
    extraction status (not a crash), consistent with Items 15/16 taxonomy. For Facebook
    Marketplace, also assert a login-wall/challenge fixture resolves via Item 15's
    `classify_block` to `blocked`/`captcha`, **not** `extraction_failed`.
  - `queue_for_source_type` returns the preset-declared queue for each source type.
  - `schemas/product.py` accepts `css_selector_currency`; `source_type` string validation
    rejects a disabled/unknown key.
- **Integration** (`backend/tests/integration/`, real Postgres testcontainer `pg_async_client`):
  - The `source_type_enum` → `String` migration runs and existing product rows retain their
    values; `source_type` is a plain string afterward.
  - `SourcePreset` seed migration populates the six built-ins; `source_preset_service`
    reads them back.
  - Creating a product with each new `source_type` persists and validates via the
    string/registry path; on-demand and scheduled dispatch route to the queue the preset
    declares.
  - `GET /api/v1/sources` returns the seeded enabled presets (key, label, queue).
- **Negative** (Arrange-Assert-Act):
  - Product created with a disabled/unknown source key → 422 validation error, not a silent
    scrape failure (fixes today's `ebay`/`currys` `UnknownSourceError`-at-scrape-time trap).
  - A Facebook Marketplace login-wall/challenge fixture → `blocked`/`captcha`, not
    `extraction_failed`.
  - A fixture with markup but no extractable price → the correct non-`ok` status per source,
    no crash.
- **Live E2E** (`@pytest.mark.live_api`, opt-in — excluded from the default run):
  - One live product URL per retailer (eBay UK, Currys, John Lewis) scrapes to `ok`; kept
    out of CI/default runs (external dependency, bot-protection, non-determinism). A live
    Facebook Marketplace check is included (gated behind Item 15's proxy/stealth config)
    and likewise `@pytest.mark.live_api`.

### Documentation
- **`backend/app/models/source_preset.py`** — create: DB-backed `SourcePreset` model.
- **`backend/app/services/source_preset_service.py`** — create: preset resolution +
  `source_type` validation helpers.
- **`backend/app/schemas/source_preset.py`** — create: `SourcePresetRead` schema.
- **`backend/app/scrapers/registry.py`** — update: data-driven `get_scraper` /
  `queue_for_source_type` from the preset registry; remove the local `SourceType` enum,
  `_REGISTRY`, and `_PLAYWRIGHT_SOURCE_TYPES`.
- **`backend/app/scrapers/ebay.py`, `currys.py`, `john_lewis.py`** — create: UK retailer
  scrapers (eBay httpx+`ld+json`; Currys/John Lewis Playwright).
- **`backend/app/scrapers/facebook_marketplace.py`** — create (Item 15 merged first):
  Playwright Marketplace listing scraper on the anti-blocking module; ships enabled.
- **`backend/app/models/product.py`** — update: `source_type` → plain `String` column;
  remove the native `SourceType` enum.
- **`backend/app/schemas/product.py`** — update: `source_type` validated against the enabled
  preset registry; add `css_selector_currency` to product schemas.
- **`backend/alembic/versions/`** — create: (1) `source_type_enum` → `String` migration
  dropping the native type; (2) `source_preset` table + built-in seed migration.
- **`backend/app/api/v1/sources.py`, `backend/app/api/v1/router.py`** — create/update:
  `GET /api/v1/sources` enabled-presets endpoint.
- **`frontend/src/`** — update: source dropdown populated from `GET /api/v1/sources`
  (types + client method + form); MSW handler for the new endpoint in
  `tests/mocks/handlers.ts`.
- **`docs/research/uk-ecommerce-sources.md`** — create: deep-research catalogue of major UK
  e-commerce sites + prioritised shortlist of next presets.
- **`docs/decisions/`** — add ADR: configurable monitoring sources (DB-backed preset
  registry, native-enum→String migration, queue-in-preset routing, explicit-`source_type`
  validation, Facebook-Marketplace-on-Item-15, UK scope).
- **`CLAUDE.md`** — update: scraping-layer section to note the preset registry and the new
  UK source types; note `source_type` is now a validated string; scope note that sources
  are UK-only for now.
- **`CHANGELOG.md`** — add `### Added` entry: configurable monitoring sources with eBay UK,
  Currys, John Lewis, and Facebook Marketplace presets (UK); `GET /api/v1/sources`;
  deep-research catalogue of UK e-commerce candidates. `### Changed`: `product.source_type`
  migrated from a native Postgres enum to a validated string column.

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
