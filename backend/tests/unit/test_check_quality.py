"""Unit tests for backend/scripts/check_quality.py."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

import scripts.check_quality as cq

# ---------------------------------------------------------------------------
# percentile
# ---------------------------------------------------------------------------


def test_percentile_p95_ten_values():
    values = list(range(1, 11))  # 1..10
    result = cq.percentile(values, 95)
    assert abs(result - 9.55) < 0.01


def test_percentile_p5_ten_values():
    values = list(range(1, 11))
    result = cq.percentile(values, 5)
    assert abs(result - 1.45) < 0.01


def test_percentile_single_value():
    assert cq.percentile([42.0], 95) == 42.0


def test_percentile_empty():
    assert cq.percentile([], 95) == 0.0


# ---------------------------------------------------------------------------
# load_thresholds
# ---------------------------------------------------------------------------


def test_load_thresholds_reads_toml(tmp_path, monkeypatch):
    toml_content = textwrap.dedent("""\
        [backend]
        cc_p95_max = 5
        mi_p5_min = 15
        halstead_effort_p95_max = 300
        coverage_min_pct = 88

        [frontend]
        coverage_min_pct = 75
    """)
    toml_file = tmp_path / "quality-thresholds.toml"
    toml_file.write_text(toml_content)
    monkeypatch.setattr(cq, "THRESHOLDS_PATH", toml_file)

    result = cq.load_thresholds()

    assert result["backend"]["cc_p95_max"] == 5
    assert result["backend"]["coverage_min_pct"] == 88


def test_load_thresholds_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cq, "THRESHOLDS_PATH", tmp_path / "missing.toml")

    with pytest.raises(SystemExit) as exc_info:
        cq.load_thresholds()
    assert exc_info.value.code == 1


def test_load_thresholds_malformed_toml(tmp_path, monkeypatch):
    bad_file = tmp_path / "quality-thresholds.toml"
    bad_file.write_text("not valid toml [[[")
    monkeypatch.setattr(cq, "THRESHOLDS_PATH", bad_file)

    with pytest.raises(SystemExit) as exc_info:
        cq.load_thresholds()
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# coverage threshold
# ---------------------------------------------------------------------------


def _make_coverage_xml(tmp_path: Path, line_rate: float) -> Path:
    xml_content = f'<?xml version="1.0" ?>\n<coverage line-rate="{line_rate}" branch-rate="0" />\n'
    path = tmp_path / "coverage.xml"
    path.write_text(xml_content)
    return path


def test_load_coverage_pct_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(cq, "COVERAGE_XML", _make_coverage_xml(tmp_path, 0.92))
    assert abs(cq.load_coverage_pct() - 92.0) < 0.01


def test_load_coverage_pct_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(cq, "COVERAGE_XML", _make_coverage_xml(tmp_path, 0.89))
    assert abs(cq.load_coverage_pct() - 89.0) < 0.01


def test_load_coverage_pct_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(cq, "COVERAGE_XML", tmp_path / "no-coverage.xml")

    with pytest.raises(SystemExit) as exc_info:
        cq.load_coverage_pct()
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# latest_report_dir
# ---------------------------------------------------------------------------


def test_latest_report_dir_missing_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(cq, "LOGS_QUALITY", tmp_path / "no-logs")

    with pytest.raises(SystemExit) as exc_info:
        cq.latest_report_dir()
    assert exc_info.value.code == 1


def test_latest_report_dir_empty_logs(tmp_path, monkeypatch):
    logs = tmp_path / "quality"
    logs.mkdir()
    monkeypatch.setattr(cq, "LOGS_QUALITY", logs)

    with pytest.raises(SystemExit) as exc_info:
        cq.latest_report_dir()
    assert exc_info.value.code == 1


def test_latest_report_dir_picks_last(tmp_path, monkeypatch):
    logs = tmp_path / "quality"
    logs.mkdir()
    (logs / "20240101T120000").mkdir()
    (logs / "20240102T120000").mkdir()
    monkeypatch.setattr(cq, "LOGS_QUALITY", logs)

    result = cq.latest_report_dir()
    assert result.name == "20240102T120000"


# ---------------------------------------------------------------------------
# run() — full integration within a temp filesystem
# ---------------------------------------------------------------------------


def _make_report_dir(base: Path, cc_scores: list[float], mi_scores: list[float], hal_efforts: list[float]) -> Path:
    report_dir = base / "20240101T120000"
    report_dir.mkdir(parents=True)

    cc_data = {"app/main.py": [{"name": f"fn{i}", "complexity": v} for i, v in enumerate(cc_scores)]}
    (report_dir / "cc.json").write_text(json.dumps(cc_data))

    mi_data = {f"app/mod{i}.py": {"mi": v} for i, v in enumerate(mi_scores)}
    (report_dir / "mi.json").write_text(json.dumps(mi_data))

    hal_data = {"app/main.py": {"functions": [{"name": f"fn{i}", "effort": v} for i, v in enumerate(hal_efforts)]}}
    (report_dir / "hal.json").write_text(json.dumps(hal_data))

    return report_dir


def _patch_all(monkeypatch, tmp_path: Path, line_rate: float, cc: list, mi: list, hal: list):
    toml_content = textwrap.dedent("""\
        [backend]
        cc_p95_max = 7
        mi_p5_min = 10
        halstead_effort_p95_max = 500
        coverage_min_pct = 90
    """)
    thresholds_file = tmp_path / "thresholds.toml"
    thresholds_file.write_text(toml_content)
    monkeypatch.setattr(cq, "THRESHOLDS_PATH", thresholds_file)
    monkeypatch.setattr(cq, "COVERAGE_XML", _make_coverage_xml(tmp_path, line_rate))
    logs = tmp_path / "quality"
    logs.mkdir(exist_ok=True)
    _make_report_dir(logs, cc, mi, hal)
    monkeypatch.setattr(cq, "LOGS_QUALITY", logs)


def test_run_all_pass(monkeypatch, tmp_path):
    _patch_all(monkeypatch, tmp_path, line_rate=0.95, cc=[1, 2, 3], mi=[80, 90, 100], hal=[100, 200, 300])

    cq.run()  # must not raise


def test_run_coverage_below_threshold(monkeypatch, tmp_path, capsys):
    _patch_all(monkeypatch, tmp_path, line_rate=0.89, cc=[1, 2, 3], mi=[80, 90, 100], hal=[100, 200, 300])

    with pytest.raises(SystemExit) as exc_info:
        cq.run()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "backend coverage" in captured.out.lower() or "Backend coverage" in captured.out


def test_run_cc_above_threshold(monkeypatch, tmp_path):
    _patch_all(monkeypatch, tmp_path, line_rate=0.95, cc=[8, 9, 10], mi=[80, 90, 100], hal=[100, 200, 300])

    with pytest.raises(SystemExit) as exc_info:
        cq.run()
    assert exc_info.value.code == 1


def test_run_github_step_summary_all_pass(monkeypatch, tmp_path):
    _patch_all(monkeypatch, tmp_path, line_rate=0.95, cc=[1, 2, 3], mi=[80, 90, 100], hal=[100, 200, 300])
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    cq.run()

    content = summary_file.read_text()
    assert "✅" in content
    assert "❌" not in content


def test_run_github_step_summary_one_failure(monkeypatch, tmp_path):
    _patch_all(monkeypatch, tmp_path, line_rate=0.89, cc=[1, 2, 3], mi=[80, 90, 100], hal=[100, 200, 300])
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    with pytest.raises(SystemExit):
        cq.run()

    content = summary_file.read_text()
    assert "❌" in content
