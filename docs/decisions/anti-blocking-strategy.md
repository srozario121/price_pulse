# ADR — Anti-Blocking Fetch Hardening

**Status**: Accepted
**Date**: 2026-07-17
**Item**: 15 (Anti-Blocking: Rotating Proxies, Realistic UA/Headers & Stealth Context)

---

## Context

Scheduled, at-scale scraping of real retail sites (Amazon in particular) draws
CAPTCHAs, rate-limits, and IP bans. Before this item the fetch layer used a
single datacenter IP, a stock header set, and — on the Playwright path — a
default `browser.new_context()` that is trivially fingerprintable. A 200-status
CAPTCHA interstitial was mis-recorded as `extraction_failed`, indistinguishable
from a genuinely broken selector. This surfaced during the 2026-07-12 Amazon E2E
investigation.

## Decision

Harden **both** fetch paths (httpx `generic`/`http_client`, Playwright `amazon`)
against blocking, sharing one anti-blocking module so the two paths present an
identical fingerprint.

1. **BYO rotating proxies, per-request pick + rotate-on-block.** Proxies are a
   bring-your-own list in `settings.PROXY_URLS` (comma-separated env, coerced to
   `list[str]` like `CORS_ORIGINS`; empty ⇒ proxying disabled). A fresh proxy is
   picked per fetch; on a detected block the fetch rotates to the next proxy and
   retries up to `MAX_PROXY_ROTATIONS` (default 2), then resolves to
   `BLOCKED`/`CAPTCHA`. A **dead/unreachable** proxy rotates too but does **not**
   consume the block-retry budget, and once every proxy has been tried the call
   fails bounded rather than looping. No managed-provider integration, no sticky
   sessions.

2. **Two new extraction statuses — `BLOCKED` and `CAPTCHA`.** Added to
   `ExtractionStatus`. `BLOCKED` = 429/503 or IP-ban markers after rotations are
   exhausted; `CAPTCHA` = a robot-check interstitial (often HTTP 200). Both are
   diagnostically distinct from `extraction_failed` (selector drift, Item 16) and
   `http_error` (transient).

3. **Drop the `extraction_status` CHECK constraint (migration 0006).** Migration
   0004 restricted the column to three values, so the new values would raise an
   `IntegrityError`. Rather than widen the constraint per status, the column
   becomes a genuinely open `String(20)` — which the app-level `StrEnum` already
   assumes — so Item 16's `selector_miss` and any future status need no DB change.

4. **Stealth = `playwright-stealth` + custom init-script top-ups.** The library
   provides broad evasion; a small versioned `add_init_script` layer patches the
   surfaces detectors probe most (`navigator.webdriver`, `plugins`, `languages`,
   `window.chrome`, WebGL vendor/renderer). Library application is best-effort;
   the custom patches always apply. Only the Amazon Playwright path consumes it.

5. **Shared block classifier in both paths.** `classify_block(status, html)` →
   `BLOCKED | CAPTCHA | None` runs on every response, so a 200-status challenge
   page is caught in both paths. CAPTCHA markers win over status codes so a
   Cloudflare/Amazon challenge served with 503/200 is a challenge, not a bare
   block.

6. **Settings-based config now; hot-reloadable file deferred.** Proxy list,
   rotation budget, and the UA/header pool live in `core/config.py`, consistent
   with existing config patterns. A mounted, hot-updatable file is deferred to a
   future item (aligned with Item 16's externalised-selector direction).

7. **Monitoring on the existing surface.** `find_failing_products` /
   `FailingProductRead` expose each flagged product's failure **category**
   (`blocked` / `captcha` / `other`) plus aggregate `blocked_count` /
   `captcha_count` on `GET /products/failing`, so a block spike is visible
   without a new route.

## Alternatives considered

- **Managed rotating-proxy provider (sticky sessions, provider SDK).** Rejected
  for this item: heavier integration and non-deterministic to test. BYO list +
  per-request rotation covers cold and soft-banned IPs and is trivially testable.
- **Widen the CHECK constraint per new status.** Rejected: every future status
  would need a migration. Dropping it once matches the open-string design.
- **Status codes only for block detection.** Rejected: a 200-status CAPTCHA is
  invisible to status-only detection; HTML-marker classification is required.
- **Per-domain proxy/UA/rate overrides.** Out of scope — global pools only keep
  the config surface and test matrix tight.

## Consequences

- Production expects a residential/rotating `PROXY_URLS` list; empty means direct
  egress (unchanged behaviour, dev-friendly).
- Existing back-off / `Retry-After` / Redis per-domain rate-limit are **reused**,
  not duplicated; proxy rotation and block detection layer on top.
- robots.txt handling is unchanged (log-and-proceed).
- A persistent block now records `BLOCKED`/`CAPTCHA` instead of silently logging
  price-less `extraction_failed` rows, and is visible on `/products/failing`.
