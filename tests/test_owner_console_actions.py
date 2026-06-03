"""Handler-level tests for owner-console manage callbacks + /transfer FSM (Plan 5c, Tasks 4+5).

Reuses the fake Message/CallbackQuery + monkeypatched get_sessionmaker pattern from
tests/test_owner_console_handlers.py and tests/test_master_onboarding.py. The FSM
context is faked with a small object that persists its data dict across the two
/transfer handler calls.
"""
from types import SimpleNamespace

from sqlmodel import select

from quantuum.db.models import (
    Account,
    AccountIdentity,
    AuditLog,
    Tenant,
    TenantBot,
    TenantRole,
)
from quantuum.domain.tenants import grant_role

from .conftest import build_translator

OWNER_TG = 111
CUSTOMER_TG = 222
ADMIN_TG = 333


# ── fakes ─────────────────────────────────────────────────────────────────────

class FakeMessage:
    def __init__(self, *, from_user_id, text=""):
        self.text = text
        self.from_user = SimpleNamespace(id=from_user_id)
        self.chat = SimpleNamespace(id=from_user_id)
        self.answers = []  # list of (text, reply_markup)
        self.edits = []  # list of (text, reply_markup)

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup))

    async def edit_text(self, text, reply_markup=None, **kwargs):
        self.edits.append((text, reply_markup))


class FakeCallbackQuery:
    def __init__(self, *, from_user_id):
        self.from_user = SimpleNamespace(id=from_user_id)
        self.message = FakeMessage(from_user_id=from_user_id)
        self.answers = []  # list of (text, kwargs)

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

    async def set_state(self, state):
        self.state = state

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


# ── seeding ───────────────────────────────────────────────────────────────────

async def _make_tenant(session, slug, display_name, *, status="active", is_platform=False):
    t = Tenant(slug=slug, display_name=display_name, status=status, is_platform=is_platform)
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


async def _seed_bot(session, tenant_id, *, status="active"):
    bot = TenantBot(
        tenant_id=tenant_id,
        bot_token_enc=b"x",
        webhook_secret_path=f"wh-{tenant_id}-{status}",
        status=status,
    )
    session.add(bot)
    await session.commit()
    await session.refresh(bot)
    return bot


async def _seed_account(session, *, tenant, tg, role=None):
    acc = Account(tenant_id=tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    session.add(AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=str(tg)))
    await session.commit()
    if role is not None:
        await grant_role(session, tenant_id=tenant.id, account_id=acc.id, role=role)
    return acc


async def _seed_owner_tenant(session, slug="acme", display_name="Acme"):
    """Tenant T with an owner (tg 111), a TenantBot, and a customer (tg 222, no role)."""
    t = await _make_tenant(session, slug, display_name)
    bot = await _seed_bot(session, t.id)
    owner = await _seed_account(session, tenant=t, tg=OWNER_TG, role="owner")
    customer = await _seed_account(session, tenant=t, tg=CUSTOMER_TG, role=None)
    return t, bot, owner, customer


async def _audit_rows(session, tenant_id, action):
    result = await session.execute(
        select(AuditLog).where(AuditLog.tenant_id == tenant_id, AuditLog.action == action)
    )
    return list(result.scalars().all())


# ── Task 4: stats ──────────────────────────────────────────────────────────────

async def test_stats_callback(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t, _bot, _owner, _cust = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)

    query = FakeCallbackQuery(from_user_id=OWNER_TG)
    await oc.on_manage_stats(query, OwnerManageCb(action="stats", tenant_id=t.id), i18n=i18n)

    assert query.message.edits, "stats text should re-render in place"
    text = query.message.edits[0][0]
    assert "Статистика" in text
    # numbers present
    assert "Активные" in text
    assert "DAU" in text
    assert "Выручка" in text
    # query.answer() acknowledged
    assert query.answers and query.answers[-1][0] is None


# ── Task 4: pause / resume ──────────────────────────────────────────────────────

