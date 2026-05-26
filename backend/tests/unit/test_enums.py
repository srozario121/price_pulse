"""Tests for ExtractionStatus enum."""
from __future__ import annotations

from app.models.enums import ExtractionStatus


def test_extraction_status_values() -> None:
    assert ExtractionStatus.OK == "ok"
    assert ExtractionStatus.EXTRACTION_FAILED == "extraction_failed"
    assert ExtractionStatus.HTTP_ERROR == "http_error"


def test_extraction_status_is_str() -> None:
    assert isinstance(ExtractionStatus.OK, str)
    assert isinstance(ExtractionStatus.EXTRACTION_FAILED, str)
    assert isinstance(ExtractionStatus.HTTP_ERROR, str)


def test_extraction_status_str_comparison() -> None:
    # str(Enum) works because it inherits str
    assert ExtractionStatus.OK == "ok"
    assert ExtractionStatus.EXTRACTION_FAILED == "extraction_failed"
    assert ExtractionStatus.HTTP_ERROR == "http_error"


def test_extraction_status_value_attribute() -> None:
    assert ExtractionStatus.OK.value == "ok"
    assert ExtractionStatus.EXTRACTION_FAILED.value == "extraction_failed"
    assert ExtractionStatus.HTTP_ERROR.value == "http_error"


def test_extraction_status_from_string() -> None:
    assert ExtractionStatus("ok") == ExtractionStatus.OK
    assert ExtractionStatus("extraction_failed") == ExtractionStatus.EXTRACTION_FAILED
    assert ExtractionStatus("http_error") == ExtractionStatus.HTTP_ERROR


def test_extraction_status_all_members() -> None:
    members = {m.value for m in ExtractionStatus}
    assert members == {"ok", "extraction_failed", "http_error"}
