#!/usr/bin/env bash
# =============================================================================
# Frontend intra-tier coverage overlap — per-test-file coverage generator
# =============================================================================
# vitest aggregates coverage across all tests in a run and does not attribute
# lines to individual test files. To get per-test-file attribution we run each
# test file in isolation and save its Istanbul coverage-final.json into a
# staging directory keyed by "<tier>__<name>". check_coverage_overlap_frontend.js
# then compares the per-file reports and flags same-tier line overlap.
#
# Only tests/unit/ and tests/integration/ are iterated. e2e/ files and top-level
# tests/*.test.* files (e.g. smoke.test.ts) are intentionally excluded.
#
# Usage: bash scripts/check_coverage_overlap_frontend.sh
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="$REPO_ROOT/logs/quality/frontend-coverage-per-file"

# Recreate the staging directory fresh on every run.
rm -rf "$STAGING"
mkdir -p "$STAGING"

cd "$REPO_ROOT/frontend"

shopt -s nullglob
found_any=false
for tier in unit integration; do
  tier_dir="tests/$tier"
  [ -d "$tier_dir" ] || continue
  for file in "$tier_dir"/*.test.ts "$tier_dir"/*.test.tsx; do
    [ -e "$file" ] || continue
    found_any=true
    name="$(basename "$file")"
    name="${name%.test.ts}"
    name="${name%.test.tsx}"
    slug="${tier}__${name}"
    echo "--- coverage for $file (slug: $slug) ---"
    npx vitest run "$file" \
      --coverage \
      --coverage.reporter=json \
      --coverage.reportsDirectory="../logs/quality/frontend-coverage-per-file/$slug"
  done
done

if [ "$found_any" = false ]; then
  echo "No unit/integration test files found under frontend/tests/ — nothing to stage."
fi
