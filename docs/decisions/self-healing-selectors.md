# ADR — LLM-Generated Self-Healing Price Selectors

**Status**: Accepted
**Date**: 2026-07-26
**Item**: 16 (Handle Selector Drift — LLM-Generated Self-Healing Selectors)

---

## Context

DOM price extraction depends on hardcoded, ordered CSS selector lists — the
Amazon `_DOM_PRICE_SCRIPT` list added on 2026-07-12, and the per-product
`css_selector` for generic sources. Retailers rotate their markup periodically,
so an entire list can go stale at once, silently degrading every product on a
host to a price-less record while the page itself loads fine (HTTP 200, real
title, no block).

That failure is *diagnostically distinct* from the ones Item 15 addressed: a
CAPTCHA page and a 429 both mean "the site refused us", whereas "the page loaded
and nothing matched" means "the markup moved". They call for opposite remedies —
rotate proxies vs. update selectors — but before this item both landed in
`extraction_failed`, so neither was actionable.

Hand-maintaining selector lists makes markup drift a recurring manual task with
an unbounded tail of retailers. Onboarding sources became a data change in Item
18; keeping their selectors working should not stay a code change.

## Decision

When deterministic extraction finds no price on a page that loaded and was not
blocked, an LLM generates a replacement CSS selector from the page's HTML. The
selector is **validated against that same page**, stored per host, and reused by
every subsequent scrape of that host with no further LLM calls.

### `selector_miss` as a distinct extraction status

`ExtractionStatus.SELECTOR_MISS` means: HTTP 200, not classified as
`blocked`/`captcha` by Item 15's `classify_block`, real page content, and no
selector matched a price. `extraction_failed` is retained for the different case
where a selector *did* match but its text would not parse — the markup has not
moved, so regenerating would be the wrong remedy.

Item 15's block classifier runs **first**, unconditionally. Generating a selector
from a CAPTCHA interstitial would store a selector for the block page and
permanently poison the host, so a blocked page can never become a
`selector_miss`. No migration was needed: migration 0006 dropped the
`ck_price_record_extraction_status` CHECK constraint, leaving an open string
column.

### Per-host selector store, one row with a version counter

Selectors are keyed by **normalised host** (lower-case, `www.` stripped) rather
than by product: all products on `currys.co.uk` share markup, so one heal fixes
all of them and only one generation is paid for. Regional storefronts stay
distinct rows — the 2026-07-12 investigation confirmed `amazon.co.uk` and
`amazon.com` ship different markup.

The table holds **one row per host** with an in-place `version` counter, not a
row per generation. The alternative was rejected because the cooldown and
attempt-budget state has to exist for a host that has *never* produced a valid
selector, which a version-per-row table has nowhere to put.

### Validate-then-promote, always

A generated selector is promoted to `active` only after it extracts a plausible
numeric price from the live page, using the same `_normalize_price_text` the
built-in selectors use. Model confidence is recorded but is never the deciding
factor.

This is a *plausibility* gate, not a correctness proof — a selector aimed at a
review count would still extract a plausible number. What it rules out is the far
commoner failure: a hallucinated selector matching nothing, silently replacing a
working selector with a broken one. Targeting the right element is the model's
job, steered by the agent instructions.

### Status governs regeneration, not serving

A stored selector is handed to scrapers whenever one exists, **whatever the
profile's status**. `stale` and `failed` gate *whether regeneration may run*;
they never gate *whether the incumbent selector is used*.

This was not the original implementation, and the difference is not cosmetic —
withholding a non-`active` selector produces a **livelock**, which the live E2E
run surfaced on 2026-07-28: the worker promoted a validated selector, and scrapes
were still recording `selector_miss` two minutes later. Each scrape read the
profile while it was `stale`, got nothing, missed, and its own
`_handle_selector_miss` demoted the freshly-promoted `active` profile back to
`stale`. A host under ordinary scheduled scraping would heal and instantly
un-heal itself, forever, and no unit or integration test could see it because
none of them run a scrape and a promotion concurrently.

The same rule also stops two lesser harms: a `selector_miss` on one product
marks the whole host stale, which would strip a working selector from every
*other* product on that host for the length of the cooldown; and a spurious user
report would do the same to a perfectly healthy host. Re-serving a selector that
genuinely no longer matches costs nothing — it misses again, exactly as it would
have.

### Asynchronous regeneration, off the scrape path

A `selector_miss` marks the host stale and enqueues a Celery task on the
`playwright` queue (browser-capable, and where the LLM credentials are injected).
The existing selectors keep serving meanwhile, so a drift event degrades one
scrape cycle rather than blocking on provider availability.

The task **never raises and never retries**. Retrying would double-charge the
provider for a page that is by construction currently unparseable; the per-host
cooldown is the retry mechanism. Two guards bound the cost:

- `SELECTOR_MAX_REGEN_ATTEMPTS` — consecutive failures park the host as `failed`.
- `SELECTOR_REGEN_COOLDOWN_HOURS` — minimum spacing between attempts, which also
  collapses the N jobs that N products on one host enqueue in the same cycle.

"No credential resolved" is deliberately **not** counted against the budget: it
is a property of the deployment, not the host, and counting it would park every
host as failed on a deployment that simply has no key.

