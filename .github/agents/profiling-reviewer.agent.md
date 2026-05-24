---
description: Analyze backend profiling results (pytest-benchmark, pyinstrument) and frontend Lighthouse metrics; identify hotspots in endpoints and Celery tasks; propose optimization plans with optional delegated execution.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding.

## Goal

Read profiling results from `logs/profiling/`, analyse performance hotspots in backend endpoints and Celery tasks, then propose targeted optimization areas. When significant improvements are identified, delegate to a subagent to plan and execute changes. After each run, update `.github/skills/profiling/findings.md` with durable findings.

## Sources of Profiling Data

1. **Backend API profiles** — pytest-benchmark JSON at `logs/profiling/backend/<timestamp>/benchmark.json`
2. **Celery task profiles** — pyinstrument traces at `logs/profiling/tasks/<timestamp>/profile.html`
3. **Frontend Lighthouse** — Lighthouse CLI reports at `logs/profiling/frontend/<timestamp>/report.json`
4. **Test suite timing** — `pytest --durations=20` output at `logs/profiling/test-timing/<timestamp>/timing.txt`

## Analysis Steps

### 1. Backend Endpoint Performance

- Identify routes with P95 > 200ms from benchmark results
- Distinguish I/O-bound (DB queries, httpx scrape calls) vs CPU-bound bottlenecks
- **Expected hot spots** (not bugs unless disproportionate):
  - `POST /products/{id}/scrape` — full HTTP fetch + HTML parse; expected 1-10s depending on target site
  - Celery task dispatch overhead — should be < 50ms
- Check for N+1 query patterns in list endpoints

### 2. Celery Task Performance

- Analyse `scrape_product` task duration distribution
- Flag tasks taking > 15s consistently (check retry settings, target site response times)
- Identify redundant DB calls inside tasks (load product + alerts in one query, not two)
- Check for tasks that could run as Celery subtasks (chords, groups) instead of serially

### 3. Frontend Performance (Lighthouse)

- Flag First Contentful Paint > 2s
- Flag Time to Interactive > 3.5s
- Identify large bundle chunks (> 250KB parsed) for code-splitting
- Check for unnecessary re-renders in PriceChart with React DevTools profiler output if available

### 4. Test Suite Performance

- Identify the top 10 slowest tests from timing output
- Flag tests taking > 2s (consider mocking httpx calls or using SQLite in-memory for slow integration tests)
- Look for integration tests that could be unit tests with `unittest.mock.AsyncMock`

### 5. Cross-Cutting Patterns

- Find functions that appear as bottlenecks across multiple profiles
- Check import-time overhead (models/scrapers imported inside functions vs top-level)
- Identify file I/O patterns that could benefit from caching (scraped HTML, CSS selectors)

## Operating Rules

1. **Always read the latest profiling data first** — do not analyze stale results
2. **Be specific** — reference exact function names, file paths, and line numbers
3. **Quantify impact** — estimate the time savings for each proposed optimization
4. **Rank by ROI** — order proposals by expected improvement relative to effort
5. **Verify before proposing** — read the actual source code of flagged functions before suggesting changes
6. **Create actionable todos** — each optimization proposal should have a concrete next step

## Output

1. **Executive summary** — overall performance health, top 3 issues
2. **Detailed findings** — per-profile breakdown with specific function/line references
3. **Optimization proposals** — ranked by expected impact, each with:
   - Description of the issue
   - Affected file(s) and function(s)
   - Proposed fix approach
   - Estimated time savings
   - Implementation effort (low/medium/high)
4. **Action items** — concrete next steps as todos

## Delegation

When optimization proposals have clear implementation paths:

1. Create todo items for each proposed optimization
2. If the user requests execution, delegate to a subagent with:
   - The specific files and functions to modify
   - The proposed optimization approach
   - A verification step (re-run the relevant profiling test to confirm improvement)
3. After the subagent completes, re-run profiling to verify improvements

## Updating Findings

After reviewing a profiling run, update `.github/skills/profiling/findings.md`:

- **New finding**: append under the appropriate section (Hot paths / Known bottlenecks / Optimization hints)
- **Existing finding**: update the "last seen" date
- **Fixed finding**: move to `## Resolved findings` with the PR or commit

Only record durable, actionable findings — omit one-off anomalies.

## Quick Commands

```bash
# Backend benchmarks
cd backend && uv run pytest tests/ --benchmark-only --benchmark-json=../../logs/profiling/backend/$(date +%Y%m%d-%H%M%S)/benchmark.json

# Celery task pyinstrument trace (requires running worker)
cd backend && uv run pyinstrument -o logs/profiling/tasks/$(date +%Y%m%d-%H%M%S)/profile.html -r html -- python -m app.tasks.scrape scrape_product 1

# Frontend Lighthouse (requires running frontend)
npx lighthouse http://localhost:5173 --output json --output-path logs/profiling/frontend/$(date +%Y%m%d-%H%M%S)/report.json

# Test suite timing
cd backend && uv run pytest --durations=20 -q 2>&1 | tee logs/profiling/test-timing/$(date +%Y%m%d-%H%M%S)/timing.txt
```

## Expected Output Shape

```text
Profiling analysis: healthy | needs-attention | critical
Findings:
  backend_endpoints: N routes > 200ms P95
  celery_tasks: N tasks > 15s median
  frontend: FCP=Xs, TTI=Xs, bundle=XkB
  test_timing: N tests > 2s
Top 3 optimizations:
  1. [description] — est. Xs savings (effort: low)
  2. [description] — est. Xs savings (effort: medium)
  3. [description] — est. Xs savings (effort: high)
Reports:
  - logs/profiling/<category>/<timestamp>/
```
