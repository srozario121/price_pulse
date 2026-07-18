# UK E-commerce Scraping Sources — Research Catalogue

> **Date:** 2026-07-17
> **Deliverable:** Item 18 (research/documentation only — **no scraper code in this deliverable**).
> **Status:** This is a **research shortlist**, NOT a commitment to scrape any listed
> retailer. Inclusion here does not imply approval. **Each candidate requires its own
> Terms-of-Service and robots.txt review before any implementation is scheduled.**

## Purpose & Method

This document catalogues major **UK-based** e-commerce retailers as *candidate future*
scraping sources for Price Pulse, to inform preset prioritisation. It deliberately
excludes sources the platform already supports.

**Already supported (referenced only as precedent, not re-catalogued):**
`amazon` (Playwright/browser), `generic` (CSS selector), `ebay` (httpx + `ld+json`),
`currys` (Playwright), `john_lewis` (Playwright),
`facebook_marketplace` (Playwright + anti-blocking).

**Extraction strategy reminder.** Price Pulse scrapers extract **price + currency**
(GBP for UK sources), preferring `ld+json` / structured data on the fast **httpx**
path (as the `ebay` preset does) and falling back to a **headless-browser
(Playwright)** path for React/SPA client-rendered sites (as `currys` / `john_lewis`
do). The lowest-effort presets are therefore sites that (a) expose price in
`ld+json`/embedded JSON and (b) do not sit behind aggressive bot management.

**Confidence & verification.** Facts were verified via web search and, where the host
allowed it, by fetching the live `/robots.txt`. A **403 on the robots.txt fetch itself**
is recorded as a bot-protection signal, not treated as "unknown". Where a fact could
**not** be verified in this pass it is marked **`unverified / needs spike`** rather than
guessed. A "spike" here means a short throwaway fetch of one real PDP to inspect the
page source for a `<script type="application/ld+json">` product block and to fingerprint
the anti-bot cookies (`_abck`/`bm_sz` = Akamai, `cf-ray` = Cloudflare,
`_px*` = PerimeterX/HUMAN, `datadome` = DataDome).

---

## Catalogue

Columns: **Price via structured data?** (httpx-scrapable `ld+json`/embedded JSON vs
requires a browser) · **Bot protection** · **robots.txt stance toward product PDPs** ·
**Effort** (Low/Medium/High) · **Reuse** (which existing strategy it would clone).

### Tier A — General merchandise / department stores

| Retailer | Domain(s) | Price via structured data? | Bot protection | robots.txt (product PDPs) | Effort | Reuse |
|---|---|---|---|---|---|---|
| Argos | argos.co.uk | Browser/embedded JSON — Next.js `__NEXT_DATA__` holds product/price; not classic `ld+json` on the static path | **Akamai** (robots.txt fetch returned 403 — Akamai edge signal) | `unverified / needs spike` (fetch blocked by Akamai; PDPs believed allowed) | **High** | Playwright like `currys` (likely + anti-blocking) |
| Very | very.co.uk | `unverified / needs spike` — React/SPA storefront (The Very Group); pricing likely client-rendered | `unverified / needs spike` | `unverified / needs spike` | Medium–High | Playwright like `currys` |
| Next | next.co.uk | `unverified / needs spike` | Present — robots.txt fetch returned **403** (edge bot management, vendor unconfirmed) | `unverified / needs spike` (fetch blocked) | Medium–High | Playwright like `currys` |
| Marks & Spencer | marksandspencer.com | `unverified / needs spike` (SFCC-style; JSON-LD plausible) | `unverified / needs spike` | **Allowed** — no blanket PDP disallow; blocks only `/*search?q=`, `/*/cart$`, `/*/account$`, "just-arrived" pages | Medium | httpx + `ld+json` (like `ebay`) if PDP block confirmed, else Playwright |

### Tier B — Electricals / electronics

| Retailer | Domain(s) | Price via structured data? | Bot protection | robots.txt (product PDPs) | Effort | Reuse |
|---|---|---|---|---|---|---|
| AO.com | ao.com | `unverified / needs spike` (electricals PDPs commonly carry JSON-LD) | `unverified / needs spike` (robots.txt fetched cleanly — no aggressive edge block on that path) | **Allowed** — disallows `/c/` (category), `/qa/`, search & review-submission; **PDPs not disallowed** | Low–Medium | httpx + `ld+json` (like `ebay`) if confirmed, else Playwright |

### Tier C — DIY / home improvement / trade / auto

