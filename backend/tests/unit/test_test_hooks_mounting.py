"""Unit tests: the gated E2E test-hooks router mounts only when the flag is on.

Guards against the test-control endpoints ever being exposed in a non-e2e
environment (where ``E2E_TEST_HOOKS`` is false, i.e. everywhere but the e2e
docker-compose overlay).
"""

from __future__ import annotations

from app.core.config import settings
from app.main import create_app

_SCRAPE_SYNC = "/api/v1/_test/products/{product_id}/scrape-sync"
_RESET_COOLDOWN = "/api/v1/_test/alerts/{alert_id}/reset-cooldown"


def _test_hook_paths(app: object) -> set[str]:
    return {
        getattr(r, "path", "")
        for r in app.routes  # type: ignore[attr-defined]
        if getattr(r, "path", "").startswith("/api/v1/_test")
    }


def test_hooks_absent_when_flag_false(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(settings, "E2E_TEST_HOOKS", False)
    # Act
    app = create_app()
    # Assert
    assert _test_hook_paths(app) == set()


def test_hooks_present_when_flag_true(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(settings, "E2E_TEST_HOOKS", True)
    # Act
    app = create_app()
    # Assert
    paths = _test_hook_paths(app)
    assert _SCRAPE_SYNC in paths
    assert _RESET_COOLDOWN in paths
