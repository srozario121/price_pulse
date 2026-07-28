"""Executed BDD steps for the live self-healing selector loop (Item 16).

**These call a REAL LLM provider and spend money.** They carry both ``live_api``
and ``live_llm``, so ``make test-e2e`` / ``make test-e2e-smoke`` (which select on
``live_api`` alone plus ``smoke``) never pick them up, and CI never runs them.
Invoke deliberately with ``make test-e2e-llm`` and a key in ``.env``.

Kept in its own module rather than added to ``test_behaviour.py`` so the
money-spending scenarios cannot be swept into the free suite by a future marker
change, and so a provider outage cannot redden the everyday E2E job.

Everything is asserted through the public REST API and the observable scrape
outcome — the ``selector_profile`` table is never read directly. What that buys
is a test of the behaviour a user actually experiences (a broken source starts
working again) rather than of an internal state transition, which is also why
these scenarios needed no new read endpoint.
"""

from __future__ import annotations

import os
import time
import uuid
from decimal import Decimal

import httpx
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

pytestmark = [pytest.mark.live_api, pytest.mark.live_llm]

scenarios("selector_healing.feature")

# Regeneration is a queued Celery job that makes a network round-trip to an LLM
# provider, so it is far slower than the rest of the E2E suite. Generous, but
# bounded — a hang must fail the scenario, not wedge the run.
_HEAL_TIMEOUT_S = 120.0
_POLL_INTERVAL_S = 3.0
_FIXTURE_PRICE = "199.99"


# ── helpers ─────────────────────────────────────────────────────────────────


