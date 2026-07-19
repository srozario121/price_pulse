# ADR — Queued-Scrape Visibility

**Status**: Accepted
**Date**: 2026-07-19
**Item**: 17 (Queued-Scrape Visibility: List Queued/Running Jobs & Their Statuses)

---

## Context

`POST /products/{id}/scrape` returned a `task_id` + `status: "queued"` and then
the outcome was only observable indirectly through new `PriceRecord` rows. Flower
exists in the dev stack but is an ops tool, not an app surface. Scheduled scrapes
(the 30-minute RedBeat cadence — the bulk of all scrapes) had no product-facing
visibility at all. Operators/users needed a durable view of scrape-job lifecycle
and failures.

---

## Decision

### 1 — A durable `ScrapeJob` table is the source of truth

A new persisted `scrape_job` table (Alembic `0009`), not the Celery result
backend. The result backend is ephemeral, TTL'd, lost on a Redis flush, and
cannot be filtered by product/status/queue — a table is the only durable,
indexable surface. `status` / `extraction_status` are plain `String` columns (no
native DB enum), matching the `price_record.extraction_status` convention, so
folding new outcomes in needs no further migration.

### 2 — Signal-driven lifecycle covers both dispatch paths

`scrape_product` is dispatched from two independent places — the on-demand API
(`apply_async`) and the RedBeat beat scheduler (worker-side, no API code path).
To capture both uniformly, lifecycle is driven by Celery signals rather than
endpoint code:

- **`before_task_publish`** (producer side — fires in the API process for
  on-demand and the beat process for scheduled dispatch) creates the `queued`
  row. It is the only signal that fires for *both* paths at enqueue time.
- **`task_prerun`** → `started`; **`task_postrun`** finalises off the `state`
  arg.

Recording only API-triggered scrapes would leave the Jobs view mostly empty and
hide exactly the scheduled-scrape failures this item exists to surface.

### 3 — The extraction outcome is folded into the job status

`ScrapeJobStatus` is `queued → started → success / failure`. A task that runs to
completion is `success` **only** when the scrape produced a usable price
(`extraction_status == "ok"`); any other retval (`http_error`,
`extraction_failed`, `blocked`, `captcha`, …) **and** a raised/timed-out task
both resolve to `failure`. The raw retval is kept in `extraction_status` and any
exception text in `detail`, so "task errored" stays distinguishable from "ran but
found no price" even though both read as `failure`. `RETRY` is not terminal — the
row stays `started` and the next `task_prerun` bumps `retries`.

### 4 — Signal writes use a dedicated *synchronous* session

The worker runs under the celery-aio-pool `AsyncIOPool`, so `task_prerun` /
`task_postrun` fire while an event loop is already running — `asyncio.run()` there
raises `RuntimeError`. A small sync engine (psycopg v3 over the same Postgres) is
used exclusively for `ScrapeJob` writes in signal handlers. `schedule.py`'s
`asyncio.run()` pattern works only because `worker_ready` fires *before* the loop
is processing tasks; the per-task signals have no such guarantee.

### 5 — Every handler filters to `scrape_product` and never breaks the pipeline

Handlers ignore non-`scrape_product` senders (so `send_notification` / schedule
tasks create no rows) and wrap all DB work in a guard that logs and continues — a
`ScrapeJob` write must never break scraping or notification delivery (mirrors the
existing best-effort schedule-registration and `on_worker_ready` guards).

### 6 — Idempotent upsert keyed by `task_id`

`scrape_product` has `acks_late=True` + `max_retries=3`, so the same `task_id`
can be re-published (retry) and re-run (redelivery). All handlers upsert by the
unique `task_id` (`INSERT … ON CONFLICT (task_id) DO NOTHING`; updates by
`task_id`), so a retried/redelivered task yields exactly one row. A publish for an
already-deleted `product_id` raises an FK error that the guard swallows — dispatch
proceeds, no row leaked.

### 7 — Time-based retention prune

A daily `prune_scrape_jobs` beat task deletes rows older than
`SCRAPE_JOB_RETENTION_DAYS` (default 7). At a 30-minute cadence × every active
product the table grows unbounded; a configurable time-based prune bounds it with
one simple, testable task registered on the static `beat_schedule`.

### 8 — `task_id` is the join key; trigger response unchanged

The existing `ScrapeJobResponse` (`task_id` + `status: "queued"` + `product`) is
unchanged. Because `before_task_publish` creates the row with that same
`task_id`, the client maps the 202 response 1:1 to the durable job via
`GET /scrape-jobs?task_id=…`. The on-demand path carries a `pp_trigger` header so
the row is marked `on_demand`; scheduled dispatches carry no header and default to
`scheduled`.

### 9 — Live queue depth is best-effort and clearly separable

`GET /scrape-jobs/queue-depth` reports per-queue broker depth (Redis `LLEN`) plus
a responsive-worker count (`inspect().ping()`), run in a threadpool. It degrades
to `null` values rather than erroring/hanging when no broker/worker answers. The
durable table already satisfies the core visibility goal, so this is additive.

---

## Consequences

- New main dependency: `psycopg[binary]` (sync driver for signal-handler writes).
- New API surface: `GET /scrape-jobs`, `GET /scrape-jobs/queue-depth`,
  `GET /products/{id}/scrape-jobs`; new `SCRAPE_JOB_RETENTION_DAYS` setting.
- The signal module is imported by `celery_app` so handlers register in the API,
  beat, and worker processes alike.
- Frontend gains a Jobs view (route + nav), a per-product last-scrape status badge
  on the Dashboard, and `useScrapeJobs` hooks.
