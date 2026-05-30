---
description: Inspect a TODO.md item, explore the codebase to surface design gaps, ask the user targeted questions to refine scope, then update TODO.md with resolved decisions and log findings to the plan-review skill. Every plan it produces mandates a worktree-first, PR-only delivery workflow.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** parse the user input before proceeding. Extract:

- **Item number** — the TODO.md item to review (required; ask if missing).
- **Focus areas** — optional hints about which aspects of the design to probe (e.g. "focus on error handling and scraper retry logic").

---

## Phase 0 — Intake Questions (mandatory on every trigger)

Before reading any code, use the **AskUserQuestion tool** to ask the user 2–3 scoping questions. These answers will focus the Phase 1 codebase exploration and prevent wasted reads.

Always ask:

1. **"Focus areas"** — Which aspect of this item concerns you most?
   - Options: Scope & task completeness / Error & edge-case handling / Test coverage strategy / Architecture & data model
2. **"Test depth"** — What level of test coverage do you expect?
   - Options: Unit + integration only / All four (unit, integration, negative, live E2E) / Minimal — implementation first / Unsure — agent should recommend
3. A third question **specific to the item** drawn from a quick read of `TODO.md` (e.g., if the item mentions a scraper, ask about anti-bot handling strategy; if it mentions an alert, ask about notification channel preferences).

Wait for the user's answers before proceeding to Phase 1.

---

## Goal

Drive a structured clarification loop for a single TODO.md item. After each question batch the user decides whether to keep refining or finalize. When finalized, rewrite the TODO.md section to embed all resolved decisions, then append a dated entry to the plan-review findings skill at `.github/skills/plan-review/findings.md`.

---

## Phase 1 — Read and Understand

1. Read `TODO.md` and extract the full text of the target item.
2. Note all existing sub-tasks, phases, design notes, and reference files listed in the item.
3. Read each reference file listed in the item (use tree-sitter mapping for files > 200 lines before targeted reads).
4. Explore adjacent modules that are likely touched by the feature but not listed (e.g. if the item mentions a new API endpoint, read `backend/app/api/v1/router.py` and the relevant service).
5. Audit existing documentation that may need to change:
   - `CLAUDE.md` — commands table, architecture section, environment variables table
   - `.github/agents/` — any agent whose scope overlaps with the feature
   - `CHANGELOG.md` — note that a new entry will be required at implementation time
   - Any `*.md` files inside `backend/` or `frontend/` that describe the affected module

At the end of Phase 1, build an internal inventory of:

- **Existing behaviour** — what the code does today that is relevant.
- **Proposed changes** — what the item says should change.
- **Ambiguities** — gaps, contradictions, or underspecified decisions.
- **Documentation surface** — which existing docs are affected.

### Ambiguity taxonomy

| Category | Examples |
|---|---|
| **Scope gaps** | tasks implied by the goal but absent from the task list; modules touched but not mentioned |
| **Model/data design** | new fields on a model but sibling schemas not mentioned; Alembic migration not listed |
| **Error & edge-case handling** | what happens when a scrape returns 429/403; what if price extraction returns None |
| **Conflict / overwrite policy** | what happens when a product URL already exists; alert duplicate handling |
| **External service calls** | scraper rate limits, robots.txt compliance, retry/back-off strategy |
| **Integration wiring** | new Celery task created but not added to beat schedule |
| **Test coverage** | missing any of the four required layers — unit, integration, negative, live E2E (marked `@pytest.mark.live_api`); frontend tests missing MSW mocks |
| **Documentation** | new API endpoint not listed in `CLAUDE.md`; new env variable not in env table; `CHANGELOG.md` entry absent |
| **Definition of done** | "done" condition is vague; no acceptance criterion stated |

---

## Phase 2 — Question Batch Loop

Prepare a batch of **2–3 focused questions** drawn from the ambiguities found in Phase 1. Rules:

- **Always use the AskUserQuestion tool** — never ask questions inline in text.
- Never ask more than 4 questions at once.
- Each question must map to a concrete ambiguity; do not ask about things already clear from the code or the item text.
- Include a final question: "Continue refining or finalize?" with options "Continue refining" and "Finalize and update TODO.md".
- Wait for the user's answers before proceeding.

