# Master-bot superadmin cabinet — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A platform superadmin can, from inside the master bot via Telegram, view/manage all tenant bots (list, stats, suspend/resume, delete) and manage invites (create, list, revoke), through a button-driven cabinet.

**Architecture:** Bridge the superadmin Telegram-identity gap by linking a `tg_chat` identity to the superadmin account at bootstrap (env `BOOTSTRAP_SUPERADMIN_TG_ID`) and resolving it with a new `find_superadmin_by_tg`. A new master-bot router (`master_superadmin.py`) gates every action on that resolver and reuses existing domain functions (`set_tenant_status`, `archive_tenant`, `tenant_stats`, `create_invite`/`list_invites`/`revoke_invite`). UI is inline-keyboard driven from one `/admin` entry.

**Tech Stack:** Python 3.12, aiogram 3 (Router, CallbackData, FSM, F filters, InlineKeyboardBuilder), SQLModel/asyncpg, pytest + pytest-asyncio (auto mode).

**Conventions for every task:**
- Tests need the test PG/redis up at `172.30.0.2` / `172.30.0.3`.
- Run only the task's targeted tests during the task; full suite once at the end (Task 8).
- Run tests with `uv run pytest …`.
- New i18n keys auto-seed (insert-only) — no live `UPDATE` needed.
- Reuse the SP2 type-the-slug delete pattern and the existing master-bot handler test fakes.

---

### Task 1: Add the `admin.*` i18n keys

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py`
- Test: `tests/test_i18n_seed.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_i18n_seed.py`:

```python
def test_superadmin_cabinet_strings_present():
    from quantuum.i18n.seed_strings import BASE_STRINGS

    for key in [
        "admin.denied",
        "admin.menu.title",
        "admin.menu.kb.tenants",
        "admin.menu.kb.invites",
        "admin.tenants.title",
        "admin.tenants.empty",
        "admin.tenant.title",
        "admin.tenant.kb.stats",
        "admin.tenant.kb.suspend",
        "admin.tenant.kb.resume",
        "admin.tenant.kb.delete",
        "admin.kb.back",
        "admin.tenant.suspended",
        "admin.tenant.resumed",
        "admin.invites.title",
        "admin.invites.empty",
        "admin.invites.kb.new",
        "admin.invite.kb.revoke",
        "admin.invite.created",
        "admin.invite.revoked",
        "admin.stale",
    ]:
        assert key in BASE_STRINGS, f"missing {key}"
        assert "ru" in BASE_STRINGS[key] and "en" in BASE_STRINGS[key], f"{key} missing ru/en"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_i18n_seed.py::test_superadmin_cabinet_strings_present -v`
Expected: FAIL with `AssertionError: missing admin.denied`

- [ ] **Step 3: Add the keys**

In `src/quantuum/i18n/seed_strings.py`, insert this block right after the `owner.delete.platform_blocked` entry (the last of the SP2 owner-console keys):

```python
    # Superadmin cabinet (SP1, master bot /admin)
    "admin.denied": {
        "ru": "Недостаточно прав.",
        "en": "Not authorized.",
    },
    "admin.menu.title": {
        "ru": "🛠 Панель суперадмина",
        "en": "🛠 Superadmin panel",
    },
    "admin.menu.kb.tenants": {
        "ru": "🏢 Боты",
        "en": "🏢 Bots",
    },
    "admin.menu.kb.invites": {
        "ru": "🎟 Инвайты",
        "en": "🎟 Invites",
    },
    "admin.tenants.title": {
        "ru": "Все боты:",
        "en": "All bots:",
    },
    "admin.tenants.empty": {
        "ru": "Ботов пока нет.",
        "en": "No bots yet.",
    },
    "admin.tenant.title": {
        "ru": "Бот: {display_name} (/{slug}) — {status}",
        "en": "Bot: {display_name} (/{slug}) — {status}",
    },
    "admin.tenant.kb.stats": {
        "ru": "📊 Статистика",
        "en": "📊 Stats",
    },
    "admin.tenant.kb.suspend": {
        "ru": "⏸ Приостановить",
        "en": "⏸ Suspend",
    },
    "admin.tenant.kb.resume": {
        "ru": "▶️ Возобновить",
        "en": "▶️ Resume",
    },
    "admin.tenant.kb.delete": {
        "ru": "🗑 Удалить",
        "en": "🗑 Delete",
    },
    "admin.kb.back": {
        "ru": "⬅️ Назад",
        "en": "⬅️ Back",
    },
    "admin.tenant.suspended": {
        "ru": "⏸ Бот приостановлен.",
        "en": "⏸ Bot suspended.",
    },
    "admin.tenant.resumed": {
        "ru": "▶️ Бот возобновлён.",
        "en": "▶️ Bot resumed.",
    },
    "admin.invites.title": {
        "ru": "Активные инвайты:",
        "en": "Active invites:",
    },
    "admin.invites.empty": {
        "ru": "Активных инвайтов нет.",
        "en": "No active invites.",
    },
    "admin.invites.kb.new": {
        "ru": "➕ Новый инвайт",
        "en": "➕ New invite",
    },
    "admin.invite.kb.revoke": {
        "ru": "🗑 Отозвать",
        "en": "🗑 Revoke",
    },
    "admin.invite.created": {
        "ru": "Инвайт создан:\n{link}",
        "en": "Invite created:\n{link}",
    },
    "admin.invite.revoked": {
        "ru": "Инвайт отозван.",
        "en": "Invite revoked.",
    },
    "admin.stale": {
        "ru": "Не найдено — список обновлён.",
        "en": "Not found — list refreshed.",
    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_i18n_seed.py::test_superadmin_cabinet_strings_present -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/i18n/seed_strings.py tests/test_i18n_seed.py
git commit -m "feat(superadmin): seed admin.* cabinet i18n strings"
```

---

### Task 2: Identity bridge (settings + find_superadmin_by_tg + bootstrap link)

**Files:**
- Modify: `src/quantuum/settings.py` (add `bootstrap_superadmin_tg_id`)
- Modify: `src/quantuum/auth/identity.py` (add `find_superadmin_by_tg`)
- Modify: `src/quantuum/db/bootstrap.py` (link tg identity in `ensure_superadmin`)
- Test: `tests/test_superadmin_identity.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_superadmin_identity.py`:

```python
from quantuum.db.models import Account, AccountIdentity


async def _make_superadmin(session, *, tg=None):
    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    if tg is not None:
        session.add(
            AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=tg)
        )
    await session.commit()
    await session.refresh(acc)
    return acc


