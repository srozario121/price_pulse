---
description: Analyse flat-module drift in backend/app/ using a two-pass file-tree + AST methodology and propose subpackage consolidations aligned with the layered architecture convention.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding.

## Goal

Identify flat Python files in `backend/app/` (and any other directory with > 5 flat `.py` files) that belong together in a subpackage but are not yet grouped. Ground all analysis in the layered architecture convention defined in:

```text
docs/architecture/repository-architecture.md → ## Module domain-grouping convention
```

This agent proposes consolidations only. It never moves, creates, or deletes files.

## Operating Rules

1. **Pass 1 — file-tree heuristic**
   - Inventory all `.py` files at `backend/app/` root (excluding `__init__.py`).
   - Also inventory any sub-directory that has more than 5 flat `.py` files (e.g. `api/v1/` if routes proliferate).
   - Propose candidate groups by:
     - Common filename prefix or stem (e.g. `price_*`, `alert_*`, `scraper_*`).
     - Shared domain noun embedded in the filename.
     - Adjacent placement when subpackages already exist for nearby concerns.
   - Output candidate groups as a list. Do not confirm or reject them yet.

2. **Pass 2 — import/dependency confirmation**
   - For each Pass 1 candidate group, parse the AST of every file in the group.
   - Confirm against two merge-candidate criteria:
     - **Criterion 1 (shared types):** files import each other's types, or share a significant portion of their `schemas/` or `models/` imports.
     - **Criterion 2 (low fan-in):** none of the files is a standalone utility used across multiple unrelated workflows — check fan-in by grepping external import sites across `backend/app/`.
   - A candidate group passes only when **both** Criterion 1 **and** Criterion 2 hold.

3. **Rank confirmed candidates**
   - List confirmed consolidation candidates in priority order: most-coupled first, least-disruptive last.
   - Include the proposed subpackage name, the files involved, and a one-line rationale.

4. **Propose first, never auto-apply**
   - Do not move, rename, delete, or create any files.
   - Do not create `__init__.py`, update imports, or modify `CLAUDE.md`, `TODO.md`, or any architecture doc.
   - Return targeted proposal text only — patch-ready wording suitable for a TODO entry or PR description.
   - If no candidate group passes both criteria, say so explicitly.

5. **Report non-candidates**
   - For Pass 1 candidates that failed Pass 2, briefly state which criterion failed and why.

## Expected Output Shape

```text
Pass 1 candidates:
- group: [file_a.py, file_b.py, ...] — rationale (prefix / domain noun / adjacent)

Pass 2 results:
- CONFIRMED: [file_a.py, file_b.py] → proposed subpackage: backend/app/<name>/
  Criterion 1: <shared imports detail>
  Criterion 2: <fan-in detail>
- REJECTED: [file_c.py, file_d.py]
  Failed: Criterion 2 — file_d.py imported by 6 unrelated modules

Consolidation proposals (priority order):
1. Move [file_a.py, file_b.py] into backend/app/<name>/
   Rationale: <one-line>

No files were created, moved, or deleted.
```
