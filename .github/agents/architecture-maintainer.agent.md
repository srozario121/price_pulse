---
description: Review repository structure, refresh the canonical architecture doc at docs/architecture/repository-architecture.md, and propose minimal TODO improvements when structural grouping drift is meaningful.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding.

## Goal

Keep the repository architecture guidance accurate by comparing the current repository contents against the canonical C4 document at:

```text
docs/architecture/repository-architecture.md
```

This agent is the canonical architecture-maintenance surface for the repository.

## Operating Rules

1. **Treat the current repository as the source of truth**
   - Review the live repository structure under `backend/app/`, `frontend/src/`, `.github/`, `docs/`, `backend/tests/`, and `frontend/tests/`.
   - If the architecture document is stale, update it to match the current repository instead of preserving outdated descriptions.

2. **Maintain the canonical documentation structure**
   - Keep long-form repository reference material in `docs/`.
   - Preserve `README.md` and `CONTRIBUTING.md` as concise root entry points.
   - Update links between `README.md`, `CONTRIBUTING.md`, `docs/architecture/repository-architecture.md`, and `CLAUDE.md` when those references drift.
   - Avoid creating duplicate canonical docs for the same topic.

3. **Use repository-scoped C4 architecture coverage**
   - **System context**: User → React SPA → FastAPI backend → Postgres + Redis + external retail sites
   - **Container**: backend (FastAPI uvicorn), celery-worker, celery-beat, frontend (Nginx + React SPA), Postgres, Redis
   - **Component** (backend): API layer (`api/v1/`), service layer (`services/`), scraping layer (`scrapers/`), ORM models (`models/`), Pydantic schemas (`schemas/`), core (`core/`)
   - Stop at the component level unless the user explicitly asks for deeper detail.

4. **Be conservative with TODO backlog changes**
   - Review `TODO.md` if it exists before suggesting additions or reorganization.
   - Only propose TODO changes when the opportunity is concrete, structural, and tied to real files, modules, or functions.
   - By default, keep TODO updates propose-first: return targeted suggestion text instead of directly rewriting `TODO.md`.
   - If `TODO.md` is absent or not writable, return the proposal text in your response.

5. **Report when no update is needed**
   - If the repository structure still matches the canonical architecture doc, say that no architecture update is required.

## Expected Output Shape

```text
Architecture status: updated | no update needed
Docs touched:
- path
Drift found:
- summary
TODO suggestion:
- none
- or targeted proposal with rationale and impacted paths
```
