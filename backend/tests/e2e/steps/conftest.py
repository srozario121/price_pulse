"""Shared fixtures for the executed backend BDD suite (Item 14).

These step definitions run on the host against the **live e2e compose stack**
(`make test-e2e`). They assert exclusively through the public REST API and
drive the fixture server + gated test-control hooks; they never touch the DB
or Redis directly.

Endpoints (overridable via env for CI):
- backend           E2E_BACKEND_URL          default http://localhost:8000
- fixture (host)     E2E_FIXTURE_HOST_URL     default http://localhost:9000
- fixture (in-net)   E2E_FIXTURE_INTERNAL_URL default http://fixture-server:9000
- webhook sink       E2E_WEBHOOK_URL          default http://webhook-sink:8080/

The whole suite is marked ``live_api`` so it is selected only by
``make test-e2e`` (``-m live_api``) and never by the default test run.
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.live_api


@pytest.fixture(scope="session")
def backend_url() -> str:
    return os.environ.get("E2E_BACKEND_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def fixture_host_url() -> str:
    """Fixture server as reachable from the host (for price mutation)."""
    return os.environ.get("E2E_FIXTURE_HOST_URL", "http://localhost:9000")


@pytest.fixture(scope="session")
def fixture_internal_url() -> str:
    """Fixture server as reachable by the backend (stored on Product.url)."""
    return os.environ.get("E2E_FIXTURE_INTERNAL_URL", "http://fixture-server:9000")


@pytest.fixture(scope="session")
def webhook_url() -> str:
    return os.environ.get("E2E_WEBHOOK_URL", "http://webhook-sink:8080/")


@pytest.fixture()
def http() -> httpx.Client:
    """Blocking HTTP client for step definitions (pytest-bdd steps are sync)."""
    with httpx.Client(timeout=30.0) as client:
        yield client


@pytest.fixture()
def context() -> dict:
    """Per-scenario scratch space shared across Given/When/Then steps."""
    return {}