`POST /products/{id}/report-selector-issue` clears a spent budget — a human
asserting the price is wrong is exactly the signal that should revive a parked
host — but still respects the cooldown, so repeated reports do not queue
duplicate work.

### Pydantic AI, provider-agnostic

Generation goes through Pydantic AI rather than a raw provider SDK, so OpenAI,
Anthropic, Azure OpenAI and OpenRouter are all reachable through one code path;
onboarding a provider is a config change. `output_type=SelectorSuggestion`
schema-validates the reply at the framework boundary, so no provider-specific
response parsing exists anywhere in the app. A single long-lived `Agent` carries
the instructions and output type; the model is supplied **per run**, so one agent
serves every credential without being rebuilt.

This supersedes the earlier `anthropic`-SDK-only design recorded in the Item 16
plan.

Azure's two endpoint styles take opposite configuration — the classic
`https://<resource>.openai.azure.com` form requires an API version, the newer
`…/openai/v1` form rejects one. Both mistakes are caught at startup (admin
default) or with a 422 (BYO credential), because the alternative is discovering
them from inside a Celery worker hours after deploy. This is a deliberate
refinement of the plan's "requires both endpoint and api_version", which did not
match the SDK.

### Custom endpoints are deployment-level, not credential-level

`LLM_BASE_URL` routes generation through a gateway, egress proxy, or self-hosted
OpenAI-compatible server. Only `openai` and `anthropic` accept one; OpenRouter's
endpoint is fixed and Azure carries its own, so setting it there is rejected at
startup rather than ignored — silently dropping it would leave traffic on the
public API while the operator believed it was routed away.

It applies to the **admin default only**. A per-product BYO key deliberately does
*not* inherit it and always reaches the provider's real endpoint: that gateway
belongs to the deployer while the key belongs to the user, and forwarding
someone's credential to infrastructure they did not choose is a leak. The
consequence — BYO keys need direct egress — is the correct trade against silently
exposing them. If a deployment needs BYO traffic gatewayed too, the credential
should grow its own `base_url` field so the choice is the key owner's.

### Two credential scopes, no auth system

The repo has no users or roles, so credentials are scoped without one:

1. an env-configured **admin default** (`LLM_PROVIDER`/`LLM_MODEL`/`LLM_API_KEY`)
   — the deployer's key, used for every host;
2. a per-product **bring-your-own** credential, submitted via the API.

Resolution order at generation time: **product BYO → admin default → `None`**.
`None` means generation is disabled — the documented state for a deployment with
no key, not an error. Extraction then falls back to today's behaviour and records
`selector_miss`; nothing crashes.

The product is the only ownership boundary that exists today. BYO keys are
encrypted at rest with Fernet, keyed off the already-validated `SECRET_KEY`, and
decrypted only inside `resolve_llm_config`. They are never logged (not even in
`__repr__`, which reaches logs) and never returned by any endpoint — the read
schema has no field that could carry one, only provider/model and a masked hint.
A credential written under a rotated `SECRET_KEY` decrypts to `None` and falls
back to the admin default rather than surfacing as a 500.

### Graceful fallback everywhere

Extraction order — Amazon: `ld+json` → stored active selector → legacy hardcoded
list → `selector_miss`. Generic: product `css_selector` → stored active selector
→ `selector_miss`. The existing working paths remain the safety net, so the new
capability is purely additive and the LLM is optional at runtime.

## Consequences

**Positive**

- Markup drift becomes a one-time, self-remediated blip instead of ongoing
  silent degradation, and one heal fixes every product on the host.
- Drift is separately observable: `selector_miss_count` on `GET /products/failing`
  sits alongside Item 15's `blocked_count`/`captcha_count`, and each item now
  carries the `host` a heal would act on.
- Selectors are runtime-editable data, queryable and versioned, rather than
  constants requiring a redeploy.
- External users can attach their own provider account per product.

**Negative / accepted**

- Selector generation costs LLM calls. Bounded by the per-host cache (one
  generation per host, not per product or per scrape), the attempt budget, and
  the cooldown.
- Validation cannot prove a selector targets the *right* element, only that it
  extracts a plausible price. Accepted: the alternative — a human-reviewed
  promotion queue — would reintroduce the manual step this item removes.
- A rotated `SECRET_KEY` invalidates stored BYO credentials. Accepted as the
  intended failure mode; affected products degrade to the admin default.
- Per-product BYO credentials have no access control until an auth system exists.
  Documented, and consistent with every other endpoint in the repo today.

## Notes

- `GenericScraper` previously extracted a matched element's **outer HTML** rather
  than its text, so a class name containing a hyphen or digit (`.pdp-price`)
  leaked into the parsed number and could produce a negative price. Latent for
  hand-written selectors, a certainty for LLM-generated ones, so it was fixed
  here; explicit `::text`/`::attr(...)` selectors are still passed through.
- The shared `validation_exception_handler` could not serialise errors raised by
  custom request-body validators (Pydantic v2 puts the exception object in
  `ctx`), turning an intended 422 into a 500. Item 16 added the first such
  validator, so the handler now stringifies `ctx`.
