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

## 14. Standardised, Executed E2E Behaviour Specification (BDD)

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
- [ ] Add `pytest-bdd` to `backend/pyproject.toml` `[dependency-groups] dev`; register a `live_api` (or new `e2e`) marker usage for the step tests
- [ ] Add `playwright-bdd` to `frontend/package.json` devDependencies; add `bddgen`/`playwright test` wiring and a `test:e2e:bdd` script
- [ ] Configure `pytest-bdd` feature discovery to point at `docs/behaviour/` (`bdd_features_base_dir` in `pytest.ini`/`pyproject.toml`); configure `playwright-bdd` `defineBddConfig({ features: '../docs/behaviour/**/*.feature' })`

**Feature catalogue**
- [ ] Author `docs/behaviour/*.feature` per the Scenario catalogue above (Given/When/Then), each `Scenario` tagged `@PP-E2E-NNN`
- [ ] Create `docs/behaviour/README.md` documenting the Gherkin conventions, the `PP-E2E-NNN` ID scheme, ID allocation, the features→step-modules map, and how to run the suite (`make test-e2e`)

**Backend step definitions** (`backend/tests/e2e/steps/`)
- [ ] Implement `pytest-bdd` step definitions covering all backend `.feature` scenarios, asserting **only via the public REST API** (httpx against the running stack), driving the fixture server's price-mutation endpoint and the gated control hooks for scrape/cooldown
- [ ] Provision unique per-scenario fixture product URLs (Background/fixture) so scenarios are isolated without a global reset

**Frontend step definitions** (`frontend/tests/e2e/steps/`)
- [ ] Implement `playwright-bdd` step definitions for `ui_journeys.feature` against the composed nginx stack (`E2E_BASE_URL=http://localhost`), seeding the required product via the API before UI assertions

**Notification read surface** (needed for public-API notification assertions)
- [ ] Add `GET /api/v1/alerts/{alert_id}/notifications` — paginated `NotificationLogRead` list (new `NotificationLogRead` schema in `schemas/notification.py`; service method in a notification/query service; route in `api/v1/alerts.py`)

**Traceability**
- [ ] Ensure every step-definition module / scenario references its `@PP-E2E-NNN` tag so the executed test maps 1:1 to the catalogue; add a short traceability table to `docs/behaviour/README.md`

**Harness dependencies (tracked in Item 13, verified here)**
- [ ] Confirm the Item 13 e2e compose profile, fixture server (+ price-mutation endpoint), webhook-sink service, `E2E_TEST_HOOKS` control endpoints, `make test-e2e`, and CI job exist and satisfy the contract these steps assume; file the gaps as Item 13 tasks if not

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

## References

- FastAPI docs: https://fastapi.tiangolo.com/
- Celery docs: https://docs.celeryq.dev/
- SQLAlchemy async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Alembic: https://alembic.sqlalchemy.org/
- Vitest: https://vitest.dev/
- React Query: https://tanstack.com/query/latest
- MSW: https://mswjs.io/
- Recharts: https://recharts.org/