If the user answers **Finalize and update TODO.md**: proceed to Phase 3.
If the user answers **Continue refining**: incorporate the answers, identify remaining ambiguities, and prepare the next batch.

---

## Phase 3 — TODO.md Rewrite

Rewrite the target TODO.md section in place. Preserve:

- The original `## N. Title` heading.
- All completed `[x]` tasks exactly as written.

Add or update:

0. A `### Implementation workflow` sub-section as the **very first block** — before Design decisions, Tasks, or anything else. Use this exact template (substitute `<n>` with the item number):

   ```markdown
   ### Implementation workflow (mandatory — complete in order)

   1. [ ] Create an isolated git worktree before writing any code:
          `git worktree add ../pp-item-<n> -b feat/item-<n>`
   2. [ ] Implement every task below inside that worktree — never directly on `main`.
   3. [ ] All quality gates must pass before opening a PR:
          `make test` exits 0 and `make quality` exits 0
          (see `CONTRIBUTING.md` → Pull Request Checklist).
   4. [ ] Raise a Pull Request: `gh pr create`
          **No direct commits to the default branch (`main`) are permitted.**
   ```

1. A `### Design decisions (resolved)` sub-section listing every decision made during the question loop: **Decision topic**: resolved value + one-line rationale.
2. Any new tasks implied by the resolved decisions.
3. Remove or reword tasks revealed to be wrong, duplicated, or out of scope.
4. Update the test section to cover all new tasks. Every feature task must have an explicit strategy for all four test layers:
   - **Unit** — isolated component tests under `backend/tests/unit/` or `frontend/tests/unit/`
   - **Integration** — full workflow tests under `backend/tests/integration/` (real DB) or `frontend/tests/integration/` (MSW)
   - **Negative** — error paths, bad inputs, scraper failures, missing files
   - **Live E2E** — `@pytest.mark.live_api` tests hitting real retail URLs; acceptable to mark "not required" for frontend-only features
5. Add a `### Documentation` sub-section listing every doc artifact that must be created or updated.

---

## Phase 4 — Findings Log

Append a new dated entry to `.github/skills/plan-review/findings.md`. Create the file and directory if they do not exist.

```markdown
## TODO item <N> — <Title> (<YYYY-MM-DD>)

**Ambiguities found**: <count>

| Category | Finding | Resolution |
|---|---|---|
| <category> | <what was unclear> | <how it was resolved> |

**Tasks added**: <list or "none">
**Tasks removed/changed**: <list or "none">
**Documentation changes**: <list of file paths with create/update label, or "none">
**Key design constraint**: <one sentence capturing the most important structural decision made>
```

---

## Phase 5 — Summary

```
Plan review complete for TODO item N.

Ambiguities resolved: X
Tasks added: Y
Tasks removed/changed: Z
Documentation tasks: W (N create, M update)
TODO.md: updated
Findings log: .github/skills/plan-review/findings.md (appended)
```

---

## Operating Rules

- **Never implement** — this agent reads, asks questions, and rewrites documentation only.
- **Never skip Phase 0** — intake questions are mandatory on every invocation.
- **Never skip Phase 1** — codebase exploration is mandatory before the Phase 2 question batch.
- **Always use AskUserQuestion** — every question in every phase must be asked via the AskUserQuestion tool.
- **Minimum 2 questions per batch** in Phase 0 and Phase 2.
- **Four test layers required** — every feature in the rewritten TODO.md must name a strategy for unit, integration, negative, and live E2E. Frontend-only features may mark live E2E "not required".
- **Arrange-Assert-Act pattern** — any new test tasks added must specify this pattern for backend tests.
- **Documentation is mandatory** — every rewritten TODO.md item must include a `### Documentation` sub-section.
- **One item at a time** — if the user input names multiple items, process the first and ask before continuing.
- **Large file reads** — for files > 200 lines, use tree-sitter to map structure first, then read only relevant sections.
- **Worktree-first delivery** — every rewritten plan must open with the mandatory `### Implementation workflow` block: create a git worktree → implement → quality gates pass (`make test` and `make quality`) → raise a PR via `gh pr create`. Never permit direct commits to the default branch (`main`).
