"""Intra-tier coverage overlap detector (backend).

Reads the coverage.py context-tagged JSON at logs/quality/coverage-contexts.json
(produced by `make quality` via `coverage json --show-contexts`) and flags any
source line that is covered by two or more test functions in the *same* tier
(both `tests/unit/` or both `tests/integration/`).

Cross-tier overlap (a unit test and an integration test covering the same line)
is intentional and NOT flagged — the two tiers verify different things.

Enforcement: if `[test-health] max_intra_tier_duplicate_lines_backend` is set in
config/quality-thresholds.toml and the actual count exceeds it, exit 1.
If the field is absent, print an informational note and exit 0.

Usage:
    cd backend && uv run python scripts/check_coverage_overlap.py
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
THRESHOLDS_PATH = REPO_ROOT / "config" / "quality-thresholds.toml"
CONTEXTS_JSON = REPO_ROOT / "logs" / "quality" / "coverage-contexts.json"

# Substrings used to classify a test node ID into a tier. Node IDs produced by
# pytest-cov's --cov-context=test look like "tests/unit/test_x.py::test_y"; a
# leading path prefix (absolute paths) is tolerated by the substring match.
TIER_MARKERS = {
    "unit": "tests/unit/",
    "integration": "tests/integration/",
}


def _die(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def load_thresholds() -> dict:
    if not THRESHOLDS_PATH.exists():
        return {}
    try:
        return tomllib.loads(THRESHOLDS_PATH.read_text())
    except tomllib.TOMLDecodeError as exc:
        _die(f"Failed to parse {THRESHOLDS_PATH}: {exc}")
    return {}  # unreachable; keeps type checkers happy


def load_contexts() -> dict:
    if not CONTEXTS_JSON.exists():
        _die("Run make quality first to generate coverage data")
    try:
        return json.loads(CONTEXTS_JSON.read_text())
    except json.JSONDecodeError as exc:
        _die(f"Failed to parse {CONTEXTS_JSON}: {exc}")
    return {}  # unreachable


def classify_tier(node_id: str) -> str | None:
    """Return 'unit', 'integration', or None for an unrecognised test context."""
    for tier, marker in TIER_MARKERS.items():
        if marker in node_id:
            return tier
    return None


def _test_func_name(node_id: str) -> str:
    """Truncate a node ID to its test function name for readable output."""
    # Drop any coverage phase suffix ("...::test_x|run") then take the last ::part.
    base = node_id.split("|", 1)[0]
    return base.rsplit("::", 1)[-1] if "::" in base else base


def find_duplicates(data: dict) -> list[tuple[str, int, str, str, str]]:
    """Flag lines where >=2 distinct tests of the same tier cover the line.

    Returns a list of (source_file, line, tier, test_a, test_b) tuples.
    """
    duplicates: list[tuple[str, int, str, str, str]] = []
    files = data.get("files", {})
    for source_file in sorted(files):
        contexts = files[source_file].get("contexts", {})
        for line_str in sorted(contexts, key=lambda s: int(s) if s.isdigit() else 0):
            # Group distinct test node IDs (ignoring blank/phase-suffix dups) by tier.
            per_tier: dict[str, list[str]] = {}
            for ctx in contexts[line_str]:
                if not ctx:
                    continue  # blank context = code run outside any test
                base = ctx.split("|", 1)[0]
                tier = classify_tier(base)
                if tier is None:
                    continue  # e2e / unrecognised path — skip
                bucket = per_tier.setdefault(tier, [])
                if base not in bucket:
                    bucket.append(base)
            for tier, node_ids in per_tier.items():
                if len(node_ids) >= 2:
                    duplicates.append(
                        (
                            source_file,
                            int(line_str),
                            tier,
                            _test_func_name(node_ids[0]),
                            _test_func_name(node_ids[1]),
                        )
                    )
    return duplicates


def print_report(duplicates: list[tuple[str, int, str, str, str]]) -> None:
    if duplicates:
        print(f"\n{'source_file':<45} {'line':>6}  {'tier':<12} {'test_a':<28} test_b")
        print(f"{'-' * 45} {'-' * 6}  {'-' * 12} {'-' * 28} {'-' * 28}")
        for source_file, line, tier, test_a, test_b in duplicates:
            print(f"{source_file:<45} {line:>6}  {tier:<12} {test_a:<28} {test_b}")

    files_affected = len({d[0] for d in duplicates})
    unit = sum(1 for d in duplicates if d[2] == "unit")
    integration = sum(1 for d in duplicates if d[2] == "integration")
    print(
        f"\n{len(duplicates)} intra-tier duplicate lines found across "
        f"{files_affected} source files (unit: {unit}, integration: {integration})"
    )


def run() -> None:
    data = load_contexts()
    duplicates = find_duplicates(data)
    print_report(duplicates)

    thresholds = load_thresholds()
    test_health = thresholds.get("test-health", {})
    threshold = test_health.get("max_intra_tier_duplicate_lines_backend")

    if threshold is None:
        print("No enforcement threshold set — run baseline task first")
        sys.exit(0)

    actual = len(duplicates)
    if actual > threshold:
        _die(f"Backend intra-tier duplicate lines ({actual}) exceeds threshold ({threshold})")
    print(f"Backend intra-tier duplicate lines ({actual}) within threshold ({threshold})")


if __name__ == "__main__":
    run()
