# Plan 5c — Self-Service Owner Commands (Master Bot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox (`- [ ]`) steps.

**Goal:** Let tenant owners manage their tenants from the master bot: `/tenants` (list), `/manage <slug>` (inline menu: stats / pause / resume / transfer), `/transfer <slug>` (ownership handoff). Authorization is by Telegram identity → `tenant_roles`. All mutations reuse the Plan 5b domain logic and write `audit_log` entries.

**Architecture:** A new `domain/owner_console.py` resolves a Telegram user's managed tenants and authorizes actions (tg identity → accounts → `tenant_roles`). A new master-bot router `bot/handlers/owner_console.py` adds the commands + an inline manage-menu (callbacks) + a transfer FSM, all calling the existing 5b domain helpers (`tenant_stats`, `set_tenant_status`, `transfer_ownership`, `record_audit`). The router is registered on the master dispatcher alongside onboarding.

**Tech Stack:** aiogram 3 (Router, FSM, CallbackData), the 5b domain layer, pytest. Master-bot owner strings stay plain Russian (consistent with the existing `master_onboarding.py`; full master-bot i18n is deferred). Spec ref: §8 "Self-service owner commands".

---

## Key facts (from the codebase)
- Telegram identity: `account_identities(provider="tg_chat", provider_user_id=str(tg_user_id))` links an Account to a Telegram user. A user has a separate Account per tenant but the same `provider_user_id`.
- Provisioning grants the owner an `owner` `tenant_role` in their new tenant, and `tenants.owner_tg_id = str(tg_id)` / `owner_chat_id`.
- Master dispatcher (`bot/master_app.py`) already runs `TenantMiddleware` + `AccountMiddleware` (handlers get `account`, `tenant_id`, `chat_id`, and a platform-tenant `i18n`/`lang`). The master bot operates in the PLATFORM tenant.
- 5b domain helpers (reuse): `quantuum.domain.tenants.set_tenant_status`, `transfer_ownership`, `list_roles`, `count_owners`; `quantuum.domain.stats.tenant_stats`; `quantuum.domain.audit.record_audit`. `Tenant(id, slug, display_name, status, tier, is_platform, primary_owner_account_id, owner_tg_id)`.
- Callbacks pattern: `bot/ui/callbacks.py` holds `CallbackData` classes (e.g. `OwnerOnboardCb`). aiogram callback handlers: `@router.callback_query(Cb.filter(...))`. Note (memory): for CallbackQuery the middleware sets `chat_id` from `query.message.chat.id`, not `event.chat`.

---

## File Structure
Created:
- `src/quantuum/domain/owner_console.py` — `managed_tenants(session, tg_user_id)`, `authorize_tenant_action(session, *, tg_user_id, tenant_id, roles)`, `resolve_managed_tenant_by_slug(session, *, tg_user_id, slug, roles)`
- `src/quantuum/bot/handlers/owner_console.py` — `/tenants`, `/manage`, `/transfer`, manage-menu callbacks, transfer FSM
- Tests per task

Modified:
- `src/quantuum/bot/ui/callbacks.py` — add `OwnerManageCb(action: str, tenant_id: int = 0)`
- `src/quantuum/bot/master_app.py` — register `owner_console.router`

---

## Task 1: owner_console domain (resolution + authorization)

**Files:** Create `src/quantuum/domain/owner_console.py`; Test `tests/test_owner_console_domain.py`.

```python
async def managed_tenants(session, tg_user_id: str, *, roles=("owner", "admin")) -> list[Tenant]:
    """Tenants where this Telegram user holds one of `roles` (via tg_chat identity → accounts → tenant_roles)."""
    # SELECT DISTINCT tenants.* FROM tenants
    #   JOIN tenant_roles tr ON tr.tenant_id = tenants.id AND tr.role IN roles
    #   JOIN account_identities ai ON ai.account_id = tr.account_id
    #   WHERE ai.provider = 'tg_chat' AND ai.provider_user_id = tg_user_id
    # order by tenants.id

async def account_id_for_role(session, *, tg_user_id, tenant_id, roles=("owner","admin")) -> int | None:
    """The account_id (in this tenant) the tg user holds one of `roles` with — used as the audit actor; None if not authorized."""

async def authorize_tenant_action(session, *, tg_user_id, tenant_id, roles=("owner","admin")) -> int | None:
    """Return the actor account_id if authorized, else None."""
    return await account_id_for_role(session, tg_user_id=tg_user_id, tenant_id=tenant_id, roles=roles)

async def resolve_managed_tenant_by_slug(session, *, tg_user_id, slug, roles=("owner","admin")) -> tuple[Tenant, int] | None:
    """Find the tenant by slug AND authorize; return (tenant, actor_account_id) or None."""
```
Use `str(tg_user_id)` consistently (provider_user_id is text).

