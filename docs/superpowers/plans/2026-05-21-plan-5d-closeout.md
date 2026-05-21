# Plan 5d — Close-out (loose ends) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox (`- [ ]`) steps.

**Goal:** Close every documented loose end from Plans 5a/5b/5c: audit the invite routes, fix the superadmin-grant email response, re-authorize the transfer FSM at apply time, seed the platform tenant's default language, add per-account read lists (account detail + blueprints/requests/payments), add DB-backed LLM config admin (`/admin/platform/llm`), and wire the master bot (onboarding + owner console) to i18n.

**Architecture:** Mostly additive on existing modules. New `domain/llm_config.py` (platform_config-backed LLM settings with env fallback). Master-bot i18n reuses the 5a `Translator` already injected by `AccountMiddleware` for the platform tenant; new platform-string keys are seeded for master-bot text.

**Tech Stack:** FastAPI, SQLModel, the 5a i18n layer, aiogram 3, pytest. No new deps. No new migrations (uses existing tables: `platform_config`, `audit_log`, `account_balance`, `blueprints`, `requests`, `payments`, `platform_strings`, `tenant_languages`).

**Scope decisions (deliberate):**
- LLM **API key stays env-only** (`settings.llm_api_key`) — never stored in the DB. Only `provider/model/temperature/max_tokens` become platform_config-managed (spec §369-372). The GET endpoint reports the effective config with the key **redacted** (just "configured: true/false").
- **Materialized stats views are NOT built** (spec §639 defers them until load grows; real-time SQL is the MVP).

---

## Task 1: audit invite create/revoke

**Files:** Modify `src/quantuum/api/routes/admin_platform.py`; Test: extend `tests/test_api_admin_platform.py`.

The `POST /admin/platform/invites` and `POST /admin/platform/invites/{id}/revoke` routes mutate without audit. Add `record_audit(session, tenant_id=None, actor_account_id=admin.id, action="platform.invite.create"|"platform.invite.revoke", entity_type="tenant_invite", entity_id=invite.id, payload={...})` before the response. NOTE: `create_invite`/`revoke_invite` (domain/invites.py) currently commit internally — to keep the audit atomic, either (a) call `record_audit` then `session.commit()` after the domain call (the domain already committed the invite; the audit is a follow-up commit — acceptable), or (b) preferred: add the audit row and commit once. Simplest robust approach: after the domain call returns the invite, `await record_audit(...)` then `await session.commit()`. Verify no double-commit error.

- [ ] Step 1: extend the invite tests — after create/revoke, assert an `AuditLog` row exists with the right action + entity_id. Step 2-5: FAIL → implement → PASS + ruff → commit `feat(5d): audit invite create/revoke`.

## Task 2: superadmin-grant returns real email

**Files:** Modify `src/quantuum/api/routes/admin_platform.py` (the `POST /superadmins` handler); Test: extend `tests/test_api_platform_admin.py` or `test_api_admin_platform.py`.

The grant handler returns `SuperadminOut(account_id=..., email=None)`. Fix it to look up the account's `magic_link` `AccountIdentity` email (same logic as the list endpoint) and return it (None only if the account truly has no email identity).

- [ ] Step 1: test — grant superadmin on an account that HAS a magic_link identity → response `email` equals that email. Step 2-5: FAIL → implement → PASS + ruff → commit `feat(5d): superadmin grant returns account email`.

## Task 3: transfer FSM re-authorizes at apply time

**Files:** Modify `src/quantuum/bot/handlers/owner_console.py` (`on_transfer_target`); Test: extend `tests/test_owner_console_actions.py`.

`on_transfer_target` trusts `actor_id` stored in FSM state from `/transfer`. Re-authorize at apply time: inside the session, call `authorize_tenant_action(session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id, roles=("owner",))`; if it returns None → reply "Больше нет прав на передачу." + clear state + return (do NOT transfer). Use the freshly-resolved actor id as the audit actor.

