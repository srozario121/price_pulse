"""Executed backend BDD step definitions for the Price Pulse behaviour catalogue.

Binds every backend ``.feature`` under ``docs/behaviour/`` and implements the
steps against the **live e2e compose stack**. Assertions go through the public
REST API only; the fixture server and gated test-control hooks are driven over
HTTP. Notification delivery is asynchronous (Celery worker), so notification
assertions poll with a bounded deadline.

Run via ``make test-e2e`` / ``make test-e2e-smoke`` (never the default suite).
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

pytestmark = pytest.mark.live_api

scenarios(
    "product_tracking.feature",
    "scraping.feature",
    "alerts.feature",
    "notification_channels.feature",
)

_POLL_TIMEOUT_S = 30.0
_POLL_INTERVAL_S = 1.0
_NEGATIVE_GRACE_S = 6.0


# ── helpers ─────────────────────────────────────────────────────────────────


def _create_product(http: httpx.Client, backend_url: str, url: str) -> int:
    resp = http.post(
        f"{backend_url}/api/v1/products",
        json={
            "name": f"E2E {url}",
            "url": url,
            "source_type": "generic",
            "css_selector": ".price",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _notifications(http: httpx.Client, backend_url: str, alert_id: int) -> dict:
    resp = http.get(f"{backend_url}/api/v1/alerts/{alert_id}/notifications")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _poll_notification_total(
    http: httpx.Client, backend_url: str, alert_id: int, expected: int
) -> dict:
    """Poll until the notification total reaches *expected* (bounded)."""
    deadline = time.monotonic() + _POLL_TIMEOUT_S
    body = _notifications(http, backend_url, alert_id)
    while body["total"] < expected and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)
        body = _notifications(http, backend_url, alert_id)
    return body


# ── Given ───────────────────────────────────────────────────────────────────


@given("the API is available")
def api_available(http: httpx.Client, backend_url: str) -> None:
    resp = http.get(f"{backend_url}/health")
    assert resp.status_code == 200


@given(
    parsers.parse('a tracked product with a fixture price of "{price}"'),
    target_fixture="product",
)
@when(
    parsers.parse('I add a tracked product with a fixture price of "{price}"'),
    target_fixture="product",
)
def tracked_product(
    http: httpx.Client,
    backend_url: str,
    fixture_host_url: str,
    fixture_internal_url: str,
    context: dict,
    price: str,
) -> dict:
    slug = uuid.uuid4().hex[:8]
    http.put(f"{fixture_host_url}/fixtures/{slug}/price", json={"price": price})
    url = f"{fixture_internal_url}/fixtures/{slug}"
    product_id = _create_product(http, backend_url, url)
    context.update(product_id=product_id, slug=slug, url=url)
    return {"id": product_id, "url": url, "slug": slug}


def _create_alert(
    http: httpx.Client,
    backend_url: str,
    context: dict,
    direction: str,
    threshold: str,
    channel: str,
    webhook_url: str | None = None,
    whatsapp_number: str | None = None,
) -> int:
    payload: dict = {
        "product_id": context["product_id"],
        "threshold_price": threshold,
        "direction": direction,
        "channel": channel,
    }
    if webhook_url is not None:
        payload["webhook_url"] = webhook_url
    if whatsapp_number is not None:
        payload["whatsapp_number"] = whatsapp_number
    resp = http.post(f"{backend_url}/api/v1/alerts", json=payload)
    assert resp.status_code == 201, resp.text
    context["alert_id"] = resp.json()["id"]
    return context["alert_id"]


@given(
    parsers.parse('an active "{direction}" alert at threshold "{threshold}" on channel "{channel}"')
)
def alert_basic(
    http: httpx.Client,
    backend_url: str,
    context: dict,
    direction: str,
    threshold: str,
    channel: str,
) -> None:
    _create_alert(http, backend_url, context, direction, threshold, channel)


@given(
    parsers.parse(
        'an active "{direction}" alert at threshold "{threshold}" '
        'on channel "webhook" with a valid webhook URL'
    )
)
def alert_webhook_valid(
    http: httpx.Client,
    backend_url: str,
    webhook_url: str,
    context: dict,
    direction: str,
    threshold: str,
) -> None:
    _create_alert(
        http, backend_url, context, direction, threshold, "webhook", webhook_url=webhook_url
    )


@given(
    parsers.parse(
        'an active "{direction}" alert at threshold "{threshold}" '
        'on channel "webhook" with no webhook URL'
    )
)
def alert_webhook_missing(
    http: httpx.Client, backend_url: str, context: dict, direction: str, threshold: str
) -> None:
    _create_alert(http, backend_url, context, direction, threshold, "webhook")


@given(
    parsers.parse(
        'an active "{direction}" alert at threshold "{threshold}" '
        'on channel "whatsapp" with a whatsapp number'
    )
)
def alert_whatsapp_valid(
    http: httpx.Client, backend_url: str, context: dict, direction: str, threshold: str
) -> None:
    _create_alert(
        http, backend_url, context, direction, threshold, "whatsapp", whatsapp_number="+15551230000"
    )


@given(
    parsers.parse(
        'an active "{direction}" alert at threshold "{threshold}" '
        'on channel "whatsapp" with no whatsapp number'
    )
)
def alert_whatsapp_missing(
    http: httpx.Client, backend_url: str, context: dict, direction: str, threshold: str
) -> None:
    _create_alert(http, backend_url, context, direction, threshold, "whatsapp")


@given("a synchronous scrape has recorded a price")
def given_synchronous_scrape(http: httpx.Client, backend_url: str, context: dict) -> None:
    resp = http.post(f"{backend_url}/api/v1/_test/products/{context['product_id']}/scrape-sync")
    assert resp.status_code == 200, resp.text


# ── When ─────────────────────────────────────────────────────────────────────


@when("I run a synchronous scrape")
def run_scrape(http: httpx.Client, backend_url: str, context: dict) -> None:
    resp = http.post(f"{backend_url}/api/v1/_test/products/{context['product_id']}/scrape-sync")
    assert resp.status_code == 200, resp.text


@when(parsers.parse('I set the fixture price to "{price}"'))
def set_fixture_price(http: httpx.Client, fixture_host_url: str, context: dict, price: str) -> None:
    resp = http.put(f"{fixture_host_url}/fixtures/{context['slug']}/price", json={"price": price})
    assert resp.status_code == 200, resp.text


@when("I add another product with the same URL")
def add_duplicate_product(http: httpx.Client, backend_url: str, context: dict) -> None:
    resp = http.post(
        f"{backend_url}/api/v1/products",
        json={
            "name": "dup",
            "url": context["url"],
            "source_type": "generic",
            "css_selector": ".price",
        },
    )
    context["dup_status"] = resp.status_code


@when("I delete the product")
def delete_product(http: httpx.Client, backend_url: str, context: dict) -> None:
    resp = http.delete(f"{backend_url}/api/v1/products/{context['product_id']}")
    assert resp.status_code == 204, resp.text


@when("I reset the alert cooldown")
def reset_cooldown(http: httpx.Client, backend_url: str, context: dict) -> None:
    resp = http.post(f"{backend_url}/api/v1/_test/alerts/{context['alert_id']}/reset-cooldown")
    assert resp.status_code == 200, resp.text


@when("I wait for a scheduled scrape to run")
def wait_for_scheduled_scrape(http: httpx.Client, backend_url: str, context: dict) -> None:
    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline:
        resp = http.get(f"{backend_url}/api/v1/products/{context['product_id']}/prices")
        if resp.status_code == 200 and resp.json()["total"] >= 1:
            return
        time.sleep(3.0)


# ── Then ─────────────────────────────────────────────────────────────────────


@then("the product is created successfully")
def product_created(context: dict) -> None:
    assert context.get("product_id") is not None


@then("the product appears in the product list")
def product_in_list(http: httpx.Client, backend_url: str, context: dict) -> None:
    resp = http.get(f"{backend_url}/api/v1/products", params={"limit": 100})
    assert resp.status_code == 200, resp.text
    ids = {p["id"] for p in resp.json()["items"]}
    assert context["product_id"] in ids


@then("the request is rejected as a conflict")
def rejected_conflict(context: dict) -> None:
    assert context["dup_status"] == 409


@then("the product's price history is no longer available")
def price_history_gone(http: httpx.Client, backend_url: str, context: dict) -> None:
    resp = http.get(f"{backend_url}/api/v1/products/{context['product_id']}/prices")
    assert resp.status_code == 404


@then(parsers.parse('the latest recorded price is "{price}"'))
def latest_price_is(http: httpx.Client, backend_url: str, context: dict, price: str) -> None:
    resp = http.get(f"{backend_url}/api/v1/products/{context['product_id']}/prices")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items, "expected at least one price record"
    assert Decimal(str(items[0]["price"])) == Decimal(price)


@then(parsers.parse("the price history contains {count:d} record"))
@then(parsers.parse("the price history contains {count:d} records"))
def price_history_count(http: httpx.Client, backend_url: str, context: dict, count: int) -> None:
    resp = http.get(f"{backend_url}/api/v1/products/{context['product_id']}/prices")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == count


@then(parsers.parse("the price history contains at least {count:d} record"))
def price_history_at_least(http: httpx.Client, backend_url: str, context: dict, count: int) -> None:
    resp = http.get(f"{backend_url}/api/v1/products/{context['product_id']}/prices")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] >= count


@then(parsers.parse("the alert has {count:d} notification"))
@then(parsers.parse("the alert has {count:d} notifications"))
def alert_notification_count(
    http: httpx.Client, backend_url: str, context: dict, count: int
) -> None:
    if count == 0:
        time.sleep(_NEGATIVE_GRACE_S)
        body = _notifications(http, backend_url, context["alert_id"])
        assert body["total"] == 0
        return
    body = _poll_notification_total(http, backend_url, context["alert_id"], count)
    assert body["total"] == count


@then(parsers.parse('the most recent notification status is "{status}"'))
def most_recent_status(http: httpx.Client, backend_url: str, context: dict, status: str) -> None:
    body = _poll_notification_total(http, backend_url, context["alert_id"], 1)
    assert body["items"], "expected at least one notification"
    assert body["items"][0]["status"] == status