- [ ] Step 1: failing test — seed: a tenant T with an owner account O (tenant_role owner) + an account_identity(tg_chat, "111") for O; a tenant U where "111" has role admin; a tenant V where "111" has NO role. `managed_tenants("111")` returns {T, U} (owner+admin) ordered; with roles=("owner",) returns {T} only. `authorize_tenant_action(tg_user_id="111", tenant_id=T.id)` returns O.id; for V returns None. `resolve_managed_tenant_by_slug(tg_user_id="111", slug=T.slug)` returns (T, O.id); unknown slug → None; V.slug (not managed) → None.
- [ ] Steps 2-5: FAIL → implement → PASS + ruff → commit `feat(5c): owner console domain (managed tenants + authorization)`.

---

## Task 2: `/tenants` command

**Files:** Create `src/quantuum/bot/handlers/owner_console.py` (router + this command); Test `tests/test_owner_console_tenants.py`.

`@router.message(Command("tenants"))` → `on_tenants(message, ...)`:
- `tg_user_id = str(message.from_user.id)`; open a session; `tenants = await managed_tenants(session, tg_user_id)`.
- If empty: "У тебя пока нет тенантов. Создай бота по ссылке-приглашению." 
- Else: a message listing each `f"• {t.display_name} (/{t.slug}) — {t.status}"` plus a hint "Управление: /manage <slug>".

- [ ] Step 1: failing test — drive `on_tenants` with a fake Message (from_user.id, `.answer` capturing). Seed managed tenants for the tg id; assert the reply lists their slugs; empty case shows the no-tenants message. (Match the fake-Message pattern from tests/test_bot_start_menu_profile.py / master onboarding tests.)
- [ ] Steps 2-5: FAIL → implement → PASS + ruff → commit `feat(5c): /tenants owner command`.

---

## Task 3: `/manage <slug>` inline menu

**Files:** Modify `bot/ui/callbacks.py` (add `OwnerManageCb`), `bot/handlers/owner_console.py`; Test `tests/test_owner_console_manage.py`.

`OwnerManageCb(CallbackData, prefix="omng")` with `action: str` and `tenant_id: int = 0`.

`@router.message(Command("manage"))` `on_manage(message, command: CommandObject)`:
- Parse slug from `command.args`. If missing → "Использование: /manage <slug>".
- `resolve_managed_tenant_by_slug(session, tg_user_id, slug)`; if None → "Тенант не найден или у тебя нет прав." 
- Else show an inline menu (InlineKeyboardBuilder) with buttons (callback_data = OwnerManageCb(action=..., tenant_id=t.id).pack()):
  - "📊 Статистика" action="stats"
  - "⏸ Пауза" action="pause" / "▶️ Возобновить" action="resume" (show pause if status active, resume if suspended)
  - "🔁 Передать владение" action="transfer" (owner-only — show always; the handler re-checks owner role)
  - title line: `f"Управление: {t.display_name} (/{t.slug}) — {t.status}"`.

- [ ] Step 1: failing test — `on_manage` with args="<slug>" for a managed tenant → reply has the title + an inline keyboard whose callback_datas decode to OwnerManageCb with the tenant_id; unmanaged slug → "нет прав"; missing args → usage. 
- [ ] Steps 2-5: FAIL → implement → PASS + ruff → commit `feat(5c): /manage owner menu`.

---

## Task 4: manage callbacks — stats + pause/resume

**Files:** Modify `bot/handlers/owner_console.py`; Test `tests/test_owner_console_actions.py`.