async def test_pause_then_resume_by_owner(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t, bot, _owner, _cust = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)

    # pause
    q1 = FakeCallbackQuery(from_user_id=OWNER_TG)
    await oc.on_manage_pause(q1, OwnerManageCb(action="pause", tenant_id=t.id), i18n=i18n)

    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "suspended"
    assert bot.status == "paused"
    assert len(await _audit_rows(session, t.id, "tenant.pause")) == 1
    assert q1.message.answers, "pause confirmation should be sent"

    # resume
    q2 = FakeCallbackQuery(from_user_id=OWNER_TG)
    await oc.on_manage_resume(q2, OwnerManageCb(action="resume", tenant_id=t.id), i18n=i18n)

    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "active"
    assert bot.status == "active"
    assert len(await _audit_rows(session, t.id, "tenant.resume")) == 1


async def test_pause_by_non_owner_denied(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t, bot, _owner, _cust = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)

    # tg 222 holds a customer account but no role
    q = FakeCallbackQuery(from_user_id=CUSTOMER_TG)
    await oc.on_manage_pause(q, OwnerManageCb(action="pause", tenant_id=t.id), i18n=i18n)

    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "active"  # unchanged
    assert bot.status == "active"
    assert await _audit_rows(session, t.id, "tenant.pause") == []
    # alert raised
    assert q.answers and q.answers[-1][0] == "Нет прав"
    assert q.answers[-1][1].get("show_alert") is True


