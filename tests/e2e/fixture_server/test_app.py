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


def test_drifted_layout_hides_the_price_from_the_standard_selector() -> None:
    # Arrange / Act — Item 16: simulate a retailer rotating its DOM
    client.put("/fixtures/drift-a/price", json={"price": "199.99"})
    client.put("/fixtures/drift-a/layout", json={"layout": "drifted"})
    html = client.get("/fixtures/drift-a").text

    # Assert — the price is still served, just not where `.price` looks
    assert "199.99" in html
    assert "class='price'" not in html
    assert "q9v-amount" in html


def test_drifted_layout_carries_decoy_numbers() -> None:
    # A generated selector that merely finds *a* number must not pass the
    # scenario, so the drifted page ships a was-price and a review count.
    client.put("/fixtures/drift-b/layout", json={"layout": "drifted"})
    html = client.get("/fixtures/drift-b").text
    assert "499.00" in html
    assert "318 reviews" in html


def test_layout_can_be_switched_back_to_standard() -> None:
    client.put("/fixtures/drift-c/layout", json={"layout": "drifted"})
    client.put("/fixtures/drift-c/layout", json={"layout": "standard"})
    assert "class='price'" in client.get("/fixtures/drift-c").text


def test_unknown_layout_is_422() -> None:
    resp = client.put("/fixtures/drift-d/layout", json={"layout": "sideways"})
    assert resp.status_code == 422


def test_unknown_slug_404() -> None:
    # Arrange / Act
    resp = client.get("/fixtures/does-not-exist")
    # Assert
    assert resp.status_code == 404
