# ADR — Configurable Monitoring Sources (UK)

**Status**: Accepted
**Date**: 2026-07-17
**Item**: 18 (Configurable Monitoring Sources — eBay, Currys, John Lewis & Facebook Marketplace Presets)

---

## Context

Before this item the platform could only monitor two source types: `amazon`
(Playwright) and `generic` (CSS selector). The scraping layer *advertised* more —
the `SourceType` enum in **both** `models/product.py` (native Postgres
`source_type_enum`) and `scrapers/registry.py` listed `ebay` and `currys` — but
neither had a registered scraper, so a product created with those types was
accepted at create time and then failed **every** scrape with
`UnknownSourceError`. The two enums could also drift, and neither was the
authority. Adding a retailer meant an enum change, an `ALTER TYPE … ADD VALUE`
migration, and a new `if source_type == …` branch.

## Decision

Turn the set of monitoring sources into a **data-driven, DB-backed registry** and
ship four new UK sources on top of it.

1. **DB-backed `SourcePreset` table (runtime-editable), not a config file or
   `Settings`.** Keyed by `source_type`, carrying `label`, `host_patterns`,
   extraction `strategy`, `default_css_selector`/`_currency`, target Celery
   `queue`, `enabled`, and `version`. Seeded with six built-ins (`amazon`,
   `generic`, `ebay`, `currys`, `john_lewis`, `facebook_marketplace`) by migration
   `0007` (idempotent seed). Onboarding a retailer becomes a data change.

2. **`product.source_type` migrated from the native Postgres enum → validated
   `String` (migration `0008`).** The native `source_type_enum` type is dropped;
   existing values are preserved (`USING source_type::text`). This eliminates an
   `ALTER TYPE` migration per retailer and matches the `extraction_status`
   open-string convention (Items 15–17). The registry — not a Python `Enum` — is
   the single source of truth for valid source types.

3. **Validation at the API boundary, not the schema.** `source_type` is a plain
   `str` in the Pydantic schema; `POST`/`PATCH /products` reject any value that is
   not a known **enabled** preset key with **422**. A DB-backed check cannot run
   inside a synchronous Pydantic validator, and 422 is the correct "bad input"
   signal. This closes the old "accepted at create, `UnknownSourceError` at
   scrape" trap for `ebay`/`currys`. No URL-host→preset inference this item.

4. **One registry-driven source of truth.** Both divergent `SourceType` enums are
   removed. `get_scraper` and `queue_for_source_type` resolve from the
   `SourcePreset` registry (async, DB-backed); a `strategy` → scraper-class map
   (`_STRATEGY_REGISTRY`) is the only thing that stays in code, since the scraper
   classes *are* code.

5. **Queue routing is data-driven (preset-carried), not a hardcoded frozenset.**
   Each preset declares its `queue`: eBay → `default` (httpx + `ld+json`); Currys,
   John Lewis, Facebook Marketplace, Amazon → `playwright`; generic → `default`.

6. **Shared `PlaywrightScraper` base for the new browser scrapers.** Currys, John
   Lewis and Facebook Marketplace share a base (`playwright_base.py`) that
   encapsulates the stealthed context, per-request proxy rotation with bounded
   rotate-on-block retry (Item 15), block classification **before** extraction,
   and `ld+json`-first extraction with a configurable CSS-selector DOM fallback.
   Subclasses supply only their selectors and default currency. `amazon.py`
   predates this base and keeps its own bespoke DOM script.

7. **Facebook Marketplace — full scraper, hard-gated on Item 15.** Implemented on
   the `playwright` queue using Item 15's anti-blocking module. Its login wall /
   bot-check classifies via `classify_block` **plus** FB-specific markers as
   `BLOCKED` (login wall) / `CAPTCHA` (checkpoint) — **never** `extraction_failed`
   (which Item 16 reserves for genuine selector drift and which must never feed
   selector generation). Ships **enabled**, unauthenticated, best-effort.

8. **eBay UK on the httpx path.** eBay serves fully-rendered HTML with an
   `application/ld+json` Product block, so it needs no browser: it fetches via the
   shared httpx client and parses price/currency from structured data, with a
   meta/DOM selector fallback.

9. **UK scope only.** Non-UK sources are out of scope. A deep-research catalogue of
   candidate UK retailers (`docs/research/uk-ecommerce-sources.md`) proposes a
   prioritised shortlist for future presets — research, not a commitment.

## Terms-of-Service / robots posture (Facebook Marketplace)

Marketplace is login-walled, ToS-restrictive toward automated access, and
bot-protected. This scraper runs **unauthenticated** (no credential handling, no
auth-wall circumvention) and treats the login wall as a first-class `BLOCKED`
outcome rather than attempting to bypass it. robots.txt handling is unchanged from
Item 15 (log-and-proceed). Operators are responsible for their own ToS/robots
compliance per source; the preset ships enabled but a login wall simply surfaces
the product on `/products/failing` instead of recording a price.

## Alternatives considered

- **Config-file / `Settings`-based preset list.** Rejected: a DB table is
  runtime-editable and mirrors Item 16's `SelectorProfile` direction.
- **Keep the native enum, widen it per retailer.** Rejected: every new retailer
  needs an `ALTER TYPE` migration; a validated string column needs none.
- **Schema-level `source_type` validation.** Not possible against a DB registry
  inside a sync Pydantic validator; route-level validation returning 422 is used.
- **Host→preset auto-detection.** Deferred: avoids host-matching ambiguity; the
  caller still supplies `source_type` explicitly.
- **Refactor `amazon.py` onto the shared Playwright base.** Rejected for this
  item: Amazon's bespoke buy-box DOM script and its test suite make the risk
  outweigh the DRY benefit; the base serves the three new browser scrapers.

## Consequences

- `ebay`/`currys` products now scrape instead of failing; `john_lewis` and
  `facebook_marketplace` are new, enabled sources.
- `get_scraper`/`queue_for_source_type` are now `async` and take an
  `AsyncSession`; all call sites (scrape task, schedule sync, product routes,
  on-demand scrape, E2E hooks) pass the session they already hold.
- `product.source_type` is a `varchar`; the native `source_type_enum` type no
  longer exists. Adding a UK retailer is a `SourcePreset` row + a scraper class
  for a new `strategy` (existing strategies need no code).
- `GET /api/v1/sources` exposes the enabled presets so the frontend "add product"
  form is populated from the backend registry.
- `find_failing_products` / `GET /products/failing` are unchanged — they key off
  `extraction_status`, so new source types are attributed correctly with no code
  change.
