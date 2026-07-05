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

## 12. Quality Issue Fixes (PR #1 pre-merge)

Address quality gate failures surfaced when CI runs against PR #1 (`feat/item-11-plan-review`). This item tracks any lint, test, type-check, or threshold violations that must be resolved before the branch can be merged to `main`.

**Depends on**: PR #1 CI run completing and reporting failures.

### Tasks

- [ ] Review CI results for PR #1 and list all failing jobs (lint, test-backend, test-frontend, build, security, agent-quality)
- [ ] Fix each failing check and push fixup commits to `feat/item-11-plan-review`
- [ ] Confirm all required status checks pass before converting PR #1 from draft to ready for review

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
