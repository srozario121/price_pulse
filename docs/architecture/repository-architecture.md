# Price Pulse — Repository Architecture

C4-style documentation for the Price Pulse monorepo. Three levels: system context (C1), containers (C2), and backend components (C3).

---

## C1 — System Context

```
                        ┌─────────────────────────────────────────────────────┐
                        │                    Price Pulse                      │
                        │                                                     │
                        │  Users add retail product URLs. The system          │
                        │  monitors prices on a schedule and alerts users     │
                        │  when price thresholds are crossed.                 │
                        └─────────────────────────────────────────────────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    ▼                        ▼                        ▼
             ┌─────────────┐       ┌─────────────────┐     ┌──────────────────┐
             │  React SPA  │◄─────►│  FastAPI REST   │────►│  Retail websites │
             │  (browser)  │       │   (backend)     │     │  (scraped URLs)  │
             └─────────────┘       └─────────────────┘     └──────────────────┘
                                           │
                               ┌───────────┼───────────┐
                               ▼           ▼           ▼
                          PostgreSQL     Redis    Celery workers
```

**Actors**
- **User** — interacts with the React SPA via a browser; adds product URLs, views price history, configures alerts
- **Retail websites** — external HTTP/HTTPS endpoints scraped by Celery workers (Amazon via Playwright, others via httpx + CSS selectors)

---

## C2 — Container Diagram

| Container | Technology | Port | Responsibility |
|-----------|-----------|------|----------------|
| Frontend SPA | React 18 + Vite + TypeScript + Nginx 1.27 | 80 | Static file serving (production) + reverse proxy to `/api/v1` |
| Backend API | FastAPI + Uvicorn (Python 3.12) | 8000 | REST API `/api/v1`, business logic, ORM layer, health check |
| Celery Worker | Celery 5 + asyncio pool | — | Default queue — scraping (generic/httpx), notifications (email/webhook) |
| Celery Beat | Celery Beat + redbeat | — | Periodic scheduling — fires `scrape_product` for every active product |
| Celery Playwright | Celery 5 + Playwright (Microsoft image) | — | `playwright` queue — Amazon scraping via Chromium headless browser |
| PostgreSQL | Postgres 16-alpine | 5432 | Persistent storage — products, price history, alerts, notification logs |
| Redis | Redis 7 | 6379 | Celery broker + result backend + per-domain rate-limit cache + redbeat scheduler state |
| Nginx | Nginx 1.27-alpine | 80 | Static file server (frontend SPA) + reverse proxy to backend API |

**Network topology**: all containers share a single Docker Compose network. Nginx is the only container exposed to the host on port 80. Backend is reachable from Nginx on the internal network at `http://backend:8000`.

---

## C3 — Backend Component Diagram

The backend (`backend/app/`) follows a strict layered architecture. Data flows top-down; no layer imports from a layer above it.

```
┌─────────────────────────────────────────────────┐
│  API layer  (app/api/v1/)                       │
│  products.py · prices.py · alerts.py · router   │
└──────────────────────┬──────────────────────────┘
                       │ calls
┌──────────────────────▼──────────────────────────┐
│  Service layer  (app/services/)                 │
│  price_service · alert_service · notifications  │
└──────┬───────────────────────────┬──────────────┘
       │ calls                     │ calls
┌──────▼──────────┐    ┌───────────▼──────────────┐
│ Scraping layer  │    │  Celery tasks             │
│ (app/scrapers/) │    │  (app/tasks/)             │
│ base · generic  │    │  scrape · schedule        │
│ amazon · http_  │    │  notify                   │
│ client · regist │    │                           │
│ ry · exceptions │    │  (app/workers/)           │
└─────────────────┘    │  celery_app               │
                       └───────────────────────────┘
       ┌───────────────────────────────────────────┐
       │  ORM models  (app/models/)                │
       │  product · price_history · alert          │
       │  notification_log · enums                 │
       └───────────────────────────────────────────┘
       ┌───────────────────────────────────────────┐
       │  Pydantic schemas  (app/schemas/)         │
       │  product · price · alert · notification   │
       │  scraper · common                         │
       └───────────────────────────────────────────┘
       ┌───────────────────────────────────────────┐
       │  Core  (app/core/)                        │
       │  config · database · logging · exceptions │
       └───────────────────────────────────────────┘
```

### API layer (`app/api/v1/`)

Thin route handlers — validate input (FastAPI dependency injection + Pydantic), call a service function, return a typed response schema. No business logic lives here.

