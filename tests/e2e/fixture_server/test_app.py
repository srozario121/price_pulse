"""Unit tests for the E2E fixture server (runnable with the backend venv)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.e2e.fixture_server.app import app

client = TestClient(app)


def test_health_ok() -> None:
    # Arrange / Act
    resp = client.get("/health")
    # Assert
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_default_fixture_renders_price_in_selector() -> None:
    # Arrange / Act
    resp = client.get("/fixtures/default")
    # Assert
    assert resp.status_code == 200
    assert "class='price'>199.99</span>" in resp.text


def test_put_price_mutates_served_html() -> None:
    # Arrange
    client.put("/fixtures/widget/price", json={"price": "49.99"})
    # Act
    resp = client.get("/fixtures/widget")
    # Assert
    assert "class='price'>49.99</span>" in resp.text


def test_get_price_json() -> None:
    # Arrange
    client.put("/fixtures/gadget/price", json={"price": "12.34"})
    # Act
    resp = client.get("/fixtures/gadget/price")
    # Assert
    assert resp.json() == {"slug": "gadget", "price": "12.34"}


def test_unknown_slug_404() -> None:
    # Arrange / Act
    resp = client.get("/fixtures/does-not-exist")
    # Assert
    assert resp.status_code == 404
