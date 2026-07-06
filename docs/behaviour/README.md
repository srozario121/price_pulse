# Price Pulse — E2E Behaviour Specification

This directory is the **single source of truth** for Price Pulse's expected
end-to-end behaviour. The `.feature` files here are written in Gherkin and are
**executed** as tests against the live `docker compose` stack:

- **Backend journeys** run under [`pytest-bdd`](https://pytest-bdd.readthedocs.io/)
  with step definitions in `backend/tests/e2e/steps/`.
- **Frontend UI journeys** (`ui_journeys.feature`) run under
  [`playwright-bdd`](https://vitalets.github.io/playwright-bdd/) with step
  definitions in `frontend/tests/e2e/steps/`.

The runners are pointed at this directory (they do **not** get their own copy of
the features): backend via `bdd_features_base_dir = "../docs/behaviour"` in
`backend/pyproject.toml`; frontend via `defineBddConfig({ features })` in
`frontend/playwright.config.ts`.

## Running

The executed suite needs the **e2e compose overlay** (Item 13 harness), which
adds a deterministic fixture scrape target, a webhook sink, and gated
test-control hooks. Use the `make` lifecycle targets:

```bash
make test-e2e          # up → backend pytest-bdd + frontend playwright-bdd → down
make test-e2e-smoke    # only @smoke-tagged scenarios (fast; runs on every PR)
make e2e-up            # bring the e2e overlay up (for local iteration)
make e2e-down          # tear it down and remove volumes
```

In CI, the `e2e` job runs `@smoke` on every PR/push and the **full** catalogue
nightly (schedule) and on manual `workflow_dispatch`.

## Scenario ID convention — `PP-E2E-NNN`

Every `Scenario` / `Scenario Outline` carries a **stable ID tag** of the form
`@PP-E2E-NNN`. The ID never changes even if the scenario wording is edited, so
tests, docs, and discussions can reference behaviour unambiguously.

- IDs are allocated in blocks per feature (010–019 scraping, 020–029 alerts, …).
- `@smoke` marks the subset exercised on every PR (Item 13's harness self-check).
- Gherkin tags become pytest markers (`@smoke` → `-m smoke`), so the runners
  filter by tag directly.

## Traceability — feature → step module

| Feature file | IDs | Runner | Step definitions |
|---|---|---|---|
| `product_tracking.feature` | PP-E2E-001…003 | pytest-bdd | `backend/tests/e2e/steps/test_behaviour.py` |
| `scraping.feature` | PP-E2E-010…013 | pytest-bdd | `backend/tests/e2e/steps/test_behaviour.py` |
| `alerts.feature` | PP-E2E-020…022 | pytest-bdd | `backend/tests/e2e/steps/test_behaviour.py` |
| `notification_channels.feature` | PP-E2E-030…034 | pytest-bdd | `backend/tests/e2e/steps/test_behaviour.py` |
| `ui_journeys.feature` | PP-E2E-040…042 | playwright-bdd | `frontend/tests/e2e/steps/ui_journeys.steps.ts` |

`@smoke` scenarios: `PP-E2E-001`, `PP-E2E-010`, `PP-E2E-013`, `PP-E2E-020`, `PP-E2E-040`.

## Determinism (test hooks)

Scenarios are made deterministic without wall-clock waits:

- **Fixture server** serves canned product HTML through the real `generic`
  scraper; `PUT /fixtures/{slug}/price` forces a price change.
- **Gated hooks** (`E2E_TEST_HOOKS=true`, e2e overlay only):
  `POST /api/v1/_test/products/{id}/scrape-sync` runs a scrape inline;
  `POST /api/v1/_test/alerts/{id}/reset-cooldown` clears an alert cooldown.
- **Fast cadence**: the overlay sets `SCRAPE_INTERVAL_MINUTES=1` and a small
  `ALERT_COOLDOWN_HOURS` so scheduling/cooldown resolve quickly.

Assertions go through the **public REST API / UI only**; scenarios isolate by
using a **unique fixture slug per scenario** (no shared reset).

See [`../decisions/e2e-behaviour-spec.md`](../decisions/e2e-behaviour-spec.md)
for the design rationale.