- [ ] Step 1: test — start /transfer as owner, then (simulating role loss) revoke the owner role before sending the target → apply step denies + no transfer + state cleared. Keep the happy-path test green. Step 2-5: FAIL → implement → PASS + ruff → commit `feat(5d): re-authorize transfer at apply time`.

## Task 4: seed platform-tenant default language

**Files:** Modify `src/quantuum/db/bootstrap.py` (where `ensure_tenant_default_language` is called); Test: extend `tests/test_i18n_seed.py` or a bootstrap test.

In every startup path that calls `ensure_tenant_default_language(session, <default_tenant_id>)`, ALSO call it for the platform tenant: `ensure_tenant_default_language(session, platform_tenant_id, default_lang="ru")` (get the platform tenant via `ensure_platform_tenant(session)`). This makes the master bot's `resolve_lang` resolve a real default instead of falling back to `FALLBACK_LANG`.

- [ ] Step 1: test — after bootstrap, the platform tenant has exactly one default `tenant_languages` row. Step 2-5: FAIL → implement → PASS + ruff → commit `feat(5d): seed platform tenant default language`.

## Task 5: per-account read lists

**Files:** Modify `src/quantuum/api/routes/admin_tenants.py`; schemas; Test `tests/test_api_tenant_data_lists.py`.

All under `require_tenant_role(("owner","admin"))`, read-only (no audit):
- `GET /{tenant_id}/accounts/{account_id}` → account detail: id, created_at, last_seen_at, balance (package_credits, subscription_active_until), free_trial_used; 404 if not in tenant.
- `GET /{tenant_id}/blueprints?limit=50&offset=0` → `[BlueprintSummaryOut(id, account_id, status, created_at, completed_at)]` for the tenant, newest first.
- `GET /{tenant_id}/requests?limit=&offset=` → `[RequestSummaryOut(id, account_id, kind, status, created_at)]`.
- `GET /{tenant_id}/payments?limit=&offset=` → `[PaymentSummaryOut(id, account_id, amount_cents, currency, status, created_at, paid_at)]`.
Order each by `created_at DESC, id DESC`. Schemas: `AccountDetailOut`, `BlueprintSummaryOut`, `RequestSummaryOut`, `PaymentSummaryOut`.

- [ ] Step 1: tests — seed a tenant with accounts/blueprints/requests/payments (+ rows in another tenant to confirm scoping); assert each list returns only the tenant's rows, paginated, newest first; account detail 404 cross-tenant; customer 403. Step 2-5: FAIL → implement → PASS + ruff → commit `feat(5d): per-account/tenant read lists (accounts detail, blueprints, requests, payments)`.

## Task 6: LLM config admin (platform_config-backed)

**Files:** Create `src/quantuum/domain/llm_config.py`; Modify `src/quantuum/api/routes/admin_platform.py`, `src/quantuum/tasks/blueprint.py`; schemas; Test `tests/test_llm_config.py` + route test.

`domain/llm_config.py`:
```python
LLM_KEYS = ("provider", "model", "temperature", "max_tokens")

async def get_llm_config(session) -> dict:
    """Effective LLM config: platform_config 'llm.<key>' overrides, else settings defaults."""
    s = get_settings()
    defaults = {"provider": s.llm_provider, "model": s.llm_model,
                "temperature": s.llm_temperature, "max_tokens": s.llm_max_tokens}
    # read PlatformConfig rows with key in {"llm.provider", ...}; value_jsonb stored as {"value": X}
    # overlay onto defaults (coerce temperature->float, max_tokens->int)
    ...
    return {**defaults, **overrides}

async def set_llm_config(session, *, actor_id, **fields) -> dict:
    """Upsert platform_config 'llm.<key>' for provided fields (provider/model/temperature/max_tokens)."""
    ...
```
Store each as a `PlatformConfig(key=f"llm.{k}", value_jsonb={"value": v}, updated_by_account_id=actor_id)`.

Routes (superadmin):
- `GET /admin/platform/llm` → effective config + `api_key_configured: bool` (`bool(settings.llm_api_key)`), api_key itself NOT returned.
- `PUT /admin/platform/llm` `{provider?, model?, temperature?, max_tokens?}` → `set_llm_config`; audit `platform.llm.update`; return the effective config.

