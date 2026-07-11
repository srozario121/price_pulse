"""Unit tests for backend/scripts/check_coverage_overlap.py."""

from __future__ import annotations

import json
import textwrap

import pytest

import scripts.check_coverage_overlap as cco


def _data(contexts: dict[str, dict[str, list[str]]]) -> dict:
    """Wrap {file: {line: [ctx,...]}} into the coverage-json shape."""
    return {"files": {f: {"contexts": c} for f, c in contexts.items()}}


# ---------------------------------------------------------------------------
# classify_tier
# ---------------------------------------------------------------------------


def test_classify_tier_unit():
    assert cco.classify_tier("tests/unit/test_x.py::test_a") == "unit"


def test_classify_tier_integration():
    assert cco.classify_tier("tests/integration/test_x.py::test_a") == "integration"


def test_classify_tier_unrecognised_returns_none():
    assert cco.classify_tier("tests/e2e/test_x.py::test_a") is None
    assert cco.classify_tier("") is None


# ---------------------------------------------------------------------------
# find_duplicates
# ---------------------------------------------------------------------------


def test_two_unit_tests_same_line_flagged():
    # Arrange
    data = _data(
        {"app/svc.py": {"10": ["tests/unit/test_a.py::test_a", "tests/unit/test_b.py::test_b"]}}
    )
    # Act
    dups = cco.find_duplicates(data)
    # Assert
    assert len(dups) == 1
    source_file, line, tier, test_a, test_b = dups[0]
    assert (source_file, line, tier) == ("app/svc.py", 10, "unit")
    assert {test_a, test_b} == {"test_a", "test_b"}


def test_cross_tier_overlap_not_flagged():
    # Arrange
    data = _data(
        {
            "app/svc.py": {
                "10": [
                    "tests/unit/test_a.py::test_a",
                    "tests/integration/test_b.py::test_b",
                ]
            }
        }
    )
    # Act
    dups = cco.find_duplicates(data)
    # Assert
    assert dups == []


def test_no_duplication_returns_empty():
    data = _data({"app/svc.py": {"10": ["tests/unit/test_a.py::test_a"]}})
    assert cco.find_duplicates(data) == []


def test_e2e_and_blank_contexts_skipped():
    data = _data(
        {"app/svc.py": {"10": ["", "tests/e2e/test_x.py::test_a", "tests/e2e/test_y.py::test_b"]}}
    )
    assert cco.find_duplicates(data) == []


def test_same_test_with_phase_suffix_counted_once():
    # The same node id tagged with different coverage phases is one test.
    data = _data(
        {
            "app/svc.py": {
                "10": ["tests/unit/test_a.py::test_a|run", "tests/unit/test_a.py::test_a|setup"]
            }
        }
    )
    assert cco.find_duplicates(data) == []


# ---------------------------------------------------------------------------
# load_contexts
# ---------------------------------------------------------------------------


def test_missing_contexts_file_exits_1(monkeypatch, tmp_path):
    monkeypatch.setattr(cco, "CONTEXTS_JSON", tmp_path / "nope.json")
    with pytest.raises(SystemExit) as exc:
        cco.load_contexts()
    assert exc.value.code == 1


def test_malformed_json_exits_1(monkeypatch, tmp_path):
    bad = tmp_path / "coverage-contexts.json"
    bad.write_text("{ not valid json")
    monkeypatch.setattr(cco, "CONTEXTS_JSON", bad)
    with pytest.raises(SystemExit) as exc:
        cco.load_contexts()
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# run — enforcement
# ---------------------------------------------------------------------------


def _write_contexts(tmp_path, data: dict):
    path = tmp_path / "coverage-contexts.json"
    path.write_text(json.dumps(data))
    return path


def _write_thresholds(tmp_path, body: str):
    path = tmp_path / "quality-thresholds.toml"
    path.write_text(textwrap.dedent(body))
    return path


def test_run_threshold_absent_exits_0(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cco, "CONTEXTS_JSON", _write_contexts(tmp_path, _data({})))
    monkeypatch.setattr(cco, "THRESHOLDS_PATH", _write_thresholds(tmp_path, "[backend]\n"))
    with pytest.raises(SystemExit) as exc:
        cco.run()
    assert exc.value.code == 0
    assert "No enforcement threshold set" in capsys.readouterr().out


def test_run_count_equals_threshold_exits_0(monkeypatch, tmp_path, capsys):
    data = _data(
        {"app/svc.py": {"10": ["tests/unit/test_a.py::test_a", "tests/unit/test_b.py::test_b"]}}
    )
    monkeypatch.setattr(cco, "CONTEXTS_JSON", _write_contexts(tmp_path, data))
    monkeypatch.setattr(
        cco,
        "THRESHOLDS_PATH",
        _write_thresholds(tmp_path, "[test-health]\nmax_intra_tier_duplicate_lines_backend = 1\n"),
    )
    # Within threshold: run() returns normally, no SystemExit.
    cco.run()
    assert "within threshold" in capsys.readouterr().out


def test_run_count_exceeds_threshold_exits_1(monkeypatch, tmp_path, capsys):
    data = _data(
        {"app/svc.py": {"10": ["tests/unit/test_a.py::test_a", "tests/unit/test_b.py::test_b"]}}
    )
    monkeypatch.setattr(cco, "CONTEXTS_JSON", _write_contexts(tmp_path, data))
    monkeypatch.setattr(
        cco,
        "THRESHOLDS_PATH",
        _write_thresholds(tmp_path, "[test-health]\nmax_intra_tier_duplicate_lines_backend = 0\n"),
    )
    with pytest.raises(SystemExit) as exc:
        cco.run()
    assert exc.value.code == 1
    assert "exceeds threshold" in capsys.readouterr().err
