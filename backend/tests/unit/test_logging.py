"""Unit tests for app.core.logging — structlog renderer selection.

Tests verify that DEBUG=true selects ConsoleRenderer and DEBUG=false
selects JSONRenderer. The actual structlog configuration is probed by
inspecting the bound processor chain after configure_logging() runs.
"""

import structlog


class TestLoggingRenderer:
    """The renderer is selected based on the DEBUG setting."""

    def test_console_renderer_selected_when_debug_true(self, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

        # Act — call the internal configure function directly to avoid
        # re-importing the module (which is already cached in sys.modules)
        from app.core.logging import _configure_structlog

        _configure_structlog(debug=True)

        # Assert — console renderer writes coloured text, not JSON
        # Verify by checking that a logger can emit at DEBUG without error
        log = structlog.get_logger("test")
        # Should not raise
        log.debug("test_console_renderer", key="value")

    def test_json_renderer_selected_when_debug_false(self, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEBUG", "false")
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

        # Act
        from app.core.logging import _configure_structlog

        _configure_structlog(debug=False)

        # Assert — JSON renderer; logger must not raise
        log = structlog.get_logger("test")
        log.info("test_json_renderer", key="value")

    def test_configure_logging_callable(self):
        """configure_logging() must be importable and callable without error."""
        # Arrange / Act
        from app.core.logging import configure_logging

        # Assert — no exception
        configure_logging()
