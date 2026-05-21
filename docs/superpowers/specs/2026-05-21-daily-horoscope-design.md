# Daily Horoscope Push — Design Spec

**Date:** 2026-05-21
**Status:** Approved (design)
**Branch:** `feat/daily-horoscope`
**Wave:** Feature wave sub-project 3/3 (after Q&A and Transits).

## 1. Overview & goals

A **transit-aware daily horoscope** delivered as a short Telegram message at each user's
chosen local hour. It reuses the shipped `compute_transits` engine to ground a brief, warm
daily reading in the user's real natal chart and the current sky.

**Primary goal:** subscription stickiness — the subscription feels alive every morning.

It is a **subscriber perk**: only accounts with an active subscription can opt in, and
delivery is **free** (no quota/credits consumed, no refund logic).

## 2. Audience & billing

- **Eligible:** accounts whose `AccountBalance.subscription_active_until > now()` (the same
  "subscriber" signal `consume_quota` uses) **and** that have a `NatalProfile`.
- **Cost:** free. No `consume_quota`, no `Request` row, no refunds.
- **Opt-in:** off by default. The user explicitly enables daily push and picks an hour.
- Eligibility is enforced at two points: the dispatcher (selection) and the per-user task
  (re-check, because a subscription can lapse between dispatch and generation).

## 3. Data model (2 new tables)

### 3.1 `daily_subscriptions` — settings + idempotency (one row per account)

Mirrors `AccountBalance`'s "one row per account, account_id as PK" shape.

| column | type | notes |
| --- | --- | --- |
| `account_id` | int PK, FK accounts.id | one row per account |
| `tenant_id` | int FK tenants.id, index | for per-tenant bot delivery |
| `enabled` | bool, default `False` | opt-in flag |
| `send_hour` | int, default `9` | user's preferred LOCAL hour, 0–23 |
| `last_sent_on` | date \| None, default `None` | user's local date of last successful send (idempotency) |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

### 3.2 `daily_horoscopes` — history (one row per send)

Mirrors `transit_reports`/`qa_answers`.

| column | type | notes |
| --- | --- | --- |
| `id` | int PK | |
| `tenant_id` | int FK, index | |
| `account_id` | int FK, index | |
| `natal_profile_id` | int FK | |
| `local_date` | date | user's local date this horoscope is for |
| `transit_md` | str \| None | compact deterministic grounding |
| `horoscope_md` | str \| None | the short blurb (LLM output) |
| `lang` | str \| None | |
| `status` | str, default `"generating"` | generating\|done\|failed |
| `error` | str \| None | |
| `llm_provider` / `llm_model` / `llm_tokens_in` / `llm_tokens_out` | nullable | |
| `created_at` | timestamptz | |
| `completed_at` | timestamptz \| None | |

