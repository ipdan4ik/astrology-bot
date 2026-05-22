# Tenant-bot deletion (owner self-service) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a bot owner/admin delete their own tenant bot — from the master-bot owner console (Telegram) and the HTTP Admin API — as a soft delete that frees the slug and Telegram-bot id for clean re-creation.

**Architecture:** A new `archive_tenant()` domain function sets `Tenant.status="archived"` and *tombstones* the unique fields (`slug` → `{slug}__del{id}`, every bot's `bot_telegram_id` → `NULL`, bot `status="archived"`). Both surfaces call it behind a confirmation guard (type-the-slug / `confirm_slug`) and record a `tenant.delete` audit entry. `managed_tenants` is filtered to hide archived tenants. The bot is torn down by the existing reconciler (which only loads `status=="active"` bots) — the same mechanism pause uses.

**Tech Stack:** Python 3.12, aiogram 3 (Router, CallbackData, FSM StatesGroup, F filters), FastAPI, SQLModel/asyncpg, pytest + pytest-asyncio (auto mode).

**Conventions for every task:**
- Tests need the test PG/redis up at `172.30.0.2` / `172.30.0.3` (docker test stack).
- Run only the task's targeted tests during the task; run the full suite once at the end (Task 6).
- Run tests with `uv run pytest …`.
- New i18n keys auto-seed (insert-only) — no live `UPDATE` / `invalidate_i18n_all()` needed.
- Mirror the existing **pause** patterns (owner console `on_manage_pause`, HTTP `pause_tenant`) for structure, audit, and platform guards.

---

### Task 1: Add the `owner.delete.*` i18n keys

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py` (add keys to `BASE_STRINGS`)
- Test: `tests/test_i18n_seed.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_i18n_seed.py`:

```python
def test_owner_delete_strings_present():
    from quantuum.i18n.seed_strings import BASE_STRINGS

    for key in [
        "owner.manage.kb.delete",
        "owner.delete.prompt",
        "owner.delete.mismatch",
        "owner.delete.done",
        "owner.delete.cancelled",
        "owner.delete.platform_blocked",
    ]:
        assert key in BASE_STRINGS, f"missing {key}"
        assert "ru" in BASE_STRINGS[key] and "en" in BASE_STRINGS[key], f"{key} missing ru/en"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_i18n_seed.py::test_owner_delete_strings_present -v`
Expected: FAIL with `AssertionError: missing owner.manage.kb.delete`

- [ ] **Step 3: Add the keys**

In `src/quantuum/i18n/seed_strings.py`, insert this block right after the existing `owner.resume.done` entry (around line 650, with the other owner-console strings):

```python
    # Owner console — delete (SP2)
    "owner.manage.kb.delete": {
        "ru": "🗑 Удалить",
        "en": "🗑 Delete",
    },
    "owner.delete.prompt": {
        "ru": (
            "⚠️ Это навсегда удалит бота и скроет тенант. "
            "Чтобы подтвердить, отправь слаг: {slug}\n(или /cancel)"
        ),
        "en": (
            "⚠️ This permanently deletes the bot and hides the tenant. "
            "To confirm, send the slug: {slug}\n(or /cancel)"
        ),
    },
    "owner.delete.mismatch": {
        "ru": "Слаг не совпадает. Отправь {slug} ещё раз или /cancel.",
        "en": "Slug doesn't match. Send {slug} again or /cancel.",
    },
    "owner.delete.done": {
        "ru": "🗑 Бот удалён.",
        "en": "🗑 Bot deleted.",
    },
    "owner.delete.cancelled": {
        "ru": "Отменено.",
        "en": "Cancelled.",
    },
    "owner.delete.platform_blocked": {
        "ru": "Нельзя удалить платформенный тенант",
        "en": "The platform tenant cannot be deleted",
    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_i18n_seed.py::test_owner_delete_strings_present -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/i18n/seed_strings.py tests/test_i18n_seed.py
git commit -m "feat(delete): seed owner.delete.* i18n strings"
```

---

### Task 2: Domain `archive_tenant` (soft delete + tombstone)

**Files:**
- Modify: `src/quantuum/domain/tenants.py` (add `archive_tenant`)
- Test: `tests/test_tenants_archive.py` (new)

`src/quantuum/domain/tenants.py` already imports `from sqlmodel import select` and `from quantuum.db.models import Tenant, TenantBot, TenantRole` — no new imports needed.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tenants_archive.py`:

```python
from quantuum.db.models import Tenant, TenantBot


async def _make_tenant_with_bot(session, *, slug, bot_tg_id):
    tenant = Tenant(slug=slug, display_name=slug.title())
    session.add(tenant)
    await session.flush()
    bot = TenantBot(
        tenant_id=tenant.id,
        bot_telegram_id=bot_tg_id,
        bot_username=f"{slug}bot",
        bot_token_enc=b"x",
        webhook_secret_path=f"wh-{slug}",
        status="active",
    )
    session.add(bot)
    await session.commit()
    await session.refresh(tenant)
    await session.refresh(bot)
    return tenant, bot


async def test_archive_tenant_tombstones(session):
    from quantuum.domain.tenants import archive_tenant

    tenant, bot = await _make_tenant_with_bot(session, slug="acme", bot_tg_id=12345)
    tid = tenant.id

    result = await archive_tenant(session, tid)
    await session.commit()

    await session.refresh(tenant)
    await session.refresh(bot)
    assert result is not None
    assert tenant.status == "archived"
    assert tenant.slug == f"acme__del{tid}"
    assert bot.bot_telegram_id is None
    assert bot.status == "archived"


async def test_archive_tenant_idempotent(session):
    from quantuum.domain.tenants import archive_tenant

    tenant, _bot = await _make_tenant_with_bot(session, slug="beta", bot_tg_id=222)
    tid = tenant.id

    await archive_tenant(session, tid)
    await session.commit()
    await session.refresh(tenant)
    first_slug = tenant.slug

    # Second call must not re-tombstone the (already tombstoned) slug.
    await archive_tenant(session, tid)
    await session.commit()
    await session.refresh(tenant)
    assert tenant.slug == first_slug


async def test_archive_tenant_missing_returns_none(session):
    from quantuum.domain.tenants import archive_tenant

    assert await archive_tenant(session, 999999) is None


async def test_archive_frees_slug_and_bot_for_recreation(session):
    """The core re-creation guarantee: after archiving, the same slug AND the same
    bot_telegram_id can be reused by a fresh tenant with no unique violation."""
    from quantuum.domain.tenants import archive_tenant

    _tenant, _bot = await _make_tenant_with_bot(session, slug="gamma", bot_tg_id=777)
    await archive_tenant(session, _tenant.id)
    await session.commit()

    # Re-create with the SAME slug and SAME bot_telegram_id — must not raise.
    new_tenant, new_bot = await _make_tenant_with_bot(session, slug="gamma", bot_tg_id=777)
    assert new_tenant.id != _tenant.id
    assert new_bot.bot_telegram_id == 777
    assert new_tenant.slug == "gamma"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tenants_archive.py -v`
Expected: FAIL with `ImportError: cannot import name 'archive_tenant'`

- [ ] **Step 3: Implement `archive_tenant`**

In `src/quantuum/domain/tenants.py`, add this function right after `set_tenant_status` (around line 25):

```python
async def archive_tenant(session, tenant_id: int) -> Tenant | None:
    """Soft-delete a tenant: archive it and tombstone its unique fields.

    Renames the slug (``{slug}__del{id}``) and nulls every bot's
    ``bot_telegram_id`` so the same slug and Telegram bot can be re-onboarded
    later without unique-constraint collisions. Idempotent: a no-op if the tenant
    is already archived. Returns the tenant, or None if not found. The caller
    records audit + commits (mirrors ``set_tenant_status`` usage).
    """
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        return None
    if tenant.status == "archived":
        return tenant
    tenant.status = "archived"
    tenant.slug = f"{tenant.slug}__del{tenant_id}"
    session.add(tenant)

    result = await session.execute(
        select(TenantBot).where(TenantBot.tenant_id == tenant_id)
    )
    for bot in result.scalars().all():
        bot.bot_telegram_id = None
        bot.status = "archived"
        session.add(bot)

    await session.flush()
    return tenant
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tenants_archive.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/tenants.py tests/test_tenants_archive.py
git commit -m "feat(delete): archive_tenant domain fn (soft delete + tombstone)"
```

---

### Task 3: Exclude archived tenants from `managed_tenants`

**Files:**
- Modify: `src/quantuum/domain/owner_console.py` (`managed_tenants` query)
- Test: `tests/test_owner_console_domain.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_owner_console_domain.py`:

```python
async def test_managed_tenants_excludes_archived(session):
    from quantuum.db.models import Account, AccountIdentity, Tenant
    from quantuum.domain.owner_console import managed_tenants
    from quantuum.domain.tenants import grant_role

    tg = "70700"
    # Two tenants owned by the same tg user: one active, one archived.
    active = Tenant(slug="keep", display_name="Keep", status="active")
    archived = Tenant(slug="gone__del1", display_name="Gone", status="archived")
    session.add(active)
    session.add(archived)
    await session.commit()
    await session.refresh(active)
    await session.refresh(archived)
    for t in (active, archived):
        acc = Account(tenant_id=t.id)
        session.add(acc)
        await session.commit()
        await session.refresh(acc)
        session.add(
            AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=tg)
        )
        await session.commit()
        await grant_role(session, tenant_id=t.id, account_id=acc.id, role="owner")

    rows = await managed_tenants(session, tg)
    slugs = {t.slug for t in rows}
    assert "keep" in slugs
    assert "gone__del1" not in slugs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_owner_console_domain.py::test_managed_tenants_excludes_archived -v`
Expected: FAIL (archived tenant currently returned).

- [ ] **Step 3: Add the status filter**

In `src/quantuum/domain/owner_console.py`, update the `managed_tenants` query's `.where(...)` clause to also exclude archived tenants:

```python
        .where(
            TenantRole.role.in_(roles),
            AccountIdentity.provider == "tg_chat",
            AccountIdentity.provider_user_id == str(tg_user_id),
            Tenant.status != "archived",
        )
```

(`Tenant` is already imported in this module.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_owner_console_domain.py::test_managed_tenants_excludes_archived -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/owner_console.py tests/test_owner_console_domain.py
git commit -m "feat(delete): hide archived tenants from managed_tenants"
```

---

### Task 4: Owner-console Delete button + type-the-slug FSM

**Files:**
- Modify: `src/quantuum/bot/ui/callbacks.py` (`OwnerManageCb` action comment)
- Modify: `src/quantuum/bot/handlers/owner_console.py` (Delete button + FSM flow)
- Test: `tests/test_owner_console_handlers.py` (button rendering)
- Test: `tests/test_owner_console_actions.py` (delete flow)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_owner_console_handlers.py` (uses that file's existing `FakeMessage`, `_patch_sessionmaker`, `_inline`, `_make_tenant`, `_seed_account_with_role`, `build_translator`):

```python
async def test_manage_shows_delete_button(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t = await _make_tenant(session, "epsilon", "Epsilon", status="active")
    await _seed_account_with_role(session, tenant=t, role="owner")
    i18n = await build_translator(session, t.id)

    msg = FakeMessage()
    await oc.on_manage(msg, SimpleNamespace(args="epsilon"), i18n=i18n)

    _, markup = msg.answers[0]
    actions = {OwnerManageCb.unpack(b.callback_data).action for b in _inline(markup)}
    assert "delete" in actions
```

Append to `tests/test_owner_console_actions.py` (uses that file's existing `FakeMessage`, `FakeCallbackQuery`, `FakeState`, `_patch_sessionmaker`, `_seed_owner_tenant`, `_make_tenant`, `_seed_bot`, `_seed_account`, `_audit_rows`, `build_translator`, `OWNER_TG`, `CUSTOMER_TG`):

```python
async def test_delete_flow_success(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t, bot, _owner, _cust = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)
    state = FakeState()

    # step 1: tap Delete → prompt, state set
    q = FakeCallbackQuery(from_user_id=OWNER_TG)
    await oc.on_manage_delete(q, OwnerManageCb(action="delete", tenant_id=t.id), state, i18n=i18n)
    assert state.state == oc.OwnerDelete.awaiting_confirm
    assert (await state.get_data())["slug"] == t.slug

    # step 2: type the slug → archived + audit + done
    msg = FakeMessage(from_user_id=OWNER_TG, text=t.slug)
    await oc.on_delete_confirm(msg, state, i18n=i18n)

    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "archived"
    assert t.slug.endswith(f"__del{t.id}")
    assert bot.status == "archived"
    assert len(await _audit_rows(session, t.id, "tenant.delete")) == 1
    assert state.state is None


async def test_delete_slug_mismatch_keeps_tenant(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t, _bot, _owner, _cust = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)
    state = FakeState()

    q = FakeCallbackQuery(from_user_id=OWNER_TG)
    await oc.on_manage_delete(q, OwnerManageCb(action="delete", tenant_id=t.id), state, i18n=i18n)

    msg = FakeMessage(from_user_id=OWNER_TG, text="WRONG")
    await oc.on_delete_confirm(msg, state, i18n=i18n)

    await session.refresh(t)
    assert t.status == "active"  # unchanged
    assert await _audit_rows(session, t.id, "tenant.delete") == []
    assert state.state == oc.OwnerDelete.awaiting_confirm  # stays to retry


async def test_delete_cancel(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc

    _patch_sessionmaker(monkeypatch, oc, session)
    i18n = await build_translator(session, default_tenant.id)
    state = FakeState({"tenant_id": 1, "slug": "x"})
    state.state = oc.OwnerDelete.awaiting_confirm

    msg = FakeMessage(from_user_id=OWNER_TG)
    await oc.on_delete_cancel(msg, state, i18n=i18n)

    assert state.state is None
    assert await state.get_data() == {}
    assert "Отменено" in msg.answers[0][0]


async def test_delete_platform_blocked(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t = await _make_tenant(session, "platform", "Platform", is_platform=True)
    await _seed_bot(session, t.id)
    await _seed_account(session, tenant=t, tg=OWNER_TG, role="owner")
    i18n = await build_translator(session, t.id)
    state = FakeState()

    q = FakeCallbackQuery(from_user_id=OWNER_TG)
    await oc.on_manage_delete(q, OwnerManageCb(action="delete", tenant_id=t.id), state, i18n=i18n)

    await session.refresh(t)
    assert t.status == "active"  # unchanged
    assert state.state is None  # FSM not entered
    assert q.answers and q.answers[-1][1].get("show_alert") is True


async def test_delete_by_non_owner_denied(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t, _bot, _owner, _cust = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)
    state = FakeState()

    q = FakeCallbackQuery(from_user_id=CUSTOMER_TG)
    await oc.on_manage_delete(q, OwnerManageCb(action="delete", tenant_id=t.id), state, i18n=i18n)

    assert state.state is None  # FSM not entered
    assert q.answers and q.answers[-1][0] == "Нет прав"
    assert q.answers[-1][1].get("show_alert") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_owner_console_handlers.py::test_manage_shows_delete_button tests/test_owner_console_actions.py -k delete -v`
Expected: FAIL (`on_manage` has no delete button; `owner_console` has no `OwnerDelete` / `on_manage_delete` / `on_delete_confirm` / `on_delete_cancel`).

- [ ] **Step 3a: Extend the `OwnerManageCb` action comment**

In `src/quantuum/bot/ui/callbacks.py`, update the comment on `OwnerManageCb.action` to include `delete`:

```python
class OwnerManageCb(CallbackData, prefix="omng"):
    action: str  # stats | pause | resume | transfer | delete
    tenant_id: int = 0
```

- [ ] **Step 3b: Add the Delete button to `on_manage`**

In `src/quantuum/bot/handlers/owner_console.py`, inside `on_manage`, add a Delete button row after the existing transfer-button row (just before `await message.answer(...)`):

```python
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.manage.kb.delete"),
            callback_data=OwnerManageCb(action="delete", tenant_id=tenant.id).pack(),
        )
    )
```

- [ ] **Step 3c: Import `archive_tenant`**

In `src/quantuum/bot/handlers/owner_console.py`, extend the existing domain.tenants import:

```python
from quantuum.domain.tenants import archive_tenant, set_tenant_status, transfer_ownership
```

- [ ] **Step 3d: Add the delete FSM + handlers**

In `src/quantuum/bot/handlers/owner_console.py`, append at the end of the file (the `OwnerDelete` state group + its three handlers; note the `/cancel` handler is registered **before** the catch-all confirm handler so it matches first):

```python
# ── SP2: /manage → 🗑 Delete (type-the-slug confirm) ────────────────────────────


class OwnerDelete(StatesGroup):
    awaiting_confirm = State()


@router.callback_query(OwnerManageCb.filter(F.action == "delete"))
async def on_manage_delete(
    query: CallbackQuery, callback_data: OwnerManageCb, state: FSMContext, i18n: Translator
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        tenant = await session.get(Tenant, callback_data.tenant_id)
        if tenant is not None and tenant.is_platform:
            await query.answer(await i18n("owner.delete.platform_blocked"), show_alert=True)
            return
        slug = tenant.slug if tenant is not None else ""
    await state.set_state(OwnerDelete.awaiting_confirm)
    await state.update_data(tenant_id=callback_data.tenant_id, slug=slug)
    await query.message.answer(await i18n("owner.delete.prompt", slug=slug))
    await query.answer()


@router.message(Command("cancel"), OwnerDelete.awaiting_confirm)
async def on_delete_cancel(message: Message, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await message.answer(await i18n("owner.delete.cancelled"))


@router.message(OwnerDelete.awaiting_confirm)
async def on_delete_confirm(message: Message, state: FSMContext, i18n: Translator) -> None:
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    expected_slug = data["slug"]
    if (message.text or "").strip() != expected_slug:
        await message.answer(await i18n("owner.delete.mismatch", slug=expected_slug))
        return  # stay in state to retry
    async with get_sessionmaker()() as session:
        # Re-authorize at apply time (the role may have changed since the tap).
        actor = await authorize_tenant_action(
            session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await message.answer(await i18n("owner.no_rights"))
            await state.clear()
            return
        await archive_tenant(session, tenant_id)
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_account_id=actor,
            action="tenant.delete",
            entity_type="tenant",
            entity_id=tenant_id,
        )
        await session.commit()
    await state.clear()
    await message.answer(await i18n("owner.delete.done"))
```

All names used here (`F`, `Router`, `Command`, `FSMContext`, `State`, `StatesGroup`, `CallbackQuery`, `Message`, `InlineKeyboardButton`, `OwnerManageCb`, `Tenant`, `get_sessionmaker`, `record_audit`, `authorize_tenant_action`, `Translator`, `router`) are already imported at the top of `owner_console.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_owner_console_handlers.py::test_manage_shows_delete_button tests/test_owner_console_actions.py -v`
Expected: PASS (all, including the existing pause/resume/transfer tests still green).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/ui/callbacks.py src/quantuum/bot/handlers/owner_console.py tests/test_owner_console_handlers.py tests/test_owner_console_actions.py
git commit -m "feat(delete): owner-console 🗑 Delete with type-the-slug confirm"
```

---

### Task 5: HTTP `POST /admin/tenants/{id}/delete`

**Files:**
- Modify: `src/quantuum/api/schemas.py` (add `TenantDeleteIn`)
- Modify: `src/quantuum/api/routes/admin_tenants.py` (add the route + import)
- Test: `tests/test_api_admin_tenants.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_admin_tenants.py` (uses that file's existing `client`, `sa_headers`, `owner_headers`, `customer_headers`, `_make_tenant_with_bot`, `_make_role_headers`, `Tenant`, `TenantBot`, `AuditLog`, `select`, `session`, `default_tenant` fixtures):

```python
# ---------------------------------------------------------------------------
# POST /{tenant_id}/delete  (SP2)
# ---------------------------------------------------------------------------


async def test_delete_archives_and_tombstones(client, sa_headers, session):
    tenant, bot = await _make_tenant_with_bot(session)
    bot.bot_telegram_id = 998877
    session.add(bot)
    await session.commit()
    tid, slug = tenant.id, tenant.slug

    r = await client.post(
        f"/admin/tenants/{tid}/delete",
        json={"confirm_slug": slug},
        headers=sa_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "archived"

    await session.refresh(tenant)
    await session.refresh(bot)
    assert tenant.status == "archived"
    assert tenant.slug == f"{slug}__del{tid}"
    assert bot.bot_telegram_id is None
    assert bot.status == "archived"


async def test_delete_creates_audit_log(client, sa_headers, session):
    tenant, _bot = await _make_tenant_with_bot(session)
    await client.post(
        f"/admin/tenants/{tenant.id}/delete",
        json={"confirm_slug": tenant.slug},
        headers=sa_headers,
    )
    result = await session.execute(
        select(AuditLog).where(
            AuditLog.action == "tenant.delete", AuditLog.tenant_id == tenant.id
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_delete_slug_mismatch_400(client, sa_headers, session):
    tenant, _bot = await _make_tenant_with_bot(session)
    r = await client.post(
        f"/admin/tenants/{tenant.id}/delete",
        json={"confirm_slug": "nope"},
        headers=sa_headers,
    )
    assert r.status_code == 400
    await session.refresh(tenant)
    assert tenant.status == "active"  # unchanged


async def test_delete_platform_tenant_400(client, sa_headers, session):
    platform = Tenant(slug="platform-del", display_name="Platform", is_platform=True)
    session.add(platform)
    await session.commit()
    await session.refresh(platform)

    r = await client.post(
        f"/admin/tenants/{platform.id}/delete",
        json={"confirm_slug": "platform-del"},
        headers=sa_headers,
    )
    assert r.status_code == 400


async def test_delete_by_owner_200(client, session, default_tenant):
    headers = await _make_role_headers(session, default_tenant.id, "owner")
    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/delete",
        json={"confirm_slug": default_tenant.slug},
        headers=headers,
    )
    assert r.status_code == 200


async def test_delete_by_customer_403(client, customer_headers, default_tenant):
    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/delete",
        json={"confirm_slug": default_tenant.slug},
        headers=customer_headers,
    )
    assert r.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_admin_tenants.py -k delete -v`
Expected: FAIL (route returns 404/405; `TenantDeleteIn` missing).

- [ ] **Step 3a: Add the `TenantDeleteIn` schema**

In `src/quantuum/api/schemas.py`, add right after `TransferIn` (around line 301):

```python
class TenantDeleteIn(BaseModel):
    confirm_slug: str
```

- [ ] **Step 3b: Import the schema + `archive_tenant` in the route module**

In `src/quantuum/api/routes/admin_tenants.py`:
- add `TenantDeleteIn` to the `from quantuum.api.schemas import (...)` block (keep alphabetical-ish placement near `TenantDetailOut`);
- add `archive_tenant` to the `from quantuum.domain.tenants import (...)` block.

- [ ] **Step 3c: Add the delete route**

In `src/quantuum/api/routes/admin_tenants.py`, add right after the `resume_tenant` function (around line 230), mirroring `pause_tenant`:

```python
# ---------------------------------------------------------------------------
# POST /{tenant_id}/delete  (soft delete + tombstone; SP2)
# ---------------------------------------------------------------------------


@router.post("/{tenant_id}/delete", response_model=TenantDetailOut)
async def delete_tenant(
    tenant_id: int,
    body: TenantDeleteIn,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> TenantDetailOut:
    tenant, bot = await _load_tenant_and_bot(session, tenant_id)

    if tenant.is_platform:
        raise HTTPException(status_code=400, detail="cannot delete the platform tenant")

    if body.confirm_slug != tenant.slug:
        raise HTTPException(status_code=400, detail="confirm_slug does not match")

    await archive_tenant(session, tenant_id)

    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="tenant.delete",
        entity_type="tenant",
        entity_id=tenant_id,
        payload={},
    )

    await session.commit()
    await session.refresh(tenant)
    if bot is not None:
        await session.refresh(bot)
    return _tenant_detail_out(tenant, bot)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_admin_tenants.py -k delete -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/api/schemas.py src/quantuum/api/routes/admin_tenants.py tests/test_api_admin_tenants.py
git commit -m "feat(delete): POST /admin/tenants/{id}/delete (confirm_slug)"
```

---

### Task 6: Full suite + lint

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS (all tests). Investigate and fix any failure before proceeding.

- [ ] **Step 2: Lint**

Run: `uv run ruff check src/ tests/`
Expected: clean. Fix any issues (e.g. an unused import).

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: lint after tenant-bot delete"
```

(Skip if there is nothing to commit.)

---

## Self-Review

**1. Spec coverage:**
- Soft delete + tombstone (slug rename, `bot_telegram_id` NULL, status archived), idempotent → Task 2. ✓
- Re-creation safety (same slug + same bot id) → Task 2 explicit test. ✓
- `managed_tenants` excludes archived → Task 3. ✓
- Owner console 🗑 Delete + type-the-slug FSM, platform guard, authz, re-authorize at apply, /cancel, mismatch re-prompt → Task 4. ✓
- HTTP `POST /{id}/delete` with `confirm_slug`, platform guard, authz (owner|admin), audit → Task 5. ✓
- `tenant.delete` audit at both surfaces → Tasks 4 + 5. ✓
- New `owner.delete.*` keys auto-seed (insert-only) → Task 1. ✓
- Bot teardown via existing reconciler (status != active) → no code needed; covered by archive setting status archived (Task 2). ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows full code and exact commands.

**3. Type consistency:**
- `archive_tenant(session, tenant_id) -> Tenant | None` used identically in Tasks 2, 4, 5. ✓
- `OwnerManageCb(action="delete", tenant_id=…)` consistent across callbacks.py, on_manage, handler filter, tests. ✓
- `OwnerDelete.awaiting_confirm` consistent across handlers + tests. ✓
- `TenantDeleteIn{confirm_slug: str}` consistent across schema, route, tests. ✓
- Audit `action="tenant.delete"` consistent across Tasks 4, 5, and their tests. ✓
- Slug tombstone format `f"{slug}__del{tenant_id}"` consistent across Task 2 impl + Task 4/5 assertions. ✓
