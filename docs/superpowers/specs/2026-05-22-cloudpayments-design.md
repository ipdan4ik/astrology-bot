# Cloudpayments payments — design

**Status:** Direction approved (approach **A + A**); full section-by-section review **pending**. Work
**deferred** at the user's request — design saved to resume later. No implementation has started.

> First real (non-Stars) payment provider. Card payments (RUB) initiated from inside the bot,
> confirmed via an HTTP webhook. This spec is the first of three payment sub-projects; it builds the
> shared HTTP-provider plumbing that Cryptobot will later reuse.

## Goal

Let a tenant bot accept **card payments via Cloudpayments** alongside Telegram Stars, with the user
choosing the payment method at checkout. Credentials may come from either the **platform**
(superadmin's merchant account) or the **bot owner** (their own merchant account), selected per tenant
by a "franchise type".

## Decisions (from brainstorming)

1. **Cloudpayments first.** Cryptobot is a later sub-project that reuses this plumbing.
2. **Multiple payment methods, choice at checkout.** A plan can be bought via Stars (XTR) or card
   (RUB); `/buy` shows a method picker.
3. **Franchise type = credential source only (for now).** It decides *whose* Cloudpayments keys are
   used. The money-flow consequences (payout vs license, commission) are a **separate sub-project**
   and explicitly out of scope here.
4. **Pricing model — Approach A: `plan_prices` side table.** Plans keep their base `price_cents` +
   `currency` (XTR) for backward compatibility; additional rows add other currencies (RUB, ...).
5. **Franchise storage — Approach A: `franchise_type` column on `Tenant`.** Credentials live in the
   existing `PaymentProvider.config_enc` (Fernet); a resolver picks the platform's or the owner's row
   by franchise type.

## Out of scope (separate sub-projects / later)

- **Money flow & accounting by franchise type** — payout-eligibility (platform merchant → `Payout`
  minus commission) vs license fee (owner merchant → `TenantLicense`). Deferred per user.
- **Cryptobot** — sub-project C, reuses the HTTP-provider plumbing built here.
- **Refunds** — `CloudpaymentsProvider.refund` keeps raising `NotImplementedError`; the Cloudpayments
  refund API is wired later.
- **Cloudpayments recurring/auto-charge** (Recurrent API). One-time orders only; subscriptions are
  renewed by the user re-purchasing, exactly as the Stars flow does today.

## Existing seams this builds on

- `payments/base.py` — `PaymentProvider` Protocol (`create_invoice`, `verify_callback`, `refund`),
  `Invoice`, `PaymentEvent`, `PaymentNotSupportedInApiError`.
- `payments/registry.py` — `PROVIDERS` dict + `provider_for_kind(kind)`. Currently only `tg_stars`.
- `db/models.py::PaymentProvider` — `tenant_id`, `kind` (`tg_stars|cloudpayments|cryptobot`),
  `config_enc: bytes`, `active`. Reused as-is.
- `db/models.py::Payment` — `external_id`, `status` (`pending|paid|refunded|failed`), `provider_id`,
  `metadata_json`. Reused as-is.
- `domain/billing.py::fulfill_payment(payment_id, external_id)` — **idempotent**: only the
  pending→paid transition credits, so redelivered webhooks never double-credit. Reused as-is.
- `common/crypto.py` — Fernet via `bot_token_enc_key`; today only `encrypt_token`/`decrypt_token`.
- `tasks/delivery.py` — pattern for sending a bot message from a non-bot process (builds a `Bot` from
  the tenant's decrypted token). Reused to notify the user after async webhook fulfillment.

## Components

### 1. Crypto helpers (`common/crypto.py`)
Add `encrypt_json(data: dict) -> bytes` / `decrypt_json(blob: bytes) -> dict` (JSON-serialize then
reuse the existing Fernet). Provider config is a dict (`{"public_id": ..., "api_secret": ...}`).

### 2. Schema / migrations
- **`Tenant.franchise_type`**: `str`, default `"platform_merchant"`; values
  `platform_merchant | own_merchant`. Migration adds the column with the default.
- **`plan_prices` table**: `(id, tenant_id, plan_kind ['subscription'|'package'], plan_id, currency,
  price_cents, active, created_at)`, indexed by `(plan_kind, plan_id)`. A plan's base
  `price_cents`/`currency` remains the implicit XTR price; `plan_prices` rows add the rest.
- `PaymentProvider` / `Payment` need no schema change.

### 3. Cloudpayments provider (`payments/cloudpayments.py`)
`CloudpaymentsProvider` (`kind = "cloudpayments"`), constructed with the resolved config
(public_id + api_secret).
- `create_invoice(...)`: `POST https://api.cloudpayments.ru/orders/create` (HTTP Basic:
  public_id:api_secret) with `InvoiceId = payment.id`, `Amount`, `Currency` (RUB), `Description`.
  Returns `Invoice` whose payload carries the order's pay `Url` (the link sent to the user).
- `verify_callback(body, headers)`: compute `base64(HMAC-SHA256(raw_body, api_secret))` and
  constant-time compare to the `Content-HMAC` header. Body is `application/x-www-form-urlencoded`
  (Cloudpayments `Pay` notification). Extract `InvoiceId`, `TransactionId`, `Amount`, `Currency` →
  `PaymentEvent`. Raise on mismatch.
- `refund(...)`: `raise NotImplementedError` (out of scope).

### 4. Provider config resolution (`domain/providers.py`)
- Generalize beyond the hardcoded `tg_stars` filter: `get_active_provider(session, tenant_id, kind)`.
- `resolve_provider_config(session, tenant_id, kind) -> dict | None`: read the tenant's
  `franchise_type`; for `own_merchant` use the tenant's own `PaymentProvider` row, for
  `platform_merchant` use the platform tenant's row; decrypt `config_enc` via `decrypt_json`.
- Register `CloudpaymentsProvider` in `registry.PROVIDERS`. `provider_for_kind` returns an instance
  built from the resolved config (signature/construction adjusted so HTTP providers receive config).

### 5. HTTP webhook route (`api/routes/payments.py`, new; mounted in `api/app.py`)
`POST /payments/cloudpayments`:
1. Read raw body + `Content-HMAC` header.
2. Parse `InvoiceId` → load `Payment` → its `tenant_id` → `resolve_provider_config(...,
   "cloudpayments")`.
3. `verify_callback(body, headers)` with that secret. The HMAC is the authentication; `InvoiceId` is
   only a lookup key.
4. On valid: `fulfill_payment(payment_id=InvoiceId, external_id=TransactionId)`; on the real
   transition, enqueue a bot notification (see §7). Respond `{"code": 0}`.
5. Invalid HMAC / unknown invoice → log + respond `{"code": 13}` (rejected, no crediting, no retry
   storm). Already-paid (duplicate) → `{"code": 0}` (idempotent ack).

### 6. Public API create-invoice (`api/routes/me.py`)
Replace the Cloudpayments branch of the `_create_invoice_via_provider` 501 stub: record a pending
`Payment` (currency from the chosen `plan_prices` row), call `create_invoice`, and **return the pay
URL** in the response. Stars still raises `PaymentNotSupportedInApiError` → 501.

### 7. Bot `/buy` method picker (`bot/handlers/buy.py`)
- After the user picks a plan, show a row of payment-method buttons — one per active provider that has
  a price for that plan (Stars if an XTR price exists; Card if a RUB `plan_prices` row + an active
  Cloudpayments provider exist).
- **Stars** → existing `record_pending_payment` + `bot.send_invoice` path, unchanged.
- **Card** → `record_pending_payment(currency=RUB, provider_id=<cloudpayments row>)` →
  `create_invoice` → send an inline **URL button** to the Cloudpayments pay page.
- **Notification after webhook:** the `successful_payment` handler covers Stars only. For card, the
  webhook runs in the API process, so after `fulfill_payment` enqueue a delivery task (reuse the
  `tasks/delivery.py` decrypt-token pattern) to send `buy.payment_success` to the user's chat.

### 8. Owner console — own-merchant keys (`bot/handlers/owner_console.py`)
`/manage` → "💳 Платежи" → FSM collecting **Public ID** + **API Secret** for `own_merchant` tenants;
store via `encrypt_json` into a `PaymentProvider(kind="cloudpayments")` row on the tenant. **Delete
the message containing the secret** after capture. Show the notification URL the owner must paste into
their Cloudpayments dashboard (`{base}/payments/cloudpayments`).

### 9. Superadmin — platform-merchant keys (`bot/handlers/master_superadmin.py`)
`/admin` → Cloudpayments section: enter the **platform** Public ID + API Secret once
(`PaymentProvider(kind="cloudpayments")` row on the platform tenant). Used by every
`platform_merchant` tenant.

### 10. i18n
New `buy.*` (method picker, card button, pay-link prompt), `owner.payments.*`, `admin.payments.*`
keys seeded in all 10 platform languages (insert-only seed; see the i18n-seed note).

### 11. Payout currency guard (`domain/payouts.py`)
`calculate_payout` currently sums `amount_cents` across **all** currencies — once RUB payments exist
this silently mixes XTR + RUB. Minimal guard: make the sum **currency-scoped** (one payout per
currency, or filter by currency). Full franchise-aware accounting stays in the deferred money-flow
sub-project; this is just so totals are not silently wrong.

## Data flow (card purchase, happy path)
```
user /buy → pick plan → pick "Card"
  → record_pending Payment(currency=RUB, provider_id=cloudpayments, meta={kind,plan_id})
  → Cloudpayments orders/create (InvoiceId = payment.id) → pay URL
  → bot sends URL button
user pays on Cloudpayments page
  → Cloudpayments POSTs "Pay" notification → /payments/cloudpayments
  → look up Payment by InvoiceId → resolve secret by franchise_type → verify Content-HMAC
  → fulfill_payment(payment.id, external_id=TransactionId)  [idempotent: credits once]
  → enqueue delivery task → bot sends buy.payment_success
  → respond {"code": 0}
```

## Error handling
- `orders/create` fails (network / Cloudpayments error) → tell the user, mark the pending `Payment`
  `failed`.
- Invalid `Content-HMAC` or unknown `InvoiceId` → `{"code": 13}`, no crediting.
- Duplicate / redelivered notification → `fulfill_payment` returns `False`; respond `{"code": 0}`.
- No Cloudpayments provider configured for the tenant → the Card method is simply not offered.

## Testing
- **Unit:** `create_invoice` (mock httpx, asserts InvoiceId/Amount/Currency, parses pay URL);
  `verify_callback` HMAC valid/invalid; `resolve_provider_config` for both franchise types;
  `plan_prices` helpers; `encrypt_json`/`decrypt_json` round-trip.
- **Route:** webhook valid → fulfills + credits + enqueues notify; invalid HMAC → no credit
  (`code 13`); unknown invoice → no credit; duplicate → no double credit (`code 0`).
- **Bot:** `/buy` shows the method picker; card path records a pending payment + sends a URL button.
- **Owner FSM:** entering keys stores an encrypted `cloudpayments` provider row; secret message
  deleted.
- **Superadmin:** platform keys stored on the platform tenant.
- **Payout:** currency-scoped sum (XTR and RUB do not mix).

## Open considerations / risks
- **Async user notification** after the webhook (the Stars `successful_payment` path does not apply) —
  handled by the delivery-task pattern; verify the user's `chat_id` is available from the account.
- **Notification URL setup** is a manual step the owner/superadmin performs in their Cloudpayments
  dashboard; the FSM must show the exact URL.
- **Multi-currency reporting** beyond payouts (stats/analytics) may also assume a single currency —
  audit when the money-flow sub-project lands.

## Suggested implementation stages (for the future plan)
1. Crypto JSON helpers + `plan_prices` table + `Tenant.franchise_type` (+ migrations).
2. `CloudpaymentsProvider` + config resolution + registry wiring (pure unit-tested).
3. HTTP webhook route + fulfillment + async notify.
4. Bot `/buy` method picker + card URL flow + public API create-invoice.
5. Owner FSM + superadmin keys + i18n (10 langs).
6. Payout currency guard + stage-end full suite.