def _latest_record(http: httpx.Client, backend_url: str, product_id: int) -> dict | None:
    """Return the newest price record for *product_id*, or None if there are none."""
    resp = http.get(
        f"{backend_url}/api/v1/products/{product_id}/prices",
        params={"limit": 1},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    return items[0] if items else None


def _scrape_sync(http: httpx.Client, backend_url: str, product_id: int) -> None:
    resp = http.post(f"{backend_url}/api/v1/_test/products/{product_id}/scrape-sync")
    assert resp.status_code == 200, resp.text


def _provision_drifted_product(
    http: httpx.Client,
    backend_url: str,
    fixture_host_url: str,
    host_alias: str,
) -> dict:
    """Create a uniquely-slugged product whose page serves drifted markup.

    The product keeps the ordinary ``.price`` selector every other scenario uses
    — that is the point: the configured selector is correct and simply no longer
    matches, which is exactly what a retailer redesign looks like.

    *host_alias* is a per-scenario DNS alias for the one fixture-server container
    (see ``docker-compose.e2e.yml``). Selector profiles are keyed by host, so
    without distinct aliases a heal in one scenario would silently satisfy the
    next one — and a scenario asserting ``selector_miss`` would fail purely
    because an earlier scenario had already healed the shared host.
    """
    slug = f"drift-{uuid.uuid4().hex[:8]}"
    resp = http.put(
        f"{fixture_host_url}/fixtures/{slug}/layout",
        json={"layout": "drifted"},
    )
    assert resp.status_code == 200, resp.text
    resp = http.put(f"{fixture_host_url}/fixtures/{slug}/price", json={"price": _FIXTURE_PRICE})
    assert resp.status_code == 200, resp.text

    url = f"http://{host_alias}:9000/fixtures/{slug}"
    resp = http.post(
        f"{backend_url}/api/v1/products",
        json={
            "name": f"E2E drifted {slug}",
            "url": url,
            "source_type": "generic",
            "css_selector": ".price",
        },
    )
    assert resp.status_code == 201, resp.text
    return {"slug": slug, "url": url, "product_id": resp.json()["id"]}


def _wait_for_ok_scrape(http: httpx.Client, backend_url: str, product_id: int) -> dict:
    """Poll a fresh scrape until one records ``ok``, or fail with a diagnosis.

    Re-scrapes each round rather than only reading records: the heal lands on the
    *profile*, and it is the next scrape that proves the profile is actually
    being used.
    """
    deadline = time.monotonic() + _HEAL_TIMEOUT_S
    last: dict | None = None
    while time.monotonic() < deadline:
        _scrape_sync(http, backend_url, product_id)
        last = _latest_record(http, backend_url, product_id)
        if last is not None and last["extraction_status"] == "ok":
            return last
        time.sleep(_POLL_INTERVAL_S)
    pytest.fail(
        f"selector was not healed within {_HEAL_TIMEOUT_S:.0f}s — "
        f"latest record: {last}. Check the celery-playwright worker consumed the "
        f"regeneration job and that LLM_API_KEY reached the container."
    )


# ── Given ────────────────────────────────────────────────────────────────────


@given("the e2e stack is running")
def stack_running(http: httpx.Client, backend_url: str) -> None:
    resp = http.get(f"{backend_url}/health")
    assert resp.status_code == 200, resp.text
    if not os.environ.get("LLM_API_KEY"):
        pytest.skip("No LLM_API_KEY in the environment — cannot exercise the live provider")


@pytest.fixture()
def host_alias(request) -> str:
    """A fixture-server DNS alias unique to this scenario.

    Derived from the scenario's own node id so scenarios cannot collide, and so
    adding a scenario does not require hand-assigning an alias — it only requires
    the pool in ``docker-compose.e2e.yml`` to be large enough, which is asserted
    rather than silently wrapped.
    """
    aliases = ["fixture-host-a", "fixture-host-b", "fixture-host-c", "fixture-host-d"]
    index = _SCENARIO_ALIAS_INDEX.setdefault(request.node.nodeid, len(_SCENARIO_ALIAS_INDEX))
    assert index < len(aliases), (
        f"more @live-llm scenarios ({index + 1}) than fixture-server aliases "
        f"({len(aliases)}) — add another alias in docker-compose.e2e.yml, or "
        f"scenarios will share a selector profile and leak state into each other"
    )
    return aliases[index]


# scenario node id → alias slot, so each scenario keeps its own host for its
# whole run (Given and Then must agree on the URL).
_SCENARIO_ALIAS_INDEX: dict[str, int] = {}


@given("a tracked product whose fixture page uses drifted markup")
def given_drifted_product(
    http: httpx.Client,
    backend_url: str,
    fixture_host_url: str,
    host_alias: str,
    context: dict,
) -> None:
    context.update(_provision_drifted_product(http, backend_url, fixture_host_url, host_alias))


@given("the product has been scraped and recorded a selector miss")
def given_selector_miss(http: httpx.Client, backend_url: str, context: dict) -> None:
    _scrape_sync(http, backend_url, context["product_id"])
    record = _latest_record(http, backend_url, context["product_id"])
    assert record is not None, "no price record was written"
    assert record["extraction_status"] == "selector_miss", record


@given("the product's selector has been healed")
def given_healed(http: httpx.Client, backend_url: str, context: dict) -> None:
    """Ensure the host has a working selector, healing it only if it does not.

    Deliberately conditional. Every fixture page lives on the same host
    (``fixture-server``), so profiles are shared across scenarios — and reporting
    an issue against an already-healthy host marks it stale and, inside the
    cooldown, cannot regenerate it. Unconditionally reporting here would
    therefore break the very state this step is supposed to establish.
    """
    _scrape_sync(http, backend_url, context["product_id"])
    record = _latest_record(http, backend_url, context["product_id"])
    if record is not None and record["extraction_status"] == "ok":
        return
    resp = http.post(f"{backend_url}/api/v1/products/{context['product_id']}/report-selector-issue")
    assert resp.status_code == 202, resp.text
    _wait_for_ok_scrape(http, backend_url, context["product_id"])


# ── When ─────────────────────────────────────────────────────────────────────


@when("the product is scraped synchronously")
def when_scrape(http: httpx.Client, backend_url: str, context: dict) -> None:
    _scrape_sync(http, backend_url, context["product_id"])


@when("a selector issue is reported for the product")
def when_report_issue(http: httpx.Client, backend_url: str, context: dict) -> None:
    resp = http.post(f"{backend_url}/api/v1/products/{context['product_id']}/report-selector-issue")
    context["report_status"] = resp.status_code
    context["report_body"] = resp.json()


@when(parsers.parse('the fixture price changes to "{price}"'))
def when_price_changes(
    http: httpx.Client, fixture_host_url: str, context: dict, price: str
) -> None:
    resp = http.put(f"{fixture_host_url}/fixtures/{context['slug']}/price", json={"price": price})
    assert resp.status_code == 200, resp.text
    context["expected_price"] = price


# ── Then ─────────────────────────────────────────────────────────────────────


@then(parsers.parse('the latest price record has extraction status "{status}"'))
def then_status(http: httpx.Client, backend_url: str, context: dict, status: str) -> None:
    record = _latest_record(http, backend_url, context["product_id"])
    assert record is not None, "no price record was written"
    assert record["extraction_status"] == status, record


@then("the latest price record has no price")
def then_no_price(http: httpx.Client, backend_url: str, context: dict) -> None:
    record = _latest_record(http, backend_url, context["product_id"])
    assert record["price"] is None, record


@then("the report is accepted and regeneration is enqueued")
def then_report_accepted(context: dict) -> None:
    assert context["report_status"] == 202, context.get("report_body")
    assert context["report_body"]["regeneration_enqueued"] is True, context["report_body"]


@then(
    parsers.parse(
        'within {seconds:d} seconds a fresh scrape of the same unchanged page records "{status}"'
    )
)
def then_heals(
    http: httpx.Client, backend_url: str, context: dict, seconds: int, status: str
) -> None:
    record = _wait_for_ok_scrape(http, backend_url, context["product_id"])
    assert record["extraction_status"] == status, record
    context["healed_record"] = record


@then("the recorded price matches the price the fixture page is serving")
def then_price_matches(context: dict) -> None:
    record = context["healed_record"]
    # The generated selector must have found the real amount, not the
    # struck-through was-price or the review count the drifted page also carries.
    assert Decimal(record["price"]) == Decimal(_FIXTURE_PRICE), record


@then(parsers.parse('the recorded price is "{price}"'))
def then_price_is(http: httpx.Client, backend_url: str, context: dict, price: str) -> None:
    record = _latest_record(http, backend_url, context["product_id"])
    assert Decimal(record["price"]) == Decimal(price), record