- `products.py` — CRUD for tracked products; `POST /products/{id}/scrape` returns 202 and dispatches `scrape_product.delay()`
- `prices.py` — paginated price history with optional `from_dt`/`to_dt` date-range filtering
- `alerts.py` — CRUD for price alert thresholds; optional `?product_id` and `?is_active` filters
- `router.py` — aggregates the three routers into `api_router` mounted at `/api/v1` in `main.py`

### Service layer (`app/services/`)

The only layer that writes to the database. Route handlers and Celery tasks both call into services; services never call route handlers.

- `price_service.py` — `record_price()`: deduplicates by `raw_html_hash`; inserts `PriceRecord`; calls `alert_service.evaluate_alerts()` on successful extraction
- `alert_service.py` — `evaluate_alerts()`: loads active alerts; checks 24h cooldown (`Settings.ALERT_COOLDOWN_HOURS`); compares price against threshold; sets `notified_at` and calls `notifications.notify_alert()` on threshold crossing
- `notifications.py` — thin dispatch shim: `notify_alert(alert_id)` calls `send_notification.delay(alert_id)`; decouples alert evaluation from Celery broker availability

### Scraping layer (`app/scrapers/`)

Pluggable adapters per retail source type. All adapters return `ScrapedResult` (defined in `schemas/scraper.py`); HTTP errors and extraction failures are encoded as `extraction_status` rather than raised as exceptions.

- `base.py` — abstract `BaseScraper` with `fetch(url) -> ScrapedResult` and `_compute_hash(html) -> str` (SHA-256)
- `http_client.py` — shared async httpx client: 8-UA string rotation, per-domain Redis rate limiting (key `rate_limit:{domain}`), robots.txt compliance cache (key `robots:{domain}`, 1h TTL, log-and-proceed), retry on 5xx/429/403 with 1s/2s/4s back-off
- `generic.py` — `GenericScraper`: uses `parsel.Selector` with `Product.css_selector`; currency mapped from symbol via hardcoded dict
- `amazon.py` — `AmazonScraper`: per-task Playwright browser context; extracts price from `ld+json` schema.org blocks via `page.evaluate()`
- `registry.py` — `SourceType` enum mirroring `source_type_enum` Postgres ENUM; `get_scraper(source_type)` factory; raises `UnknownSourceError` for unregistered types
- `exceptions.py` — `ScraperError` (base) and `UnknownSourceError(ScraperError)`

### ORM models (`app/models/`)

SQLAlchemy 2.x async ORM models. No business logic — field definitions, relationships, and server-side defaults only.

- `product.py` — `Product`: tracked retail URL; `source_type` native Postgres ENUM; `css_selector` for generic scraper
- `price_history.py` — `PriceRecord`: stores every scrape attempt; `price` + `currency` nullable (extraction failures stored with `price=NULL`); `extraction_status` column
- `alert.py` — `PriceAlert`: threshold + direction + channel + contact fields (`webhook_url`, `whatsapp_number`); `notified_at` denormalized last-triggered timestamp
- `notification_log.py` — `NotificationLog`: per-delivery audit record; JSON payload; `status` (`pending`/`sent`/`failed`)
- `enums.py` — `ExtractionStatus` Python enum (`ok`/`extraction_failed`/`http_error`)

### Pydantic schemas (`app/schemas/`)

Strictly separated from ORM models. Each domain has `Base`, `Create`, `Read`, `Update` variants. `Read` schemas use `model_config = ConfigDict(from_attributes=True)` for ORM serialisation.

- `product.py`, `price.py`, `alert.py`, `notification.py` — domain request/response types
- `scraper.py` — `ScrapedResult` (scraper layer output); `ExtractionStatus` enum reference
- `common.py` — `PaginatedResponse[T]` (items, total, limit, offset) and `ScrapeJobResponse` (task_id, status, product)

### Core (`app/core/`)

Infrastructure wiring imported at app startup. No domain logic.

- `config.py` — `Settings(BaseSettings)`: all env vars validated at startup; `CORS_ORIGINS` defaults to `["*"]` in DEBUG mode, required otherwise; `SECRET_KEY` min 32 chars; exports singleton `settings`
- `database.py` — `create_async_engine`, `AsyncSessionLocal`, `get_db` generator, `Base = declarative_base()`
- `logging.py` — structlog configured at import time; `ConsoleRenderer` when `DEBUG=true`, JSON otherwise
- `exceptions.py` — FastAPI exception handlers for `HTTPException`, `RequestValidationError`, and catch-all 500

---

## Module domain-grouping convention

