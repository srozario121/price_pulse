# TODO — Price Pulse

Price monitoring platform: track retail product prices across external web sources and alert users when it's a good time to buy.

---

## 11. Test Suite Health & Coverage Deduplication

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
- [ ] Create `scripts/` directory at repo root (non-package — no `__init__.py` or `package.json`)

**Backend detection**
- [ ] Append `--cov-context=test` to the pytest invocation in the `make quality` Makefile target (on the same `uv run pytest --cov=app ...` line added by Item 10)
- [ ] Add `coverage json -o logs/quality/coverage-contexts.json` step to the `make quality` Makefile target, run immediately after pytest (requires `cd backend` prefix; the `.coverage` database is written by pytest-cov in the backend directory)
- [ ] Create `backend/scripts/check_coverage_overlap.py`:
  - Load `logs/quality/coverage-contexts.json` (path resolved relative to repo root); exit 1 with "Run make quality first to generate coverage data" if absent
  - For each source file in the JSON, iterate the `"contexts"` dict (maps line-number string → list of test node ID strings)
  - Classify each node ID as `unit` (contains `/tests/unit/`) or `integration` (contains `/tests/integration/`); skip `e2e` and unrecognised paths
  - Flag any line where two or more node IDs share the same tier classification
  - Print a table: `source_file | line | tier | test_a | test_b`; truncate test IDs to the function name for readability
  - Print summary: `N intra-tier duplicate lines found across M source files (unit: X, integration: Y)`
  - Read `max_intra_tier_duplicate_lines_backend` from `[test-health]` in `config/quality-thresholds.toml`; if absent, print "No enforcement threshold set — run baseline task first" and exit 0; if present and actual count exceeds threshold, exit 1 with "Backend intra-tier duplicate lines (N) exceeds threshold (M)"
- [ ] Add `make check-coverage-overlap` Makefile target: `cd backend && uv run python scripts/check_coverage_overlap.py`
- [ ] Call `make check-coverage-overlap` at the end of the `make quality` target (after `check_quality.py`)

**Frontend detection**
- [ ] Create `scripts/check_coverage_overlap_frontend.sh` — for each `*.test.ts` / `*.test.tsx` file found under `frontend/tests/unit/` and `frontend/tests/integration/`, `cd` into `frontend/` then run `npx vitest run --coverage --coverage.reportsDirectory=../logs/quality/frontend-coverage-per-file/<slug> <file>` where slug is the test file basename without extension; skip `e2e/` files and top-level `tests/*.test.*` files (e.g. `smoke.test.ts`)
- [ ] Create `scripts/check_coverage_overlap_frontend.js` (Node.js, no external deps):
  - Scan `logs/quality/frontend-coverage-per-file/` for `coverage-summary.json` files; exit 0 with a warning if none found ("Run make check-coverage-overlap-frontend to generate per-file data")
  - For each source file, collect the set of line numbers reported as covered in each per-file report; classify by tier from the test file's directory path; flag any source line covered by two or more reports from the same tier
  - Print a table: `source_file | line | tier | test_file_a | test_file_b`
  - Print summary: `N intra-tier duplicate lines found across M source files`
  - Read `max_intra_tier_duplicate_lines_frontend` from `[test-health]` in `config/quality-thresholds.toml`; if absent, print "No enforcement threshold set — run baseline task first" and exit 0; if present and actual count exceeds threshold, exit 1 with "Frontend intra-tier duplicate lines (N) exceeds threshold (M)"
- [ ] Add `make check-coverage-overlap-frontend` Makefile target: `bash scripts/check_coverage_overlap_frontend.sh && node scripts/check_coverage_overlap_frontend.js`
- [ ] Call `make check-coverage-overlap-frontend` at the end of the `make quality` target (after the vitest step)

**Baseline and enforcement**
- [ ] Run `make check-coverage-overlap` and `make check-coverage-overlap-frontend` on the current codebase; add a `[test-health]` section to `config/quality-thresholds.toml` recording `baseline_backend_duplicate_lines = N` and `baseline_frontend_duplicate_lines = N` with a comment noting the date
- [ ] Set enforcement thresholds: update `[test-health]` to add `max_intra_tier_duplicate_lines_backend = N` and `max_intra_tier_duplicate_lines_frontend = N` (set to the baseline values — zero tolerance for net new duplicates from this point forward)
- [ ] Verify `make quality` exits cleanly with enforcement thresholds set (no duplicate violations in the current codebase, or remediate any found before merging)

**Gitignore**
- [ ] Verify that `logs/quality/coverage-contexts.json` and `logs/quality/frontend-coverage-per-file/` are excluded by the existing `logs/**` rule in `.gitignore`; add explicit entries only if not already covered

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

## 13. End-to-End Behaviour Suite Against Live Compose Stack