- **Unique `(account_id, local_date)`** — a hard once-per-day guard. `daily_generate` inserts
  this row FIRST (status `generating`); a concurrent/duplicate dispatch hits the unique
  violation and aborts cleanly (idempotent claim of the day's slot).
- Index `ix_daily_horoscopes_tenant_created` on `(tenant_id, created_at)` (same as siblings).

## 4. Astronomy reuse + short narration

- Reuse `compute_transits(inp, *, as_of=now, window_days=3)` — a small window: today's
  **active-now** aspects (the core of a daily reading) plus any **exacts within 3 days**.
  (`window_days=3` is below the engine's `MIN_WINDOW_DAYS=7`, so it clamps to 7 for the
  upcoming-exacts scan; that is acceptable — we render only active-now + the nearest 1–2
  imminent exacts. **Decision:** call with `window_days=7` explicitly and, in the renderer,
  show only exacts within 3 days. This keeps the engine contract clean.)
- New helper `astrology/transits.py::render_daily_md(report, *, ahead_days=3) -> str` — a
  **compact** grounding listing active aspects and imminent exacts (≤ `ahead_days`) only.
  Distinct from the 90-day 3-table `render_transits_md`. Used to ground the LLM.
- New `llm/daily_horoscope.py::daily_horoscope(client, natal_md, transit_md, *, lang, model,
  temperature, max_tokens)` + `llm/prompts/daily_astrologer.txt`. Prompt produces **2–5 warm,
  practical sentences**, same anti-hallucination rules as `transit_astrologer.txt`, low
  `max_tokens`. Mirrors `llm/transit_report.py`.

## 5. Scheduling, timezone & idempotency

- New hourly cron **`daily_dispatch(ctx)`**, added to `WorkerSettings.cron_jobs` next to the
  existing `cron(subscription_lifecycle, minute=0)`: `cron(daily_dispatch, minute=0)`.
- Each run:
  1. Load candidate rows: `daily_subscriptions` where `enabled` is true, joined to the
     account's `NatalProfile` (for `timezone`) and `AccountBalance` (subscription active).
  2. In Python, for each candidate compute `local_now = datetime.now(ZoneInfo(profile.timezone))`.
     Select when `local_now.hour == send_hour` **and** `last_sent_on is None or last_sent_on <
     local_now.date()`.
  3. For each selected account, **enqueue `daily_generate(account_id)`**.
- DST is handled automatically by `ZoneInfo`. Hour-only granularity (cron is hourly).
- **`daily_generate(account_id)`** (per-user task; mirrors `transit_generate` structure):
  1. Re-check eligibility: subscription still active, profile exists, `enabled` still true. If
     not → return silently (no send).
  2. Compute `local_date` from the profile timezone. **Insert** a `daily_horoscopes` row
     `(account_id, local_date, status="generating")`. On unique violation → already handled
     today → return.
  3. `resolve_natal(session, account_id, natal_profile_id)` (reuse from `domain/transits.py`)
     → `(BlueprintInput, natal_md, blueprint_id?)`. (blueprint_id is not stored on daily rows;
     `resolve_natal`'s natal_md is the grounding.)
  4. `compute_transits(inp, as_of=now, window_days=7)` → `render_daily_md(report, ahead_days=3)`
     → `transit_md`.
  5. LLM: `lang = account.preferred_lang or "ru"`; `get_llm_config(session)` →
     `daily_horoscope(...)`. On `llm_client is None` or LLM error → mark row `failed`, log.
  6. On success: update row `status="done"`, store `horoscope_md` + llm metadata.
  7. **Set `daily_subscriptions.last_sent_on = local_date`** (also on failure — see §9).
  8. Deliver via the **tenant's bot** (built like `subscription_lifecycle` via the botpool /
     `build_bots_by_tenant`, NOT the single `ctx["bot"]`), recovering `chat_id` from
     `AccountIdentity(provider="tg_chat")`. Delivery is best-effort.

## 6. Surfaces

### 6.1 Bot
- `/daily` command + a **"🔔 Ежедневный гороскоп"** main-menu button → both call a shared
  `run_daily_settings(message, account, i18n)` that shows current status (on/off + hour) with
  an inline keyboard:
  - toggle **On/Off** (`DailyCb(action="toggle")`),
  - **pick hour** (`DailyCb(action="hour", value=H)`) — a compact hour grid.
- Guards: non-subscriber → upsell message + buy button (no enable). No `NatalProfile` →
  prompt to fill it (`/profile`).
- New callback factory `DailyCb` in `bot/ui/callbacks.py`; handler `bot/handlers/daily.py`.

### 6.2 API (mirrors qa/transit routes in `api/routes/me.py`)
- `GET /v1/me/daily` → `DailySettingsOut {enabled, send_hour, last_sent_on}`.
- `PUT /v1/me/daily` ← `DailySettingsIn {enabled: bool, send_hour: int}` → 403 if enabling
  while not a subscriber; 422 if `send_hour` out of 0–23; upserts and returns settings.
- `GET /v1/me/daily/horoscopes` → `list[DailyHoroscopeOut]` newest-first.

## 7. i18n keys (ru + en) in `i18n/seed_strings.py`
- `btn.daily` = "🔔 Ежедневный гороскоп" / "🔔 Daily horoscope"
- `daily.status` (shows on/off + hour), `daily.enabled`, `daily.disabled`, `daily.hour_set`
- `daily.not_subscriber` (upsell), `daily.no_profile`
- `daily.header` = "🌟 Гороскоп на сегодня" / "🌟 Today's horoscope" (prefix for the delivered blurb)

## 8. Error handling

- Per-user generation isolated in its own task — one failure cannot stall others.
- `llm_client is None` or LLM exception → row `status="failed"`, logged. **No refunds** (free).
- **Failed generation still sets `last_sent_on`** (skips the day) to avoid hourly retry spam.
  (Decision locked; revisit if delivery reliability becomes an issue.)
- Delivery (send_message) best-effort and outside the DB transaction; a post-store send
  failure is logged, not retried.
- The unique `(account_id, local_date)` + `last_sent_on` together make double-sends impossible
  even if the cron double-fires.

## 9. Testing

- **Engine:** `render_daily_md` (active + imminent only; ahead_days filter; empty case).
- **Domain (`domain/daily.py`):** upsert settings, get, list_horoscopes, `due_candidates`
  query, `mark_sent`/`last_sent_on` update, claim-row-on-unique behavior.
- **LLM:** `daily_horoscope` wraps natal + transit grounding + lang line (mirror transit LLM test).
- **Task `daily_generate`:** happy (row done + last_sent_on set + bot send), not-subscriber
  skip, no-profile skip, already-sent-today skip (unique guard), llm-failure (row failed +
  last_sent_on set, no crash).
- **Dispatcher `daily_dispatch`:** selection by local hour + tz + last_sent_on, using a
  synthetic/frozen clock and ZoneInfo; enqueues exactly the due accounts; non-subscribers and
  disabled excluded.
- **API:** GET/PUT settings, 403 enabling as non-subscriber, 422 bad hour, history list.
- **Bot:** toggle on/off, set hour, non-subscriber upsell, no-profile prompt.
- **UI keyboards:** main menu grows to 7 buttons incl "🔔 Ежедневный гороскоп" (update existing
  keyboard + start/help menu assertions).
- **Migration:** single head; offline `--sql` ok.

## 10. Migration

- New revision `d9e0f1a2b3c4_daily_tables.py`, `down_revision = "c8d9e0f1a2b3"` (transit_reports
  head). Creates `daily_subscriptions` + `daily_horoscopes` with the columns/indexes/unique
  constraint above. Single head after.

## 11. File structure (anticipated)

- Create `src/quantuum/domain/daily.py` (settings CRUD + due_candidates + horoscope CRUD/claim).
- Create `src/quantuum/llm/daily_horoscope.py` + `src/quantuum/llm/prompts/daily_astrologer.txt`.
- Create `src/quantuum/tasks/daily.py` (`daily_dispatch` cron + `daily_generate` task).
- Create `src/quantuum/bot/handlers/daily.py`.
- Create `alembic/versions/d9e0f1a2b3c4_daily_tables.py`.
- Modify `src/quantuum/astrology/transits.py` (add `render_daily_md`).
- Modify `src/quantuum/db/models.py` (`DailySubscription`, `DailyHoroscope`).
- Modify `src/quantuum/tasks/worker.py` (register `daily_generate`; add `daily_dispatch` cron).
- Modify `src/quantuum/api/schemas.py` + `src/quantuum/api/routes/me.py`.
- Modify `src/quantuum/bot/ui/callbacks.py` (`DailyCb`), `bot/ui/text.py`, `bot/ui/keyboards.py`,
  `bot/handlers/menu.py`, `bot/app.py`, `i18n/seed_strings.py`.

## 12. Out of scope (YAGNI)

Multiple sends/day, weekly digests, web push, per-aspect notification preferences, snooze,
admin broadcast, minute-level scheduling. No new delivery transport — reuses per-tenant bots.

## 13. Decisions locked

- Subscriber-only, free (no quota).
- Per-user configurable LOCAL hour (from `NatalProfile.timezone`); default hour 9.
- Short blurb (2–5 sentences), today-focused (active-now + exacts ≤ 3 days).
- Settings table + horoscope history table; unique `(account_id, local_date)` idempotency.
- Bot (`/daily` + menu) **and** API surfaces.
- Dispatcher cron + per-user `daily_generate` task (fault-isolated, parallel).
- Failed generation skips the day (sets `last_sent_on`).
- Delivery via the tenant's bot (botpool), not the single worker `ctx["bot"]`.