async def test_find_superadmin_by_tg_returns_superadmin(session):
    from quantuum.auth.identity import find_superadmin_by_tg

    acc = await _make_superadmin(session, tg="555")
    found = await find_superadmin_by_tg(session, "555")
    assert found is not None
    assert found.id == acc.id
    assert found.is_superadmin is True


async def test_find_superadmin_by_tg_ignores_platform_dup(session):
    """A non-superadmin account sharing the same tg id must not be returned."""
    from quantuum.auth.identity import find_superadmin_by_tg

    sa = await _make_superadmin(session, tg="777")
    # A platform-scoped, non-superadmin account with the SAME tg id (as the
    # master-bot AccountMiddleware would create).
    plain = Account(tenant_id=None, is_superadmin=False)
    session.add(plain)
    await session.flush()
    session.add(AccountIdentity(account_id=plain.id, provider="tg_chat", provider_user_id="777"))
    await session.commit()

    found = await find_superadmin_by_tg(session, "777")
    assert found is not None
    assert found.id == sa.id  # the superadmin, not the plain account


async def test_find_superadmin_by_tg_none_for_unknown(session):
    from quantuum.auth.identity import find_superadmin_by_tg

    assert await find_superadmin_by_tg(session, "404404") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_superadmin_identity.py -v`
Expected: FAIL with `ImportError: cannot import name 'find_superadmin_by_tg'`

- [ ] **Step 3a: Add the setting**

In `src/quantuum/settings.py`, add right after `bootstrap_superadmin_email`:

```python
    bootstrap_superadmin_tg_id: str = ""
```

- [ ] **Step 3b: Add `find_superadmin_by_tg`**

In `src/quantuum/auth/identity.py`, add after `find_superadmin_by_email`:

```python
async def find_superadmin_by_tg(session, tg_user_id: str) -> Account | None:
    """Resolve the superadmin Account linked to a Telegram user id.

    Filters on Account.is_superadmin, so a coexisting platform-scoped tg_chat
    identity with the same id (created by the master-bot middleware) is ignored.
    """
    result = await session.execute(
        select(AccountIdentity)
        .join(Account, Account.id == AccountIdentity.account_id)
        .where(
            AccountIdentity.provider == "tg_chat",
            AccountIdentity.provider_user_id == str(tg_user_id),
            Account.is_superadmin == True,  # noqa: E712
        )
    )
    identity = result.scalar_one_or_none()
    if identity is None:
        return None
    return await session.get(Account, identity.account_id)
```

(`select`, `Account`, `AccountIdentity` are already imported in this module.)

- [ ] **Step 3c: Link the tg identity at bootstrap (idempotent, no early-return)**

In `src/quantuum/db/bootstrap.py`, REPLACE the entire `ensure_superadmin` function with:

```python
async def ensure_superadmin(session) -> None:
    """Create the bootstrap superadmin from env and idempotently link its Telegram
    identity (both env-gated, idempotent across restarts)."""
    settings = get_settings()
    email = settings.bootstrap_superadmin_email
    if not email:
        return

    existing = await session.execute(
        select(AccountIdentity).where(
            AccountIdentity.provider == "magic_link", AccountIdentity.email == email
        )
    )
    identity = existing.scalar_one_or_none()
    if identity is not None:
        account_id = identity.account_id
    else:
        account = Account(tenant_id=None, is_superadmin=True)
        session.add(account)
        await session.flush()
        session.add(
            AccountIdentity(
                account_id=account.id, provider="magic_link", email=email, verified_at=utcnow()
            )
        )
        account_id = account.id

    tg_id = settings.bootstrap_superadmin_tg_id
    if tg_id:
        tg_existing = await session.execute(
            select(AccountIdentity).where(
                AccountIdentity.provider == "tg_chat",
                AccountIdentity.provider_user_id == tg_id,
                AccountIdentity.account_id == account_id,
            )
        )
        if tg_existing.scalar_one_or_none() is None:
            session.add(
                AccountIdentity(
                    account_id=account_id,
                    provider="tg_chat",
                    provider_user_id=tg_id,
                    verified_at=utcnow(),
                )
            )

    await session.commit()