This section is the canonical reference for the `module-grouping-reviewer` agent.

**Promotion criteria** — a set of flat `.py` files in `backend/app/` is a candidate for subpackage promotion when **both** conditions hold:

1. **Shared types (Criterion 1)**: the files import each other's types, or they share a significant portion of their `schemas/` or `models/` imports (same domain noun appears in both import paths)
2. **Low fan-in (Criterion 2)**: none of the files is a standalone utility used across more than 3 unrelated workflows (check fan-in by grepping external import sites across `backend/app/`)

**Rejection cases** — a file that passes Criterion 1 but fails Criterion 2 stays flat. Utilities with high fan-in (`database.py`, `config.py`, `exceptions.py`) are canonical examples: every layer imports them, so they cannot be grouped into any single subpackage without creating circular dependencies.

**Convention**: modules sharing a domain noun and importing each other's types are candidates for subpackage promotion. Standalone utilities with high fan-in (> 3 unrelated callers) stay flat. Convention enforced by `module-grouping-reviewer.agent.md`.

**Current state**: the existing subdirectory grouping (`api/v1/`, `core/`, `models/`, `schemas/`, `scrapers/`, `services/`, `tasks/`, `workers/`) already encodes the layered architecture correctly. Flat files within each subdirectory should be reviewed against these criteria as the codebase grows.

---

## Data Model

ASCII ER diagram showing the four core ORM tables and their foreign key relationships.

```
┌──────────────────────────────────┐
│ Product                          │
│──────────────────────────────────│
│ id              BigInt  PK       │
│ name            String  NOT NULL │
│ url             String  UNIQUE   │
│ source_type     ENUM    NOT NULL │  (generic|amazon|ebay|currys)
│ css_selector    String  NULL     │
│ css_selector_   String  NULL     │
│   currency                       │
│ is_active       Boolean          │
│ created_at      DateTime         │
│ updated_at      DateTime         │
└──────────┬───────────────────────┘
           │ 1
           │
    ┌──────┴────────────────────────────┐
    │                                   │
    │ N                                 │ N
┌───▼──────────────────────────┐  ┌────▼──────────────────────────────┐
│ PriceRecord                  │  │ PriceAlert                        │
│──────────────────────────────│  │───────────────────────────────────│
│ id              BigInt  PK   │  │ id              BigInt  PK        │
│ product_id      FK→Product   │  │ product_id      FK→Product        │
│ price           NUMERIC NULL │  │ threshold_price NUMERIC NOT NULL  │
│ currency        Varchar NULL │  │ direction       ENUM    NOT NULL  │  (above|below)
│ raw_html_hash   Varchar NULL │  │ is_active       Boolean           │
│ extraction_     Varchar      │  │ channel         ENUM    NOT NULL  │  (email|webhook|whatsapp)
│   status                     │  │ webhook_url     Varchar NULL      │
│ captured_at     DateTime     │  │ whatsapp_number Varchar NULL      │
└──────────────────────────────┘  │ notified_at     DateTime NULL     │
                                  └──────────────┬────────────────────┘
                                                 │ 1
                                                 │ N
                                  ┌──────────────▼────────────────────┐
                                  │ NotificationLog                   │
                                  │───────────────────────────────────│
                                  │ id              BigInt  PK        │
                                  │ alert_id        FK→PriceAlert     │
                                  │ channel         ENUM    NOT NULL  │
                                  │ payload         JSON    NULL      │
                                  │ sent_at         DateTime          │
                                  │ status          ENUM    NOT NULL  │  (pending|sent|failed)
                                  └───────────────────────────────────┘
```

**Indexes**
- `ix_price_record_product_captured` on `(product_id, captured_at DESC)` — paginated price history
- `ix_price_record_html_hash` on `(raw_html_hash)` — deduplication lookups
- `ix_price_alert_product_active` on `(product_id, is_active)` — alert evaluation
- `ix_notification_log_alert_sent` on `(alert_id, sent_at DESC)` — notification history

**Cascade policy**: full `cascade="all, delete-orphan"` on all FK relationships. Deleting a `Product` removes all its `PriceRecord` and `PriceAlert` rows; deleting a `PriceAlert` removes its `NotificationLog` rows.

---

## Architecture Decision Records

| ADR | Date | Status | Summary |
|-----|------|--------|---------|
| [WhatsApp Provider](../decisions/whatsapp-provider.md) | 2026-05-26 | Pending | Spike comparing Meta Cloud API, Twilio, Vonage, and Bird; implementation deferred pending approval |