The repo currently has **no behavioural E2E coverage** against a running application. What exists is a liveness poll only: the CI "Smoke — Full-stack health check" job and `make smoke` bring up `docker compose` and curl `/health` + `/nginx-health`, and one backend `@pytest.mark.live_api` test hits `/health`. The Playwright specs in `frontend/tests/e2e/smoke.spec.ts` cover UI navigation only, target the Vite dev server (`localhost:5173`) rather than the composed nginx stack, are wired to **no** npm script, and are **never executed in CI** (`@playwright/test` is an unused devDependency).

This item adds a real E2E suite that exercises Price Pulse's core value flow — add product URL → Celery scrape → price dedup → `PriceRecord` persisted → alert evaluation → notification dispatch — against a live `docker compose` stack, plus runs the existing Playwright UI journeys against that same stack in CI.

**Depends on**: existing `docker compose` stack and CI smoke job (Item 10, complete). Behaviour scenarios should trace to the catalogue defined in Item 14.

### Tasks

**Backend pipeline E2E**
- [ ] Create `backend/tests/e2e/` with `@pytest.mark.live_api` tests that drive the full pipeline against the running stack (not mocks): POST a product → trigger `scrape_product` → assert a `PriceRecord` is persisted → assert dedup on repeated identical HTML → assert alert evaluation triggers a `NotificationLog` when a threshold is crossed
- [ ] Use a deterministic scrape target (local fixture HTTP server or a stubbed scraper `source_type`) so the flow is reproducible in CI without hitting real retail sites
- [ ] Add a `make test-e2e` target that assumes a running stack (`make up` / `make dev`) and runs `uv run pytest -m live_api`

**Frontend E2E against compose**
- [ ] Add `test:e2e` and `test:e2e:ci` scripts to `frontend/package.json` (`playwright test`)
- [ ] Point Playwright at the composed nginx stack via `E2E_BASE_URL=http://localhost` (not the Vite dev server); seed at least one product so the "navigate to product detail" journey is deterministic
- [ ] Expand `smoke.spec.ts` (or add specs) to assert core behaviour, not just navigation: a price renders on the dashboard/chart, an alert can be created and appears in the list

**CI integration**
- [ ] Add a CI job (extend the `smoke` job or add an `e2e` job that `needs: build`) that brings up `docker compose`, waits for health, then runs backend `live_api` E2E and Playwright E2E against the live stack; upload the Playwright HTML report + traces as artifacts on failure
- [ ] Ensure `make smoke` remains a fast liveness gate and E2E is a separate, clearly-named stage

### Documentation
- **`CLAUDE.md`** — update: document `make test-e2e`, the `test:e2e` frontend script, and that E2E runs against the compose stack; clarify the distinction between the liveness smoke check and behavioural E2E
- **`CHANGELOG.md`** — add `### Added` entry: behavioural E2E suite (backend pipeline + Playwright UI journeys) running against the live compose stack in CI

---

## 14. Standardised E2E Behaviour Specification in Documentation

The repo has **no standardised definition of expected end-to-end behaviour**. Behaviour intent currently lives only as ad-hoc prose inside `TODO.md` "Test strategy" / "Live E2E" subsections and the tier description in `CLAUDE.md` — there is no scenario catalogue, no Gherkin/acceptance-criteria format, and nothing traceable that the Item 13 tests can be checked against.

This item defines the expected E2E behaviour of Price Pulse in a **standardised, executable-adjacent format** (Given/When/Then scenarios) under `docs/`, so behaviour is specified once and both the backend pipeline E2E and the Playwright journeys (Item 13) trace to it.

**Depends on**: none to author the spec; Item 13 consumes it (each E2E test references a scenario ID).

### Tasks

- [ ] Create `docs/behaviour/` with a set of Gherkin `.feature` files (or a single `price-pulse.feature`) capturing the core user journeys in Given/When/Then form: add a tracked product, scheduled + on-demand scrape produces a price record, duplicate HTML is deduplicated, price history is queryable/paginated, an alert threshold crossing triggers a notification, the dashboard renders price history and alert status
- [ ] Assign each scenario a stable ID (e.g. `PP-E2E-001`) and document the format/convention in a `docs/behaviour/README.md` (how scenarios are written, how they map to Item 13 tests)
- [ ] Add a traceability note linking each Item 13 E2E test to the scenario ID it verifies (docstring/comment referencing `PP-E2E-NNN`)
- [ ] Decide and record whether scenarios are executed directly (e.g. `pytest-bdd` / Playwright-BDD) or serve as the human-readable spec that hand-written E2E tests trace to — capture the decision as a short ADR under `docs/decisions/`

### Documentation
- **`docs/behaviour/`** — create: standardised Gherkin scenario catalogue + README describing the convention
- **`docs/decisions/`** — add ADR: chosen approach for E2E behaviour specification (executed BDD vs. traceable spec)
- **`CLAUDE.md`** — update: reference `docs/behaviour/` as the source of truth for expected E2E behaviour; note the `PP-E2E-NNN` traceability convention
- **`CHANGELOG.md`** — add `### Added` entry: standardised E2E behaviour specification (Gherkin scenario catalogue with traceability IDs)

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