```

- [ ] **Step 3d: Add the bootstrap-linking tests**

Append to `tests/test_superadmin_identity.py`:

```python
async def test_ensure_superadmin_links_tg_idempotently(session, monkeypatch):
    from quantuum.db import bootstrap as bs
    from quantuum.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("BOOTSTRAP_SUPERADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("BOOTSTRAP_SUPERADMIN_TG_ID", "12321")
    get_settings.cache_clear()

    # First run: creates the account + magic_link + tg_chat identity.
    await bs.ensure_superadmin(session)
    # Second run: must NOT create a duplicate tg_chat identity.
    await bs.ensure_superadmin(session)

    from quantuum.auth.identity import find_superadmin_by_tg

    sa = await find_superadmin_by_tg(session, "12321")
    assert sa is not None and sa.is_superadmin is True

    from sqlmodel import select as _select
    from quantuum.db.models import AccountIdentity as _AI

    rows = (
        await session.execute(
            _select(_AI).where(_AI.provider == "tg_chat", _AI.provider_user_id == "12321")
        )
    ).scalars().all()
    assert len(rows) == 1  # idempotent

    get_settings.cache_clear()
```

Before relying on `get_settings.cache_clear()`, confirm `get_settings` is an `@lru_cache`'d function in `src/quantuum/settings.py` (it is — `cache_clear` exists). If settings reads env differently, adapt: set the attributes on the returned settings object instead, and note it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_superadmin_identity.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/settings.py src/quantuum/auth/identity.py src/quantuum/db/bootstrap.py tests/test_superadmin_identity.py
git commit -m "feat(superadmin): link superadmin Telegram identity + find_superadmin_by_tg"
```

---

### Task 3: `SuperAdminCb` callback + `list_all_tenants` helper

**Files:**
- Modify: `src/quantuum/bot/ui/callbacks.py` (add `SuperAdminCb`)
- Modify: `src/quantuum/domain/tenants.py` (add `list_all_tenants`)
- Test: `tests/test_superadmin_helpers.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_superadmin_helpers.py`:

```python
from quantuum.db.models import Tenant


async def test_list_all_tenants_excludes_archived_and_platform(session):
    from quantuum.domain.tenants import list_all_tenants

    active = Tenant(slug="a-co", display_name="A Co", status="active")
    paused = Tenant(slug="b-co", display_name="B Co", status="suspended")
    archived = Tenant(slug="c-co__del9", display_name="C Co", status="archived")
    platform = Tenant(slug="platform", display_name="Platform", is_platform=True)
    for t in (active, paused, archived, platform):
        session.add(t)
    await session.commit()

    rows = await list_all_tenants(session)
    slugs = [t.slug for t in rows]
    assert "a-co" in slugs
    assert "b-co" in slugs  # suspended is still shown (manageable)
    assert "c-co__del9" not in slugs  # archived hidden
    assert "platform" not in slugs  # platform hidden


def test_superadmin_cb_roundtrips():
    from quantuum.bot.ui.callbacks import SuperAdminCb

    packed = SuperAdminCb(action="tenant", tenant_id=42).pack()
    cb = SuperAdminCb.unpack(packed)
    assert cb.action == "tenant"
    assert cb.tenant_id == 42
    assert cb.invite_id == 0  # default
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_superadmin_helpers.py -v`
Expected: FAIL (`ImportError` for `list_all_tenants` / `SuperAdminCb`).

- [ ] **Step 3a: Add `SuperAdminCb`**

Append to `src/quantuum/bot/ui/callbacks.py`:

```python
class SuperAdminCb(CallbackData, prefix="sa"):
    action: str  # menu | tenants | tenant | suspend | resume | delete | invites | newinvite | revoke
    tenant_id: int = 0
    invite_id: int = 0
```

- [ ] **Step 3b: Add `list_all_tenants`**

In `src/quantuum/domain/tenants.py`, add after `archive_tenant`:

```python
async def list_all_tenants(session) -> list[Tenant]:
    """All non-archived, non-platform tenants, ordered by id (superadmin cabinet)."""
    result = await session.execute(
        select(Tenant)
        .where(Tenant.status != "archived", Tenant.is_platform == False)  # noqa: E712
        .order_by(Tenant.id)
    )
    return list(result.scalars().all())
```

(`select` and `Tenant` are already imported in this module.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_superadmin_helpers.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/ui/callbacks.py src/quantuum/domain/tenants.py tests/test_superadmin_helpers.py
git commit -m "feat(superadmin): SuperAdminCb + list_all_tenants helper"
```

---

### Task 4: Cabinet entry `/admin` + menu + authz + router registration

**Files:**
- Create: `src/quantuum/bot/handlers/master_superadmin.py`
- Modify: `src/quantuum/bot/master_app.py` (register the router)
- Test: `tests/test_superadmin_cabinet.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_superadmin_cabinet.py`:

```python
from types import SimpleNamespace

from quantuum.db.models import Account, AccountIdentity

from .conftest import build_translator

SA_TG = 900900
PLAIN_TG = 111222


class FakeMessage:
    def __init__(self, *, from_user_id, text=""):
        self.text = text
        self.from_user = SimpleNamespace(id=from_user_id)
        self.chat = SimpleNamespace(id=from_user_id)
        self.answers = []  # (text, reply_markup)

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup))