| Retailer | Domain(s) | Price via structured data? | Bot protection | robots.txt (product PDPs) | Effort | Reuse |
|---|---|---|---|---|---|---|
| Screwfix | screwfix.com | Likely `ld+json`/embedded JSON on `/p/` PDPs — `unverified / needs spike` to confirm | `unverified / needs spike` (robots.txt fetched cleanly — good early sign) | **Allowed** — `/p/` PDPs not disallowed (only `/page/u*` etc.) | **Low–Medium** | httpx + `ld+json` (like `ebay`) |
| Wickes | wickes.co.uk | Likely `ld+json` on `/p/` PDPs — `unverified / needs spike` | `unverified / needs spike` (robots.txt fetched cleanly) | **Allowed** — `/p/` PDPs allowed; only blocks malformed `*/p/*/c/*`, `*/p/*/p/*` combos | **Low–Medium** | httpx + `ld+json` (like `ebay`) |
| Halfords | halfords.com | `unverified / needs spike` | `unverified / needs spike` (robots.txt fetched cleanly) | **Allowed** — blocks only `/search*`, `/cart*`, `/account*`; PDPs allowed | Low–Medium | httpx + `ld+json` (like `ebay`) if confirmed, else Playwright |
| B&Q | diy.com | `unverified / needs spike` (Kingfisher group, same parent as Screwfix) | `unverified / needs spike` | `unverified / needs spike` | Medium | httpx + `ld+json` (like `ebay`) — mirror Screwfix findings |

### Tier D — Health & beauty

| Retailer | Domain(s) | Price via structured data? | Bot protection | robots.txt (product PDPs) | Effort | Reuse |
|---|---|---|---|---|---|---|
| Boots | boots.com | Likely `ld+json` (Salesforce Commerce Cloud typically emits JSON-LD Product) — `unverified / needs spike` | `unverified / needs spike` (SFCC storefronts often front Cloudflare) | **Allowed** — AdsBot-Google explicitly allowed `/shop-online`; category/CMS paths blocked, PDPs not | Medium | httpx + `ld+json` (like `ebay`) if confirmed, else Playwright |
| Superdrug | superdrug.com | Likely `ld+json` (Salesforce Commerce Cloud) — `unverified / needs spike` | Present — robots.txt fetch returned **403** (edge block; Cloudflare/SFCC-fronted plausible) | `unverified / needs spike` (fetch blocked) | Medium–High | httpx + `ld+json` if reachable, else Playwright |

### Tier E — Fashion (marketplace-scale, high bot protection)

| Retailer | Domain(s) | Price via structured data? | Bot protection | robots.txt (product PDPs) | Effort | Reuse |
|---|---|---|---|---|---|---|
| ASOS | asos.com | Structured product data present (schema.org / JSON-LD reported) **but gated behind Akamai** | **Akamai Bot Manager** (`_abck`/`bm_sz`; blocks stock Playwright/Scrapy fingerprints) | `unverified / needs spike` | **High** | Playwright **+ anti-blocking** (like `facebook_marketplace`) |
| Zalando UK | zalando.co.uk | Browser — JS-rendered; price/size/stock load after initial paint | Sophisticated anti-bot + geo storefront routing (vendor unconfirmed) | `unverified / needs spike` | **High** | Playwright + anti-blocking |
| Wayfair UK | wayfair.co.uk | Browser — JS-rendered PDPs | **PerimeterX (HUMAN Security)**, reportedly alongside Akamai — aggressive | `unverified / needs spike` | **High** | Playwright + anti-blocking |

### Tier F — Groceries (structural blockers — see caveats)

Grocery sites are a category apart: prices and availability are **basket/store-context
dependent**, they gate behind **postcode / delivery-slot / store selection**, and they
run behind bot management. They are **not** low-effort presets despite high traffic.

| Retailer | Domain(s) | Price via structured data? | Bot protection | robots.txt (product PDPs) | Effort | Reuse |
|---|---|---|---|---|---|---|
| Tesco | tesco.com (`/groceries`) | Browser + context — price requires delivery/store context; some internal JSON endpoints exist | Present (proxy/behaviour countermeasures reported by third parties) | `unverified / needs spike` | **High** | Playwright + session/postcode bootstrap |
| Sainsbury's | sainsburys.co.uk (`/gol-ui`, groceries) | Browser + context | Present | `unverified / needs spike` | **High** | Playwright + session/postcode bootstrap |
| ASDA | asda.com, groceries.asda.com | Browser + context (internal grocery JSON API observed by third parties) | Present | `unverified / needs spike` | **High** | Playwright / internal-API spike + postcode bootstrap |

