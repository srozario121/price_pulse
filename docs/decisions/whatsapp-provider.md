# ADR — WhatsApp Notification Provider

**Status**: Pending decision (spike findings recorded; implementation deferred pending approval)  
**Date**: 2026-05-26  
**Item**: 5 (Celery Task Infrastructure)

---

## Context

Item 5 adds WhatsApp as a third notification channel alongside email and webhook. The `send_notification` task already has a stub (`whatsapp_stub`) wired end-to-end — channel enum, model column, schema field, and task routing are all in place. Real delivery requires choosing a provider SDK and adding auth configuration.

---

## Options evaluated

### 1 — Meta WhatsApp Business Cloud API (direct)

| Dimension | Assessment |
|---|---|
| Sandbox / test numbers | ✅ Up to 5 test numbers on free tier; no real WhatsApp account needed |
| Python SDK | ⚠️ No official Python SDK; use raw `httpx` calls to Graph API |
| Async support | ✅ `httpx.AsyncClient` works natively |
| Per-message pricing | ✅ First 1,000 business-initiated conversations/month free |
| Rate limits | 1,000 conversations/day on free tier |
| Delivery receipts | ✅ Webhook callbacks (read/delivered) |
| Setup complexity | 🔴 High — requires Facebook Developer account, Business Manager verification, phone number registration |

### 2 — Twilio

| Dimension | Assessment |
|---|---|
| Sandbox / test numbers | ✅ WhatsApp Sandbox available immediately; no approval needed for dev |
| Python SDK | ✅ `twilio` package; has async support via `aiohttp` adapter |
| Async support | ⚠️ Async wrapper available but not idiomatic |
| Per-message pricing | 🔴 $0.005/message + $0.0050 WhatsApp channel fee; adds up at scale |
| Rate limits | No hard limits on sandbox; production limits depend on tier |
| Delivery receipts | ✅ Webhook status callbacks |
| Setup complexity | ✅ Low — sandbox ready in minutes with a single `TWILIO_AUTH_TOKEN` |

### 3 — Vonage (formerly Nexmo)

| Dimension | Assessment |
|---|---|
| Sandbox / test numbers | ✅ Sandbox available |
| Python SDK | ✅ `vonage` Python SDK; reasonably maintained |
| Async support | ⚠️ Sync SDK; would need `asyncio.run_in_executor()` wrapping |
| Per-message pricing | ⚠️ ~$0.0085/message; slightly higher than Twilio |
| Rate limits | Standard tier: 100 msg/s |
| Delivery receipts | ✅ Webhook callbacks |
| Setup complexity | ✅ Low-medium |

### 4 — MessageBird / Bird

| Dimension | Assessment |
|---|---|
| Sandbox / test numbers | ⚠️ Limited sandbox; production setup needed quickly |
| Python SDK | ⚠️ `messagebird` SDK; less actively maintained |
| Async support | ❌ Sync-only SDK |
| Per-message pricing | ⚠️ ~$0.005/message but varies by destination country |
| Rate limits | Standard tier; not clearly documented |
| Delivery receipts | ✅ Webhook callbacks |
| Setup complexity | ✅ Low |

---

## Recommendation

**Twilio** for development and early production:

1. **Sandbox**: Zero-friction onboarding — ready in minutes with no Meta Business verification. This unblocks development immediately.
2. **Python SDK**: Mature, well-documented, and widely used in the Python ecosystem.
3. **Async gap**: The sync SDK is a minor friction point. Mitigation: wrap calls in `asyncio.get_event_loop().run_in_executor(None, fn)` until an async client is available, or use the raw REST API directly via `httpx.AsyncClient`.
4. **Upgrade path**: When volume warrants it, migrate to the Meta Cloud API for cost savings. The `channel='whatsapp'` abstraction in `send_notification` means the provider swap requires only changes inside the task's `whatsapp` branch.

---

## Implementation plan (follow-on item)

Once this ADR is approved, the follow-on task replaces the `whatsapp_stub` in `app/tasks/notify.py`:

1. Add `twilio>=9.0` to `backend/pyproject.toml` runtime deps.
2. Add to `Settings`: `TWILIO_ACCOUNT_SID: str = ""`, `TWILIO_AUTH_TOKEN: str = ""`, `TWILIO_WHATSAPP_FROM: str = ""` (e.g. `whatsapp:+14155238886` for sandbox).
3. Add corresponding entries to `.env.example`.
4. Replace the `whatsapp_stub` logger.warning block in `send_notification` with a Twilio REST call.
5. Add unit tests: real Twilio client mocked; `status='sent'` on 201, `status='failed'` on `TwilioRestException`.
6. Add integration test: `channel='whatsapp'` → `NotificationLog.status='sent'` (mocked Twilio).

---

## Decision deferred

This ADR documents the spike findings. No provider SDK has been added to `pyproject.toml`. The `whatsapp_stub` behaviour (log WARNING, set `status='sent'`) is the production behaviour until this ADR is approved and the follow-on item is implemented.