Handlers (all re-authorize via `authorize_tenant_action`; the callback's `tenant_id` comes from the CallbackData; the tg user from `query.from_user.id`):
- `@router.callback_query(OwnerManageCb.filter(F.action == "stats"))` → authorize (owner/admin); `s = await tenant_stats(session, tenant_id)`; answer a formatted summary (active customers, paid, dau/wau/mau, revenue_cents, mrr_cents, requests_by_kind). `query.answer()`.
- `action == "pause"` → authorize; if tenant.is_platform → deny; `set_tenant_status(session, tenant_id, "suspended", "paused")`; `record_audit(session, tenant_id=tenant_id, actor_account_id=<actor>, action="tenant.pause", ...)`; commit; answer "Поставлено на паузу." 
- `action == "resume"` → authorize; `set_tenant_status(..., "active", "active")`; audit "tenant.resume"; commit; answer "Возобновлено."
- Unauthorized (authorize returns None) → `query.answer("Нет прав", show_alert=True)`.

- [ ] Step 1: failing test — fake CallbackQuery (from_user.id, `.message.chat.id`, `.answer`, `.message.answer`). For a managed owner: stats action replies with numbers (seed minimal data); pause sets tenant.status suspended + writes an audit row + answers; resume restores. For a NON-managing tg id: pause action → not authorized (status unchanged, alert). 
- [ ] Steps 2-5: FAIL → implement → PASS + ruff → commit `feat(5c): manage callbacks (stats + pause/resume) + audit`.

---

## Task 5: `/transfer <slug>` flow (owner-only)

**Files:** Modify `bot/handlers/owner_console.py` (FSM); Test `tests/test_owner_console_transfer.py`.

A small FSM `OwnerTransfer(StatesGroup): awaiting_target = State()`.
- `@router.message(Command("transfer"))` `on_transfer_cmd(message, command, state)`: parse slug; `resolve_managed_tenant_by_slug(..., roles=("owner",))` (OWNER-only); if None → "нет прав / не найдено"; else set FSM state with `tenant_id`, prompt "Перешли Telegram ID нового владельца (число). Он должен уже иметь аккаунт в этом тенанте." 
- `@router.message(OwnerTransfer.awaiting_target)` `on_transfer_target(message, state)`: parse the entered value as the new owner's **tg_user_id** (digits). Resolve the new owner's Account IN THIS tenant via `account_identities(tg_chat, value)` joined to accounts where `account.tenant_id == tenant_id` (the new owner must already be a customer of the tenant). If not found → "У этого пользователя нет аккаунта в тенанте. Он должен сначала запустить твоего бота." (stay in state or cancel). Else `transfer_ownership(session, tenant_id=..., new_owner_account_id=..., actor_id=<current owner account>)`; `record_audit(... action="tenant.transfer" ...)`; commit; clear state; reply "Готово. Владение передано." Provide a cancel (/cancel or a message) path.

(Identifying the new owner by tg_user_id keeps it in the Telegram-native idiom; the new owner must already have an account in the tenant — matches spec §282 two-account model.)

- [ ] Step 1: failing test — owner runs /transfer <slug>, then sends the new owner's tg id; seed the new owner as a customer account in that tenant (account + tg_chat identity). Assert: tenant.primary_owner_account_id updated to the new owner's account, the new owner has an "owner" role, an audit row written. Negative cases: non-owner /transfer → denied; target tg id with no account in the tenant → error message + no transfer. 
- [ ] Steps 2-5: FAIL → implement → PASS + ruff → commit `feat(5c): /transfer ownership flow + audit`.

---

## Task 6: register router + stage completion

**Files:** Modify `src/quantuum/bot/master_app.py`; Test: extend a master-dispatcher test if present.

In `create_master_dispatcher`, `dp.include_router(owner_console.router)` AFTER `master_onboarding.router` (onboarding's `CommandStart` handlers take precedence; the new commands `/tenants`,`/manage`,`/transfer` don't conflict). Verify the dispatcher builds (import + include) without conflicts.

- [ ] Step 1: test that `create_master_dispatcher()` builds and includes the owner_console router (assert the command handlers are registered, e.g. by building the dispatcher and checking it has >1 router, or that a `/tenants` update would route — minimally assert no exception on build and router count). 
- [ ] Step 2-4: implement → run targeted test → then the FULL suite `uv run pytest -q` + `uv run ruff check .` (stage end). 5. Commit `feat(5c): register owner console router on master dispatcher`.

---

## Self-review checklist
- Every command/callback authorizes via `owner_console` (tg identity → tenant_roles); transfer is owner-only. ✓
- Mutations (pause/resume/transfer) write `audit_log` with the owner's in-tenant account as actor. ✓
- Reuses 5b domain logic (no duplicated tenant/stat logic). ✓
- Master-bot strings plain RU (consistent with onboarding; i18n deferred). ✓
- owner_console router registered after onboarding; no handler conflicts. ✓

## Deploy notes
- No migration (5c is behavior-only on existing tables).
- Owners interact via the master bot; ensure provisioning grants the `owner` role + records `owner_tg_id` (already does).