---

## 1. Prioritised shortlist — top 5 next presets

Ranked by the preset-effort formula: favour low-effort, `ld+json`-exposed,
low-bot-protection, high-traffic UK retailers. All five below returned their
`/robots.txt` cleanly (no edge 403) and allow product PDPs — the cheapest starting set.

| # | Retailer | Rationale (one line) |
|---|---|---|
| 1 | **Screwfix** (screwfix.com) | robots.txt allows `/p/` PDPs, fetched cleanly (no aggressive edge block), high trade traffic — strongest `ebay`-style httpx+`ld+json` candidate; confirm the JSON block in a spike. |
| 2 | **Wickes** (wickes.co.uk) | Same profile as Screwfix — `/p/` PDPs allowed, clean robots fetch, DIY volume — likely a second cheap httpx+`ld+json` preset. |
| 3 | **Halfords** (halfords.com) | robots blocks only search/cart/account; PDPs open; clean fetch; auto/cycling niche with stable SKUs — low-to-medium httpx candidate pending structured-data spike. |
| 4 | **AO.com** (ao.com) | robots explicitly leaves PDPs open (only categories/QA/search blocked), clean fetch, major electricals traffic — promising, gated on confirming JSON-LD presence. |
| 5 | **Boots** (boots.com) | Salesforce Commerce Cloud storefront (JSON-LD Product very likely), robots allows `/shop-online` PDPs — high-traffic health & beauty; medium effort pending a bot-protection/JSON-LD spike. |

**Explicitly deprioritised (high effort — not in the next batch):** Argos & Next
(Akamai / 403 edge), ASOS, Zalando UK, Wayfair UK (Akamai / PerimeterX-HUMAN — need the
`facebook_marketplace` anti-blocking path), and all three grocers (postcode/store-context
blockers). Superdrug sits just behind the shortlist: promising SFCC/JSON-LD profile but
its robots fetch 403'd, so it needs a reachability spike first.

---

## 2. Notes & caveats

- **robots.txt is advisory in this project's log-and-proceed model.** Price Pulse
  records robots stance but does not hard-gate on it; the values above are captured for
  the record and for the required **per-retailer ToS/robots review before
  implementation**, not as an automated block. Record it; do not treat "allowed" as
  legal clearance.
- **A 403 on the robots.txt fetch is itself a bot-protection signal.** Argos, Next and
  Superdrug blocked the plain fetch — expect the same edge posture on their PDPs, so
  budget for the Playwright (and possibly anti-blocking) path, not httpx.
- **Structured-data availability varies by PDP template.** A retailer can emit `ld+json`
  on some product templates and not others (bundles, marketplace/3P listings, made-to-
  order, out-of-stock variants). Confirm on **several** real PDPs in a spike before
  committing to the httpx path; keep a DOM/`__NEXT_DATA__` fallback (as the `amazon` and
  Argos-style presets do).
- **Grocery sites need store/postcode selection.** Tesco, Sainsbury's and ASDA compute
  price/availability against a chosen store or delivery postcode; a scraper must bootstrap
  that session context (cookie/postcode) before any price is meaningful. Treat groceries
  as a distinct sub-project, not a quick preset.
- **Some non-grocery sites also geo/postcode-gate.** Delivery-cost and occasionally
  headline pricing can shift by region; where a currency/price seems context-dependent,
  pin a UK context and record it in the preset config.
- **Currency.** All UK sources should resolve to **GBP**; assert currency in the preset
  rather than assuming it, since multi-region storefronts (Zalando, Wayfair) route by
  locale.
- **Bot-protection vendors reflect third-party reporting and live signals as of
  2026-07-17** and can change without notice. Re-fingerprint at implementation time
  (`_abck`/`bm_sz` = Akamai, `cf-ray` = Cloudflare, `_px*` = PerimeterX/HUMAN,
  `datadome` = DataDome).
- **Notable UK omissions considered but not tabled** (candidates for a later pass):
  Dunelm, JD Sports, Sports Direct, TK Maxx, The Range, IKEA UK (home/fashion);
  Waitrose, Ocado, Morrisons (further groceries — same postcode/store caveat);
  Boohoo / PrettyLittleThing (fashion, likely high bot protection).

---

*Every "unverified / needs spike" cell above is a deliberate honesty marker, not an
oversight: it flags a fact that a short PDP fetch would resolve but which this
desk-research pass could not confirm. Resolve those before an implementation estimate is
treated as firm.*
