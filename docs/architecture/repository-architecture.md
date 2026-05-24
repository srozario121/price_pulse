# Price Pulse — Repository Architecture

> **Status**: Scaffold stub — full C4 documentation will be added in Item 9 (Claude Code Agents).

## C1 — System Context

```
┌─────────────────────────────────────────────────────────────────┐
│                        Price Pulse                              │
│                                                                 │
│   Users add retail product URLs. The system monitors prices    │
│   on a schedule and alerts users when thresholds are crossed.  │
└────────────────────────┬────────────────────────────────────────┘
                         │
           ┌─────────────┼──────────────────┐
           ▼             ▼                  ▼
     React SPA      FastAPI REST        Retail websites
     (browser)      (backend)           (scraped targets)
```

## C2 — Container Diagram

| Container | Technology | Responsibility |
|-----------|-----------|----------------|
| Frontend SPA | React + Vite + TypeScript | User interface — product dashboard, price charts, alert management |
| Backend API | FastAPI (Python 3.12) | REST API, business logic, ORM layer |
| Celery Worker | Celery + Redis | Async task execution — scraping, notifications |
| Celery Beat | Celery Beat | Periodic scheduling — trigger scrapes every N minutes |
| PostgreSQL | Postgres 15 | Persistent storage — products, price history, alerts, notification logs |
| Redis | Redis 7 | Celery broker + result backend |
| Nginx | Nginx 1.27 | Static file server (frontend) + reverse proxy to backend API |

## Directory Structure

```
price_pulse/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # Route handlers (thin — delegate to services)
│   │   ├── core/            # Config, DB, logging, exceptions
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── schemas/         # Pydantic v2 request/response schemas
│   │   ├── scrapers/        # Pluggable scraper adapters
│   │   ├── services/        # Business logic layer
│   │   ├── tasks/           # Celery task definitions
│   │   └── workers/         # Celery app factory
│   ├── alembic/             # Database migrations
│   └── tests/               # unit/, integration/, e2e/
├── frontend/
│   └── src/
│       ├── api/             # Typed API client
│       ├── components/      # Shared React components
│       ├── hooks/           # react-query hooks
│       ├── pages/           # Route-level page components
│       └── store/           # Zustand global UI state
├── docker/                  # Dockerfiles + Nginx config
├── docs/architecture/       # This document
├── config/                  # Quality thresholds
└── .github/workflows/       # CI pipeline
```

## Data Flow

```
User adds URL
  → POST /api/v1/products
  → Product row created in PostgreSQL

Celery Beat (every 30 min)
  → Triggers scrape_product(product_id) task
  → Worker fetches HTML from retail URL
  → Adapter extracts price
  → price_service deduplicates (by HTML hash) + stores PriceRecord
  → alert_service evaluates active alerts
  → If threshold crossed → send_notification task dispatched

Frontend (60s poll)
  → GET /api/v1/products/{id}/prices
  → PriceChart re-renders with latest data
```