async def test_admin_cannot_pause_tenant(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t, bot, _owner, _cust = await _seed_owner_tenant(session)
    await _seed_account(session, tenant=t, tg=ADMIN_TG, role="admin")
    i18n = await build_translator(session, t.id)

    q = FakeCallbackQuery(from_user_id=ADMIN_TG)
    await oc.on_manage_pause(q, OwnerManageCb(action="pause", tenant_id=t.id), i18n=i18n)

    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "active"  # unchanged
    assert bot.status == "active"
    assert await _audit_rows(session, t.id, "tenant.pause") == []
    assert q.answers and q.answers[-1][0] == "Нет прав"
    assert q.answers[-1][1].get("show_alert") is True


async def test_pause_platform_tenant_blocked(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t = await _make_tenant(session, "platform", "Platform", is_platform=True)
    bot = await _seed_bot(session, t.id)
    await _seed_account(session, tenant=t, tg=OWNER_TG, role="owner")
    i18n = await build_translator(session, t.id)

    q = FakeCallbackQuery(from_user_id=OWNER_TG)
    await oc.on_manage_pause(q, OwnerManageCb(action="pause", tenant_id=t.id), i18n=i18n)

    await session.refresh(t)
    await session.refresh(bot)
    assert t.status == "active"  # unchanged
    assert bot.status == "active"
    assert await _audit_rows(session, t.id, "tenant.pause") == []
    assert q.answers and q.answers[-1][1].get("show_alert") is True


# ── Workstream F: Transfer button wires the FSM ─────────────────────────────────

async def test_transfer_button_enters_fsm_for_owner(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t, _bot, _owner, _cust = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)
    state = FakeState()

    query = FakeCallbackQuery(from_user_id=OWNER_TG)
    await oc.on_manage_transfer(
        query, OwnerManageCb(action="transfer", tenant_id=t.id), state, i18n=i18n
    )

    assert state.state == oc.OwnerTransfer.awaiting_target
    assert (await state.get_data())["tenant_id"] == t.id
    assert query.message.answers, "transfer prompt should be sent"


async def test_transfer_button_denied_for_admin(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t, _bot, _owner, _cust = await _seed_owner_tenant(session)
    await _seed_account(session, tenant=t, tg=ADMIN_TG, role="admin")
    i18n = await build_translator(session, t.id)
    state = FakeState()

    query = FakeCallbackQuery(from_user_id=ADMIN_TG)
    await oc.on_manage_transfer(
        query, OwnerManageCb(action="transfer", tenant_id=t.id), state, i18n=i18n
    )

    assert state.state is None  # no FSM entered
    assert query.answers and query.answers[-1][0] == "Нет прав"
    assert query.answers[-1][1].get("show_alert") is True


# ── Task 5: /transfer FSM ───────────────────────────────────────────────────────

async def test_transfer_success(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc

    _patch_sessionmaker(monkeypatch, oc, session)
    t, _bot, _owner, customer = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)

    state = FakeState()

    # step 1: /transfer <slug> by the owner
    msg1 = FakeMessage(from_user_id=OWNER_TG)
    await oc.on_transfer_cmd(msg1, SimpleNamespace(args=t.slug), state, i18n=i18n)
    assert state.state == oc.OwnerTransfer.awaiting_target

    # step 2: send the new owner's tg id
    msg2 = FakeMessage(from_user_id=OWNER_TG, text=str(CUSTOMER_TG))
    await oc.on_transfer_target(msg2, state, i18n=i18n)

    await session.refresh(t)
    assert t.primary_owner_account_id == customer.id
    # customer now has the owner role
    result = await session.execute(
        select(TenantRole).where(
            TenantRole.tenant_id == t.id,
            TenantRole.account_id == customer.id,
            TenantRole.role == "owner",
        )
    )
    assert result.scalar_one_or_none() is not None
    # audit
    rows = await _audit_rows(session, t.id, "tenant.transfer")
    assert len(rows) == 1
    assert rows[0].payload_jsonb.get("after") == customer.id
    assert state.state is None  # cleared


async def test_transfer_reauthorizes_at_apply_time(session, monkeypatch):
    """If the owner's role is revoked after /transfer but before the target step,
    on_transfer_target must refuse: reply no-rights, clear state, no transfer."""
    from quantuum.bot.handlers import owner_console as oc

    _patch_sessionmaker(monkeypatch, oc, session)
    t, _bot, owner, customer = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)
    before_owner = t.primary_owner_account_id

    state = FakeState()
    # step 1: /transfer <slug> by the owner (state set)
    msg1 = FakeMessage(from_user_id=OWNER_TG)
    await oc.on_transfer_cmd(msg1, SimpleNamespace(args=t.slug), state, i18n=i18n)
    assert state.state == oc.OwnerTransfer.awaiting_target

    # revoke the owner's role before the apply step
    result = await session.execute(
        select(TenantRole).where(
            TenantRole.tenant_id == t.id,
            TenantRole.account_id == owner.id,
            TenantRole.role == "owner",
        )
    )
    role_row = result.scalar_one()
    await session.delete(role_row)
    await session.commit()

    # step 2: send the new owner's tg id — should be refused
    msg2 = FakeMessage(from_user_id=OWNER_TG, text=str(CUSTOMER_TG))
    await oc.on_transfer_target(msg2, state, i18n=i18n)

    await session.refresh(t)
    assert t.primary_owner_account_id == before_owner  # unchanged
    assert await _audit_rows(session, t.id, "tenant.transfer") == []
    assert state.state is None  # cleared
    assert any("Больше нет прав" in a[0] for a in msg2.answers)


async def test_transfer_by_non_owner(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc

    _patch_sessionmaker(monkeypatch, oc, session)
    t, _bot, _owner, _cust = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)

    state = FakeState()
    # tg 222 is a customer, not an owner
    msg = FakeMessage(from_user_id=CUSTOMER_TG)
    await oc.on_transfer_cmd(msg, SimpleNamespace(args=t.slug), state, i18n=i18n)

    assert "не владелец" in msg.answers[0][0]
    assert state.state is None  # FSM not entered


async def test_transfer_target_without_account(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc

    _patch_sessionmaker(monkeypatch, oc, session)
    t, _bot, _owner, _cust = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)
    before_owner = t.primary_owner_account_id

    state = FakeState()
    msg1 = FakeMessage(from_user_id=OWNER_TG)
    await oc.on_transfer_cmd(msg1, SimpleNamespace(args=t.slug), state, i18n=i18n)

    # 999 has no account in T
    msg2 = FakeMessage(from_user_id=OWNER_TG, text="999")
    await oc.on_transfer_target(msg2, state, i18n=i18n)

    await session.refresh(t)
    assert t.primary_owner_account_id == before_owner  # unchanged
    assert await _audit_rows(session, t.id, "tenant.transfer") == []
    # stays in state to retry
    assert state.state == oc.OwnerTransfer.awaiting_target
    assert any("аккаунт" in a[0] for a in msg2.answers)


async def test_transfer_target_non_numeric(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc

    _patch_sessionmaker(monkeypatch, oc, session)
    t, _bot, _owner, _cust = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)

    state = FakeState()
    msg1 = FakeMessage(from_user_id=OWNER_TG)
    await oc.on_transfer_cmd(msg1, SimpleNamespace(args=t.slug), state, i18n=i18n)

    msg2 = FakeMessage(from_user_id=OWNER_TG, text="not-a-number")
    await oc.on_transfer_target(msg2, state, i18n=i18n)

    assert any("числовой" in a[0] for a in msg2.answers)
    assert state.state == oc.OwnerTransfer.awaiting_target  # still awaiting


async def test_transfer_missing_args(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc

    _patch_sessionmaker(monkeypatch, oc, session)
    i18n = await build_translator(session, default_tenant.id)
    state = FakeState()
    msg = FakeMessage(from_user_id=OWNER_TG)
    await oc.on_transfer_cmd(msg, SimpleNamespace(args=""), state, i18n=i18n)

    assert "Использование" in msg.answers[0][0]
    assert state.state is None


async def test_transfer_cancel(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc

    _patch_sessionmaker(monkeypatch, oc, session)
    i18n = await build_translator(session, default_tenant.id)
    state = FakeState({"tenant_id": 1, "actor_id": 2})
    state.state = oc.OwnerTransfer.awaiting_target
    msg = FakeMessage(from_user_id=OWNER_TG)
    await oc.on_transfer_cancel(msg, state, i18n=i18n)

    assert state.state is None
    assert await state.get_data() == {}
    assert "Отменено" in msg.answers[0][0]


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


async def test_admin_cannot_delete_tenant(session, monkeypatch):
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t, _bot, _owner, _cust = await _seed_owner_tenant(session)
    await _seed_account(session, tenant=t, tg=ADMIN_TG, role="admin")
    i18n = await build_translator(session, t.id)
    state = FakeState()

    q = FakeCallbackQuery(from_user_id=ADMIN_TG)
    await oc.on_manage_delete(q, OwnerManageCb(action="delete", tenant_id=t.id), state, i18n=i18n)

    await session.refresh(t)
    assert t.status == "active"  # unchanged
    assert state.state is None  # FSM not entered
    assert q.answers and q.answers[-1][0] == "Нет прав"
    assert q.answers[-1][1].get("show_alert") is True


async def test_delete_reauthorizes_at_apply_time(session, monkeypatch):
    """If the owner's role is revoked after tapping Delete but before typing the
    slug, on_delete_confirm must refuse: reply no-rights, clear state, no archive."""
    from quantuum.bot.handlers import owner_console as oc
    from quantuum.bot.ui.callbacks import OwnerManageCb

    _patch_sessionmaker(monkeypatch, oc, session)
    t, _bot, owner, _cust = await _seed_owner_tenant(session)
    i18n = await build_translator(session, t.id)
    state = FakeState()

    # step 1: tap Delete → state set
    q = FakeCallbackQuery(from_user_id=OWNER_TG)
    await oc.on_manage_delete(q, OwnerManageCb(action="delete", tenant_id=t.id), state, i18n=i18n)
    assert state.state == oc.OwnerDelete.awaiting_confirm

    # revoke the owner's role before the confirm step
    result = await session.execute(
        select(TenantRole).where(
            TenantRole.tenant_id == t.id,
            TenantRole.account_id == owner.id,
            TenantRole.role == "owner",
        )
    )
    await session.delete(result.scalar_one())
    await session.commit()

    # step 2: type the CORRECT slug — must still be refused (role gone)
    msg = FakeMessage(from_user_id=OWNER_TG, text=t.slug)
    await oc.on_delete_confirm(msg, state, i18n=i18n)

    await session.refresh(t)
    assert t.status == "active"  # NOT archived
    assert await _audit_rows(session, t.id, "tenant.delete") == []
    assert state.state is None  # cleared