class FakeCallbackQuery:
    def __init__(self, *, from_user_id):
        self.from_user = SimpleNamespace(id=from_user_id)
        self.message = FakeMessage(from_user_id=from_user_id)
        self.answers = []  # (text, kwargs)

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


class FakeState:
    def __init__(self, data=None):
        self._data = dict(data or {})
        self.state = None

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kw):
        self._data.update(kw)

    async def set_state(self, s):
        self.state = s

    async def clear(self):
        self._data = {}
        self.state = None


def _patch_sessionmaker(monkeypatch, module, session):
    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(module, "get_sessionmaker", lambda: _Maker())


def _inline(markup):
    return [b for row in markup.inline_keyboard for b in row]


async def _make_superadmin(session, tg=SA_TG):
    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    session.add(AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=str(tg)))
    await session.commit()
    await session.refresh(acc)
    return acc


async def test_admin_menu_for_superadmin(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    i18n = await build_translator(session, default_tenant.id)

    msg = FakeMessage(from_user_id=SA_TG)
    await sa.on_admin(msg, i18n=i18n)

    text, markup = msg.answers[0]
    actions = {SuperAdminCb.unpack(b.callback_data).action for b in _inline(markup)}
    assert actions == {"tenants", "invites"}


async def test_admin_denied_for_non_superadmin(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa

    _patch_sessionmaker(monkeypatch, sa, session)
    i18n = await build_translator(session, default_tenant.id)

    msg = FakeMessage(from_user_id=PLAIN_TG)
    await sa.on_admin(msg, i18n=i18n)

    assert len(msg.answers) == 1
    text, markup = msg.answers[0]
    assert markup is None  # no menu
    assert "прав" in text or "authoriz" in text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_superadmin_cabinet.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.bot.handlers.master_superadmin'`

- [ ] **Step 3a: Create the handler module skeleton**

Create `src/quantuum/bot/handlers/master_superadmin.py`:

```python
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.auth.identity import find_superadmin_by_tg
from quantuum.bot.ui.callbacks import SuperAdminCb
from quantuum.db.session import get_sessionmaker
from quantuum.domain.audit import record_audit
from quantuum.domain.invites import create_invite, list_invites, revoke_invite
from quantuum.domain.stats import tenant_stats
from quantuum.domain.tenants import archive_tenant, list_all_tenants, set_tenant_status
from quantuum.db.models import Tenant
from quantuum.i18n import Translator
from quantuum.settings import get_settings

router = Router()


async def _menu_kb(i18n: Translator):
    b = InlineKeyboardBuilder()
    b.button(text=await i18n("admin.menu.kb.tenants"), callback_data=SuperAdminCb(action="tenants"))
    b.button(text=await i18n("admin.menu.kb.invites"), callback_data=SuperAdminCb(action="invites"))
    b.adjust(2)
    return b.as_markup()


@router.message(Command("admin"))
async def on_admin(message: Message, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(message.from_user.id))
    if sa is None:
        await message.answer(await i18n("admin.denied"))
        return
    await message.answer(await i18n("admin.menu.title"), reply_markup=await _menu_kb(i18n))
```

- [ ] **Step 3b: Register the router**

In `src/quantuum/bot/master_app.py`, update the handler import + includes:

```python
    from quantuum.bot.handlers import master_onboarding, master_superadmin, owner_console

    dp.include_router(master_onboarding.router)
    dp.include_router(owner_console.router)
    dp.include_router(master_superadmin.router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_superadmin_cabinet.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/master_superadmin.py src/quantuum/bot/master_app.py tests/test_superadmin_cabinet.py
git commit -m "feat(superadmin): /admin cabinet entry + menu (superadmin-gated)"
```

---

### Task 5: Cabinet tenants — list, manage screen, stats, suspend/resume

**Files:**
- Modify: `src/quantuum/bot/handlers/master_superadmin.py`
- Test: `tests/test_superadmin_cabinet.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_superadmin_cabinet.py` (reuses the fakes + `_make_superadmin` + `SA_TG`/`PLAIN_TG` from Task 4):

```python
from sqlmodel import select  # noqa: E402  (top-of-file import is fine too)
from quantuum.db.models import AuditLog, Tenant, TenantBot  # noqa: E402


async def _make_tenant_with_bot(session, *, slug, status="active"):
    t = Tenant(slug=slug, display_name=slug.upper(), status=status)
    session.add(t)
    await session.flush()
    bot = TenantBot(
        tenant_id=t.id, bot_token_enc=b"x", webhook_secret_path=f"wh-{slug}",
        status="paused" if status == "suspended" else "active",
    )
    session.add(bot)
    await session.commit()
    await session.refresh(t)
    await session.refresh(bot)
    return t, bot


async def _audit_rows(session, tenant_id, action):
    rows = await session.execute(
        select(AuditLog).where(AuditLog.tenant_id == tenant_id, AuditLog.action == action)
    )
    return list(rows.scalars().all())


async def test_tenants_list_lists_tenants(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    t, _bot = await _make_tenant_with_bot(session, slug="acme")
    i18n = await build_translator(session, default_tenant.id)

    q = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_tenants(q, SuperAdminCb(action="tenants"), i18n=i18n)

    _, markup = q.message.answers[0]
    cbs = [SuperAdminCb.unpack(b.callback_data) for b in _inline(markup)]
    tenant_ids = {cb.tenant_id for cb in cbs if cb.action == "tenant"}
    assert t.id in tenant_ids


async def test_tenant_suspend_then_resume(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    t, bot = await _make_tenant_with_bot(session, slug="beta")
    i18n = await build_translator(session, default_tenant.id)

    q1 = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_tenant_suspend(q1, SuperAdminCb(action="suspend", tenant_id=t.id), i18n=i18n)
    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "suspended"
    assert bot.status == "paused"
    assert len(await _audit_rows(session, t.id, "tenant.pause")) == 1

    q2 = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_tenant_resume(q2, SuperAdminCb(action="resume", tenant_id=t.id), i18n=i18n)
    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "active"
    assert bot.status == "active"
    assert len(await _audit_rows(session, t.id, "tenant.resume")) == 1


async def test_tenant_suspend_denied_for_non_superadmin(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    t, _bot = await _make_tenant_with_bot(session, slug="gamma")
    i18n = await build_translator(session, default_tenant.id)

    q = FakeCallbackQuery(from_user_id=PLAIN_TG)  # not a superadmin
    await sa.on_tenant_suspend(q, SuperAdminCb(action="suspend", tenant_id=t.id), i18n=i18n)

    await session.refresh(t)
    assert t.status == "active"  # unchanged
    assert await _audit_rows(session, t.id, "tenant.pause") == []
    assert q.answers and q.answers[-1][1].get("show_alert") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_superadmin_cabinet.py -k "tenants_list or suspend or resume" -v`
Expected: FAIL (`master_superadmin` has no `on_tenants` / `on_tenant_suspend` / `on_tenant_resume`).

- [ ] **Step 3: Add the tenants handlers**

In `src/quantuum/bot/handlers/master_superadmin.py`, add these helpers + handlers after `on_admin`:

```python
async def _tenants_kb(tenants, i18n: Translator):
    b = InlineKeyboardBuilder()
    for t in tenants:
        b.button(
            text=f"{t.display_name} · {t.status}",
            callback_data=SuperAdminCb(action="tenant", tenant_id=t.id),
        )
    b.button(text=await i18n("admin.kb.back"), callback_data=SuperAdminCb(action="menu"))
    b.adjust(1)
    return b.as_markup()


async def _tenant_manage_kb(tenant: Tenant, i18n: Translator):
    b = InlineKeyboardBuilder()
    b.button(text=await i18n("admin.tenant.kb.stats"), callback_data=SuperAdminCb(action="stats", tenant_id=tenant.id))
    if tenant.status == "active":
        b.button(text=await i18n("admin.tenant.kb.suspend"), callback_data=SuperAdminCb(action="suspend", tenant_id=tenant.id))
    else:
        b.button(text=await i18n("admin.tenant.kb.resume"), callback_data=SuperAdminCb(action="resume", tenant_id=tenant.id))
    b.button(text=await i18n("admin.tenant.kb.delete"), callback_data=SuperAdminCb(action="delete", tenant_id=tenant.id))
    b.button(text=await i18n("admin.kb.back"), callback_data=SuperAdminCb(action="tenants"))
    b.adjust(1)
    return b.as_markup()


@router.callback_query(SuperAdminCb.filter(F.action == "menu"))
async def on_menu(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if await find_superadmin_by_tg(session, str(query.from_user.id)) is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
    await query.message.answer(await i18n("admin.menu.title"), reply_markup=await _menu_kb(i18n))
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "tenants"))
async def on_tenants(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if await find_superadmin_by_tg(session, str(query.from_user.id)) is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        tenants = await list_all_tenants(session)
    if not tenants:
        await query.message.answer(await i18n("admin.tenants.empty"))
        await query.answer()
        return
    await query.message.answer(
        await i18n("admin.tenants.title"), reply_markup=await _tenants_kb(tenants, i18n)
    )
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "tenant"))
async def on_tenant(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if await find_superadmin_by_tg(session, str(query.from_user.id)) is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        tenant = await session.get(Tenant, callback_data.tenant_id)
    if tenant is None:
        await query.answer(await i18n("admin.stale"), show_alert=True)
        return
    await query.message.answer(
        await i18n("admin.tenant.title", display_name=tenant.display_name, slug=tenant.slug, status=tenant.status),
        reply_markup=await _tenant_manage_kb(tenant, i18n),
    )
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "stats"))
async def on_tenant_stats(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if await find_superadmin_by_tg(session, str(query.from_user.id)) is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        s = await tenant_stats(session, callback_data.tenant_id)
    await query.message.answer(
        await i18n(
            "owner.stats.text",
            period_days=s["period_days"], active_customers=s["active_customers"],
            paid_customers=s["paid_customers"], dau=s["dau"], wau=s["wau"], mau=s["mau"],
            revenue_cents=s["revenue_cents"], mrr_cents=s["mrr_cents"],
            requests_by_kind=s["requests_by_kind"],
        )
    )
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "suspend"))
async def on_tenant_suspend(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(query.from_user.id))
        if sa is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        await set_tenant_status(session, callback_data.tenant_id, "suspended", "paused")
        await record_audit(
            session, tenant_id=callback_data.tenant_id, actor_account_id=sa.id,
            action="tenant.pause", entity_type="tenant", entity_id=callback_data.tenant_id,
        )
        await session.commit()
    await query.message.answer(await i18n("admin.tenant.suspended"))
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "resume"))
async def on_tenant_resume(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(query.from_user.id))
        if sa is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        await set_tenant_status(session, callback_data.tenant_id, "active", "active")
        await record_audit(
            session, tenant_id=callback_data.tenant_id, actor_account_id=sa.id,
            action="tenant.resume", entity_type="tenant", entity_id=callback_data.tenant_id,
        )
        await session.commit()
    await query.message.answer(await i18n("admin.tenant.resumed"))
    await query.answer()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_superadmin_cabinet.py -v`
Expected: PASS (all — Task 4 menu tests + the new tenants tests).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/master_superadmin.py tests/test_superadmin_cabinet.py
git commit -m "feat(superadmin): cabinet tenants list/stats/suspend/resume"
```

---

### Task 6: Cabinet tenant delete (type-the-slug FSM)

**Files:**
- Modify: `src/quantuum/bot/handlers/master_superadmin.py`
- Test: `tests/test_superadmin_cabinet.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_superadmin_cabinet.py`:

```python
async def test_delete_flow_success(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    t, bot = await _make_tenant_with_bot(session, slug="delme")
    i18n = await build_translator(session, default_tenant.id)
    state = FakeState()

    q = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_tenant_delete(q, SuperAdminCb(action="delete", tenant_id=t.id), state, i18n=i18n)
    assert state.state == sa.SuperAdminDelete.awaiting_confirm
    assert (await state.get_data())["slug"] == t.slug

    msg = FakeMessage(from_user_id=SA_TG, text=t.slug)
    await sa.on_delete_confirm(msg, state, i18n=i18n)

    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "archived"
    assert t.slug.endswith(f"__del{t.id}")
    assert bot.status == "archived"
    assert len(await _audit_rows(session, t.id, "tenant.delete")) == 1
    assert state.state is None


async def test_delete_slug_mismatch_keeps_tenant(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    t, _bot = await _make_tenant_with_bot(session, slug="keepme")
    i18n = await build_translator(session, default_tenant.id)
    state = FakeState()

    q = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_tenant_delete(q, SuperAdminCb(action="delete", tenant_id=t.id), state, i18n=i18n)

    msg = FakeMessage(from_user_id=SA_TG, text="WRONG")
    await sa.on_delete_confirm(msg, state, i18n=i18n)

    await session.refresh(t)
    assert t.status == "active"
    assert await _audit_rows(session, t.id, "tenant.delete") == []
    assert state.state == sa.SuperAdminDelete.awaiting_confirm  # stays to retry


async def test_delete_request_denied_for_non_superadmin(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    t, _bot = await _make_tenant_with_bot(session, slug="safe")
    i18n = await build_translator(session, default_tenant.id)
    state = FakeState()

    q = FakeCallbackQuery(from_user_id=PLAIN_TG)
    await sa.on_tenant_delete(q, SuperAdminCb(action="delete", tenant_id=t.id), state, i18n=i18n)

    assert state.state is None
    assert q.answers and q.answers[-1][1].get("show_alert") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_superadmin_cabinet.py -k delete -v`
Expected: FAIL (`master_superadmin` has no `SuperAdminDelete` / `on_tenant_delete` / `on_delete_confirm`).

- [ ] **Step 3: Add the delete FSM + handlers**

In `src/quantuum/bot/handlers/master_superadmin.py`, append (the `/cancel` handler BEFORE the catch-all confirm handler):

```python
class SuperAdminDelete(StatesGroup):
    awaiting_confirm = State()


@router.callback_query(SuperAdminCb.filter(F.action == "delete"))
async def on_tenant_delete(
    query: CallbackQuery, callback_data: SuperAdminCb, state: FSMContext, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        if await find_superadmin_by_tg(session, str(query.from_user.id)) is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        tenant = await session.get(Tenant, callback_data.tenant_id)
    if tenant is None:
        await query.answer(await i18n("admin.stale"), show_alert=True)
        return
    await state.set_state(SuperAdminDelete.awaiting_confirm)
    await state.update_data(tenant_id=callback_data.tenant_id, slug=tenant.slug)
    await query.message.answer(await i18n("owner.delete.prompt", slug=tenant.slug))
    await query.answer()


@router.message(Command("cancel"), SuperAdminDelete.awaiting_confirm)
async def on_delete_cancel(message: Message, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await message.answer(await i18n("owner.delete.cancelled"))


@router.message(SuperAdminDelete.awaiting_confirm)
async def on_delete_confirm(message: Message, state: FSMContext, i18n: Translator) -> None:
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    expected_slug = data["slug"]
    if (message.text or "").strip() != expected_slug:
        await message.answer(await i18n("owner.delete.mismatch", slug=expected_slug))
        return  # stay in state to retry
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(message.from_user.id))
        if sa is None:
            await message.answer(await i18n("admin.denied"))
            await state.clear()
            return
        await archive_tenant(session, tenant_id)
        await record_audit(
            session, tenant_id=tenant_id, actor_account_id=sa.id,
            action="tenant.delete", entity_type="tenant", entity_id=tenant_id,
        )
        await session.commit()
    await state.clear()
    await message.answer(await i18n("owner.delete.done"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_superadmin_cabinet.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/master_superadmin.py tests/test_superadmin_cabinet.py
git commit -m "feat(superadmin): cabinet tenant delete (type-the-slug confirm)"
```

---

### Task 7: Cabinet invites — list, new, revoke

**Files:**
- Modify: `src/quantuum/bot/handlers/master_superadmin.py`
- Test: `tests/test_superadmin_cabinet.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_superadmin_cabinet.py`:

```python
async def test_new_invite_returns_deeplink(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb
    from quantuum.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("MASTER_BOT_USERNAME", "quantuum_master_bot")
    get_settings.cache_clear()

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    i18n = await build_translator(session, default_tenant.id)

    q = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_new_invite(q, SuperAdminCb(action="newinvite"), i18n=i18n)

    text = q.message.answers[0][0]
    assert "t.me/quantuum_master_bot?start=" in text
    get_settings.cache_clear()


async def test_invites_list_and_revoke(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb
    from quantuum.domain.invites import create_invite

    _patch_sessionmaker(monkeypatch, sa, session)
    await _make_superadmin(session)
    inv = await create_invite(session, created_by_account_id=None)
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)

    # list shows the invite with a revoke button
    q1 = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_invites(q1, SuperAdminCb(action="invites"), i18n=i18n)
    _, markup = q1.message.answers[0]
    revoke_ids = {
        SuperAdminCb.unpack(b.callback_data).invite_id
        for b in _inline(markup)
        if SuperAdminCb.unpack(b.callback_data).action == "revoke"
    }
    assert inv.id in revoke_ids

    # revoke it
    q2 = FakeCallbackQuery(from_user_id=SA_TG)
    await sa.on_revoke_invite(q2, SuperAdminCb(action="revoke", invite_id=inv.id), i18n=i18n)
    await session.refresh(inv)
    assert inv.status == "revoked"


async def test_new_invite_denied_for_non_superadmin(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import master_superadmin as sa
    from quantuum.bot.ui.callbacks import SuperAdminCb

    _patch_sessionmaker(monkeypatch, sa, session)
    i18n = await build_translator(session, default_tenant.id)

    q = FakeCallbackQuery(from_user_id=PLAIN_TG)
    await sa.on_new_invite(q, SuperAdminCb(action="newinvite"), i18n=i18n)

    assert q.answers and q.answers[-1][1].get("show_alert") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_superadmin_cabinet.py -k invite -v`
Expected: FAIL (`master_superadmin` has no `on_invites` / `on_new_invite` / `on_revoke_invite`).

- [ ] **Step 3: Add the invites handlers**

In `src/quantuum/bot/handlers/master_superadmin.py`, append:

```python
async def _invites_kb(invites, i18n: Translator):
    b = InlineKeyboardBuilder()
    for inv in invites:
        b.button(
            text=f"{inv.code} · {inv.tier} · {inv.used_count}/{inv.max_uses}",
            callback_data=SuperAdminCb(action="revoke", invite_id=inv.id),
        )
    b.button(text=await i18n("admin.invites.kb.new"), callback_data=SuperAdminCb(action="newinvite"))
    b.button(text=await i18n("admin.kb.back"), callback_data=SuperAdminCb(action="menu"))
    b.adjust(1)
    return b.as_markup()


def _invite_deeplink(code: str) -> str:
    return f"https://t.me/{get_settings().master_bot_username}?start={code}"


@router.callback_query(SuperAdminCb.filter(F.action == "invites"))
async def on_invites(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if await find_superadmin_by_tg(session, str(query.from_user.id)) is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        invites = [i for i in await list_invites(session) if i.status == "active"]
    if not invites:
        await query.message.answer(
            await i18n("admin.invites.empty"), reply_markup=await _invites_kb([], i18n)
        )
        await query.answer()
        return
    await query.message.answer(
        await i18n("admin.invites.title"), reply_markup=await _invites_kb(invites, i18n)
    )
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "newinvite"))
async def on_new_invite(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(query.from_user.id))
        if sa is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        invite = await create_invite(session, created_by_account_id=sa.id)
        await record_audit(
            session, tenant_id=None, actor_account_id=sa.id,
            action="platform.invite.create", entity_type="tenant_invite", entity_id=invite.id,
        )
        await session.commit()
        code = invite.code
    await query.message.answer(
        await i18n("admin.invite.created", link=_invite_deeplink(code))
    )
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "revoke"))
async def on_revoke_invite(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(query.from_user.id))
        if sa is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        revoked = await revoke_invite(session, callback_data.invite_id)
        if revoked is None:
            await query.answer(await i18n("admin.stale"), show_alert=True)
            return
        await record_audit(
            session, tenant_id=None, actor_account_id=sa.id,
            action="platform.invite.revoke", entity_type="tenant_invite", entity_id=callback_data.invite_id,
        )
        await session.commit()
    await query.message.answer(await i18n("admin.invite.revoked"))
    await query.answer()
```

Before relying on `create_invite(session, created_by_account_id=...)` and `revoke_invite(session, invite_id)`, confirm their signatures in `src/quantuum/domain/invites.py` (they are: `create_invite(session, *, created_by_account_id, tier="basic", max_uses=1, expires_at=None, preset_*=None)` and `revoke_invite(session, invite_id) -> TenantInvite | None`). Also confirm `record_audit` accepts `tenant_id=None` (it does — `audit_log.tenant_id` is nullable). If `revoke_invite` does not commit internally, the handler's `session.commit()` covers it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_superadmin_cabinet.py -v`
Expected: PASS (all cabinet tests).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/master_superadmin.py tests/test_superadmin_cabinet.py
git commit -m "feat(superadmin): cabinet invites list/create/revoke"
```

---

### Task 8: Full suite + lint

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS (all). Investigate and fix any failure before proceeding. In particular, the env-var tests (`BOOTSTRAP_SUPERADMIN_*`, `MASTER_BOT_USERNAME`) must `get_settings.cache_clear()` after themselves so they don't leak settings into other tests — if any unrelated test fails after this branch, suspect a leaked monkeypatched setting.

- [ ] **Step 2: Lint**

Run: `uv run ruff check src/ tests/`
Expected: clean. Fix any issues (e.g. unused imports).

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: lint after superadmin cabinet"
```

(Skip if there is nothing to commit.)

---

## Self-Review

**1. Spec coverage:**
- Identity bridge (env tg id + bootstrap link + `find_superadmin_by_tg`, coexists with platform dup) → Task 2. ✓
- `SuperAdminCb` + `list_all_tenants` (excl. archived + platform) → Task 3. ✓
- Button-driven `/admin` menu, superadmin-gated, terse denial → Task 4. ✓
- Tenants: list + stats + suspend/resume → Task 5. ✓
- Tenant delete via type-the-slug (reuse `owner.delete.*`) → Task 6. ✓
- Invites: create (deep-link) + list + revoke → Task 7. ✓
- Audit: `tenant.pause`/`tenant.resume`/`tenant.delete` + `platform.invite.create`/`platform.invite.revoke`, actor = superadmin → Tasks 5–7. ✓
- New `admin.*` keys auto-seed (insert-only) → Task 1. ✓
- Tests for identity, gate, tenants, delete, invites, authz-on-callbacks → Tasks 2–7. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows full code. "Confirm the signature" notes are verification guards, not missing work (the signatures are quoted).

**3. Type consistency:**
- `SuperAdminCb(action: str, tenant_id: int = 0, invite_id: int = 0)` consistent across callbacks.py, handlers, tests. ✓
- `find_superadmin_by_tg(session, tg_user_id) -> Account | None` consistent across identity.py, every handler, tests. ✓
- `list_all_tenants(session) -> list[Tenant]` consistent (Task 3 impl, Task 5 usage). ✓
- Handler names (`on_admin`, `on_menu`, `on_tenants`, `on_tenant`, `on_tenant_stats`, `on_tenant_suspend`, `on_tenant_resume`, `on_tenant_delete`, `on_delete_cancel`, `on_delete_confirm`, `on_invites`, `on_new_invite`, `on_revoke_invite`) and `SuperAdminDelete.awaiting_confirm` consistent between impl and tests. ✓
- Audit action strings consistent between handlers and test assertions. ✓
- Reused `owner.delete.prompt/mismatch/done/cancelled` exist (added in SP2). ✓
