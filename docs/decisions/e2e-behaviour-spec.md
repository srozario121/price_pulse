# ADR — Executed E2E Behaviour Specification

**Status**: Accepted
**Date**: 2026-07-05
**Items**: 13 (E2E Test Harness & CI), 14 (Standardised, Executed E2E Behaviour Specification)

---

## Context

Price Pulse had no standardised definition of expected end-to-end behaviour and
no behavioural E2E coverage — only a liveness smoke check and unexecuted
Playwright navigation specs pointed at the dev server. We needed both a
readable behaviour spec and executable coverage of the core value flow
(add product → scrape → dedup → alert → notify) against a running stack.

---

## Decision

### 1 — Executed BDD, not a traceable-only spec

Gherkin `.feature` files under `docs/behaviour/` are the single source of truth
**and** are executed directly: `pytest-bdd` for backend journeys,
`playwright-bdd` for frontend UI journeys. The spec and its verification cannot
drift because the Gherkin *is* the test.

### 2 — Item 13 owns the harness; Item 14 owns features + steps

Item 13 provides the runtime (e2e compose overlay, fixture server, webhook sink,
gated test hooks, `make` lifecycle, CI job). Item 14 authors the `.feature`
catalogue and the step definitions. Item 14 depends on Item 13; they are
delivered together, harness first.

### 3 — `docs/behaviour/` is canonical; runners point there

Features live under `docs/behaviour/` and stay browsable as documentation. The
runners are configured to discover them there (`bdd_features_base_dir`;
`defineBddConfig({ features })`) rather than duplicating features into `tests/`.
Step definitions live beside the tests (`backend/tests/e2e/steps/`,
`frontend/tests/e2e/steps/`).

### 4 — Determinism via gated test hooks, assertions via public API only

Scenarios are made deterministic without wall-clock waits:

- a **fixture HTTP server** serves canned HTML through the real `generic`
  scraper and exposes `PUT /fixtures/{slug}/price` to force price changes;
- **gated hooks** (`E2E_TEST_HOOKS=true`, mounted only by the e2e overlay)
  provide synchronous scrape and cooldown-reset;
- the overlay shrinks scrape interval and cooldown so cadence/cooldown resolve
  in seconds;
- a **webhook-sink** service accepts webhook deliveries so they record as `sent`.

Step definitions assert **only through the public REST API / UI** and isolate
scenarios with a **unique fixture slug per scenario** (no shared reset). This
keeps tests decoupled from internal storage. To support notification
assertions through the public API, a read endpoint
`GET /api/v1/alerts/{id}/notifications` was added.

### 5 — Scenario IDs and CI cadence

Every scenario carries a stable `@PP-E2E-NNN` tag (see
[`../behaviour/README.md`](../behaviour/README.md)). The `@smoke` subset runs on
every PR/push; the full catalogue runs nightly and on manual dispatch.

---

## Consequences

- New dev dependencies: `pytest-bdd` (backend), `playwright-bdd` (frontend).
- The gated hooks are a test-only surface; they are absent from the route table
  whenever `E2E_TEST_HOOKS` is false (verified by a unit test), so they never
  exist in production.
- The executed suite requires the e2e overlay and is excluded from the default
  coverage-gated test run (`--ignore=tests/e2e`); it runs via `make test-e2e`.
- One scenario (`PP-E2E-013`) intentionally exercises the real Celery beat
  cadence with bounded polling; it is excluded from `@smoke` to keep PR runs
  fast and low-flake.