Blueprint task: replace the direct `settings.llm_model/temperature/max_tokens` reads with `cfg = await get_llm_config(session)` and use `cfg["model"]/cfg["temperature"]/cfg["max_tokens"]` and `cfg["provider"]` for the recorded `llm_provider`. The LLM client/key still comes from `ctx["llm_client"]` (env key) — unchanged. (Document: API key remains env-only.)

- [ ] Step 1: tests — `get_llm_config` returns settings defaults when no platform_config; after `set_llm_config(model="claude-x", temperature=0.5)` returns the overrides merged; GET route redacts the key + reports api_key_configured; PUT updates + audits; a blueprint-task test asserts the task uses the DB-config model (extend the existing task test with a platform_config override + assert recorded llm_model). Step 2-5: FAIL → implement → PASS + ruff → commit `feat(5d): platform LLM config admin (DB-backed, env key) + task uses it`.

## Task 7: master-bot i18n (onboarding + owner console)

**Files:** Modify `src/quantuum/i18n/seed_strings.py` (add master-bot keys), `src/quantuum/bot/handlers/master_onboarding.py`, `src/quantuum/bot/handlers/owner_console.py`; Test updates for those handlers.

The master bot runs in the platform tenant; `AccountMiddleware` already injects `i18n`/`lang` for it (and Task 4 ensures a platform default lang). Wire the master-bot user-facing strings off hardcoded RU onto `i18n`:
- Add `master.*` and `owner.*` keys to `BASE_STRINGS` (ru + en) covering every string in `master_onboarding.py` (onboarding prompts, cancel, confirm, errors, success) and `owner_console.py` (/tenants list lines, no-tenants, /manage menu + buttons, stats text, pause/resume replies, transfer prompts/errors/success, "нет прав"). Keep the exact current RU as the `ru` value.
- Convert the handlers to resolve via the injected `i18n` (declare `i18n` kwarg; for keyboards build labels via `await i18n(...)`). For callback handlers, `i18n` is injected the same way (the master dispatcher has AccountMiddleware on callback_query too).
- The onboarding deep-link `/start <code>` handler runs before account creation? It DOES go through AccountMiddleware (tenant_id is the platform tenant via TenantMiddleware), so `i18n` should be available; if any handler lacks `i18n` in data (e.g. the plain `/start`), fall back to the seeded RU via `i18n` with a default, or guard with `i18n` optional + RU default. Verify each handler receives `i18n`.

- [ ] Step 1: update master_onboarding + owner_console tests to pass an `i18n` Translator (use the conftest `build_translator(session, platform_tenant_id)` after seeding; ensure the platform tenant has a default lang) and assert the replies come from i18n (seeded ru text appears). Step 2: FAIL. Step 3: add keys + wire handlers. Step 4: PASS (re-run all owner_console + master_onboarding tests). Step 5: ruff + commit `feat(5d): wire master bot (onboarding + owner console) to i18n`.

Audit (after writing): grep `[А-Яа-яЁё]` in `master_onboarding.py` + `owner_console.py` → only non-user-facing comments should remain (no hardcoded user strings). Allow plain RU only where `i18n` is genuinely unavailable (document any such case).

---

## Stage completion
- Full suite `uv run pytest -q` + `uv run ruff check .` + `uv run alembic heads` (no new migration; head stays `a6b7c8d9e0f1`).
- Final holistic review of feat/plan-5d.

## Self-review checklist
- Invite + LLM mutations now audited; superadmin email returned. ✓
- Transfer re-authorized at apply. ✓
- Platform tenant has a default language. ✓
- Per-account read lists scoped + paginated, auth-guarded, no audit. ✓
- LLM API key stays env-only; config DB-managed with env fallback. ✓
- Master-bot strings i18n-wired (no hardcoded user-facing RU left). ✓
- Materialized views intentionally excluded (documented). ✓
