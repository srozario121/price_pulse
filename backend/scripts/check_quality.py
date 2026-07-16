"""Quality threshold enforcement script.

Reads radon CC/MI/Halstead JSON reports from the most recent logs/quality/<timestamp>/
directory and backend/coverage.xml, then exits 1 if any configured threshold is breached.

When GITHUB_ACTIONS=true, also appends a markdown summary table to $GITHUB_STEP_SUMMARY.

Usage:
    cd backend && uv run python scripts/check_quality.py
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
THRESHOLDS_PATH = REPO_ROOT / "config" / "quality-thresholds.toml"
BACKEND_ROOT = Path(__file__).resolve().parent.parent
COVERAGE_XML = BACKEND_ROOT / "coverage.xml"
LOGS_QUALITY = REPO_ROOT / "logs" / "quality"


def percentile(values: list[float], p: float) -> float:
    """Compute the p-th percentile of values using linear interpolation."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    idx = p / 100 * (n - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return sorted_vals[-1]
    frac = idx - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


def load_thresholds() -> dict:
    if not THRESHOLDS_PATH.exists():
        _die(f"quality-thresholds.toml not found at {THRESHOLDS_PATH}")
    try:
        return tomllib.loads(THRESHOLDS_PATH.read_text())
    except tomllib.TOMLDecodeError as exc:
        _die(f"Failed to parse {THRESHOLDS_PATH}: {exc}")


def latest_report_dir() -> Path:
    if not LOGS_QUALITY.exists():
        _die("No quality report found; run make quality first")
    # Sort by mtime, then name as a deterministic tiebreak: report dirs are named
    # with sortable timestamps (YYYYMMDDTHHMMSS), and two created in the same
    # coarse-granularity mtime tick (fast CI filesystems) would otherwise order
    # nondeterministically.
    dirs = sorted(
        [d for d in LOGS_QUALITY.iterdir() if d.is_dir() and d.name != "__pycache__"],
        key=lambda d: (d.stat().st_mtime, d.name),
    )
    if not dirs:
        _die("No quality report found; run make quality first")
    return dirs[-1]


def load_cc_p95(report_dir: Path) -> float:
    path = report_dir / "cc.json"
    if not path.exists():
        _die(f"cc.json not found in {report_dir}; run make quality first")
    data = json.loads(path.read_text())
    scores = [entry["complexity"] for entries in data.values() for entry in entries]
    return percentile(scores, 95)


def load_mi_p5(report_dir: Path) -> float:
    path = report_dir / "mi.json"
    if not path.exists():
        _die(f"mi.json not found in {report_dir}; run make quality first")
    data = json.loads(path.read_text())
    scores = [v["mi"] for v in data.values() if isinstance(v, dict) and "mi" in v]
    return percentile(scores, 5)


def load_halstead_p95(report_dir: Path) -> float:
    path = report_dir / "hal.json"
    if not path.exists():
        _die(f"hal.json not found in {report_dir}; run make quality first")
    data = json.loads(path.read_text())
    efforts: list[float] = []
    for module in data.values():
        if not isinstance(module, dict):
            continue
        functions = module.get("functions")
        # radon 6.x emits `functions` as a {name: metrics} dict; older/mocked
        # data may use a [metrics, ...] list. Support both.
        if isinstance(functions, dict):
            entries = functions.values()
        elif isinstance(functions, list):
            entries = functions
        else:
            continue
        for fn in entries:
            if isinstance(fn, dict) and "effort" in fn:
                efforts.append(fn["effort"])
    return percentile(efforts, 95)


def load_coverage_pct() -> float:
    if not COVERAGE_XML.exists():
        _die("coverage.xml not found; run make quality first")
    root = ET.parse(COVERAGE_XML).getroot()
    line_rate = float(root.attrib.get("line-rate", 0))
    return line_rate * 100


def _die(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def run() -> None:
    thresholds = load_thresholds()
    backend_cfg = thresholds.get("backend", {})

    cc_max = backend_cfg.get("cc_p95_max", 7)
    mi_min = backend_cfg.get("mi_p5_min", 10)
    hal_max = backend_cfg.get("halstead_effort_p95_max", 500)
    cov_min = backend_cfg.get("coverage_min_pct", 90)

    report_dir = latest_report_dir()

    cc_actual = load_cc_p95(report_dir)
    mi_actual = load_mi_p5(report_dir)
    hal_actual = load_halstead_p95(report_dir)
    cov_actual = load_coverage_pct()

    checks = [
        ("Backend coverage", f"{cov_actual:.1f}%", f"≥ {cov_min:.0f}%", cov_actual >= cov_min),
        ("CC P95", f"{cc_actual:.2f}", f"< {cc_max}", cc_actual < cc_max),
        ("MI P5", f"{mi_actual:.2f}", f"> {mi_min}", mi_actual > mi_min),
        ("Halstead effort P95", f"{hal_actual:.1f}", f"< {hal_max}", hal_actual < hal_max),
    ]

    failures = [(name, actual, threshold) for name, actual, threshold, ok in checks if not ok]

    _emit_github_summary(checks)

    if failures:
        col_w = max(len(name) for name, *_ in failures)
        print("\nQuality gate FAILED — threshold violations:\n")
        print(f"  {'Check':<{col_w}}  {'Actual':>10}  {'Required':>12}")
        print(f"  {'-' * col_w}  {'-' * 10}  {'-' * 12}")
        for name, actual, threshold in failures:
            print(f"  {name:<{col_w}}  {actual:>10}  {threshold:>12}")
        print()
        sys.exit(1)

    print("Quality gate PASSED — all thresholds met.")


def _emit_github_summary(checks: list[tuple]) -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    lines = [
        "## Quality Gate Results\n",
        "| Check | Value | Threshold | Status |",
        "| --- | --- | --- | --- |",
    ]
    for name, actual, threshold, ok in checks:
        status = "✅" if ok else "❌"
        lines.append(f"| {name} | {actual} | {threshold} | {status} |")
    lines.append("")

    with open(summary_path, "a") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    run()
