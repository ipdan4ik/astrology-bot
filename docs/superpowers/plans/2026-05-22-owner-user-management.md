# Owner User Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a tenant owner/admin manage their own bot's customers from the Telegram owner console — list users (paginated), adjust credits, and ban/unban with a reason — with HTTP parity and real ban enforcement.

**Architecture:** A new `domain/accounts.py` helper set is the single source of truth (used by the bot, the HTTP API, and tests). A new master-bot handler `bot/handlers/owner_users.py` drives the Telegram flow via a new `OwnerUserCb` callback, reached from a 👥 button on the existing `/manage` tenant card. Bans are `Account.status="disabled"` + a new `ban_reason` column, enforced in the customer bot's `AccountMiddleware`. New HTTP ban/unban endpoints mirror the bot. ~27 new i18n keys ship in all 10 languages.

**Tech Stack:** Python 3.12, aiogram 3 (Router, CallbackData, FSM, InlineKeyboardBuilder), FastAPI, SQLModel/asyncpg/PostgreSQL, alembic, pytest + pytest-asyncio. Test DB at `172.30.0.2`, Redis at `172.30.0.3` (already up).

**Conventions (read before starting):**
- Branch: `feat/owner-user-management` (already created).
- Test DB/Redis are live at `172.30.0.2`/`.3`; never add DB workarounds or skip-if-no-DB guards.
- The test schema is built from `SQLModel.metadata` (conftest.py), not migrations — a model change is exercised by tests immediately; the alembic migration is the production path and is reviewed by hand.
- Domain helpers `flush()` and let the caller `commit()` (matches `record_audit`, `set_tenant_status`).
- Run only the task's targeted tests during the task; the final task runs the full suite + ruff.
- Run tests from the repo root with `pytest`.

---

### Task 1: `Account.ban_reason` column + migration

**Files:**
- Modify: `src/quantuum/db/models.py:88-97` (Account model)
- Create: `alembic/versions/a7b8c9d0e1f2_account_ban_reason.py`
- Test: `tests/test_account_ban_model.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_account_ban_model.py`:

```python
from sqlmodel import select

from quantuum.db.models import Account


async def test_account_has_ban_reason_column(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id, status="disabled", ban_reason="spam")
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    row = (await session.execute(select(Account).where(Account.id == acc.id))).scalar_one()
    assert row.status == "disabled"
    assert row.ban_reason == "spam"


async def test_account_ban_reason_defaults_none(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    assert acc.status == "active"
    assert acc.ban_reason is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_account_ban_model.py -v`
Expected: FAIL with `TypeError: 'ban_reason' is an invalid keyword argument for Account` (or AttributeError).

- [ ] **Step 3: Add the column to the model**

In `src/quantuum/db/models.py`, add `ban_reason` right after `status` in `Account`:

```python
class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, foreign_key="tenants.id", index=True)
    is_superadmin: bool = False
    status: str = "active"  # active|disabled
    ban_reason: str | None = None
    preferred_lang: str | None = None
    last_seen_at: datetime | None = _dt_field(default=None)
    created_at: datetime = _dt_field(default_factory=utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_account_ban_model.py -v`
Expected: PASS (the session-scoped schema is built from metadata, so the column exists).

- [ ] **Step 5: Write the alembic migration (production path)**

Create `alembic/versions/a7b8c9d0e1f2_account_ban_reason.py`:

```python
"""account ban_reason column

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-22 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("ban_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("accounts", "ban_reason")
```

- [ ] **Step 6: Verify the migration is the single head**

Run: `python -m alembic heads`
Expected: exactly one head, `a7b8c9d0e1f2 (head)`.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/db/models.py alembic/versions/a7b8c9d0e1f2_account_ban_reason.py tests/test_account_ban_model.py
git commit -m "feat(accounts): add ban_reason column + migration"
```

---

### Task 2: Domain — credit adjust, ban/unban, staff guard

**Files:**
- Modify: `src/quantuum/domain/accounts.py` (append functions)
- Test: `tests/test_accounts_admin_domain.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_accounts_admin_domain.py`:

```python
from quantuum.db.models import Account, AccountBalance
from quantuum.domain.accounts import (
    adjust_package_credits,
    clear_account_ban,
    is_tenant_staff,
    set_account_ban,
)
from quantuum.domain.tenants import grant_role


async def _make_account(session, tenant_id):
    acc = Account(tenant_id=tenant_id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    return acc


async def test_adjust_creates_balance_and_adds(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    new_balance = await adjust_package_credits(session, acc.id, 5)
    await session.commit()
    assert new_balance == 5
    bal = await session.get(AccountBalance, acc.id)
    assert bal.package_credits == 5


async def test_adjust_deducts_and_clamps_at_zero(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await adjust_package_credits(session, acc.id, 3)
    clamped = await adjust_package_credits(session, acc.id, -10)
    await session.commit()
    assert clamped == 0


async def test_set_and_clear_ban(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await set_account_ban(session, acc.id, reason="abuse")
    await session.commit()
    await session.refresh(acc)
    assert acc.status == "disabled" and acc.ban_reason == "abuse"

    await clear_account_ban(session, acc.id)
    await session.commit()
    await session.refresh(acc)
    assert acc.status == "active" and acc.ban_reason is None


async def test_is_tenant_staff(session, default_tenant):
    owner = await _make_account(session, default_tenant.id)
    customer = await _make_account(session, default_tenant.id)
    await grant_role(session, tenant_id=default_tenant.id, account_id=owner.id, role="owner")
    await session.commit()
    assert await is_tenant_staff(session, tenant_id=default_tenant.id, account_id=owner.id) is True
    assert await is_tenant_staff(session, tenant_id=default_tenant.id, account_id=customer.id) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_accounts_admin_domain.py -v`
Expected: FAIL with `ImportError: cannot import name 'adjust_package_credits'`.

- [ ] **Step 3: Implement the functions**

Append to `src/quantuum/domain/accounts.py` (the file currently imports `utcnow` and `from quantuum.db.models import Account, AccountIdentity`). Update the model import and add the new functions:

```python
from quantuum.db.models import Account, AccountBalance, AccountIdentity
from quantuum.domain.tenants import account_has_role


async def adjust_package_credits(session, account_id: int, delta: int) -> int:
    """Add (or, for negative delta, deduct) package credits, clamped at zero.

    Creates the AccountBalance row if missing. Flushes; caller commits.
    Returns the new package_credits balance.
    """
    bal = await session.get(AccountBalance, account_id)
    if bal is None:
        bal = AccountBalance(account_id=account_id)
        session.add(bal)
        await session.flush()
    bal.package_credits = max(0, bal.package_credits + delta)
    bal.updated_at = utcnow()
    session.add(bal)
    await session.flush()
    return bal.package_credits


async def set_account_ban(session, account_id: int, *, reason: str) -> None:
    """Disable an account and record the ban reason. Flushes; caller commits."""
    acc = await session.get(Account, account_id)
    if acc is not None:
        acc.status = "disabled"
        acc.ban_reason = reason
        session.add(acc)
        await session.flush()


async def clear_account_ban(session, account_id: int) -> None:
    """Re-enable an account and clear the ban reason. Flushes; caller commits."""
    acc = await session.get(Account, account_id)
    if acc is not None:
        acc.status = "active"
        acc.ban_reason = None
        session.add(acc)
        await session.flush()


async def is_tenant_staff(session, *, tenant_id: int, account_id: int) -> bool:
    """True if the account holds owner or admin in the tenant (protects staff/self)."""
    return await account_has_role(
        session, tenant_id=tenant_id, account_id=account_id, role="owner"
    ) or await account_has_role(
        session, tenant_id=tenant_id, account_id=account_id, role="admin"
    )
```

Note: `domain.tenants` imports only `db.models` + `settings`, so importing it from `domain.accounts` introduces no import cycle.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_accounts_admin_domain.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/accounts.py tests/test_accounts_admin_domain.py
git commit -m "feat(accounts): credit-adjust, ban/unban, staff-guard domain helpers"
```

---

### Task 3: Domain — list / count / card

**Files:**
- Modify: `src/quantuum/domain/accounts.py` (add dataclasses + 3 functions)
- Test: `tests/test_accounts_admin_domain.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_accounts_admin_domain.py`:

```python
from datetime import date, time
from decimal import Decimal

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.domain.accounts import (
    count_tenant_customers,
    get_customer_card,
    list_tenant_customers,
)
from quantuum.domain.natal_profiles import upsert_natal_profile


async def test_list_and_count_with_pagination(session, default_tenant):
    for i in range(3):
        await find_or_create_account_by_tg(
            session, tenant_id=default_tenant.id, tg_user_id=str(1000 + i)
        )
    assert await count_tenant_customers(session, default_tenant.id) == 3

    page = await list_tenant_customers(session, default_tenant.id, limit=2, offset=0)
    assert len(page) == 2
    assert page[0].tg_user_id == "1000"
    assert page[0].package_credits == 0
    assert page[0].full_name is None

    page2 = await list_tenant_customers(session, default_tenant.id, limit=2, offset=2)
    assert len(page2) == 1


async def test_card_maps_name_credits_and_ban(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="2000"
    )
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="Anna",
        birth_date=date(1980, 6, 24), birth_time=time(10, 0), birth_place="Moscow",
        latitude=Decimal("55.7558"), longitude=Decimal("37.6173"), timezone="Europe/Moscow",
    )
    await adjust_package_credits(session, acc.id, 7)
    await set_account_ban(session, acc.id, reason="spam")
    await session.commit()

    card = await get_customer_card(session, default_tenant.id, acc.id)
    assert card.full_name == "Anna"
    assert card.tg_user_id == "2000"
    assert card.package_credits == 7
    assert card.status == "disabled"
    assert card.ban_reason == "spam"


async def test_card_none_for_wrong_tenant(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="2001"
    )
    await session.commit()
    assert await get_customer_card(session, 999999, acc.id) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_accounts_admin_domain.py -k "list_and_count or card" -v`
Expected: FAIL with `ImportError: cannot import name 'list_tenant_customers'`.

- [ ] **Step 3: Implement the dataclasses + functions**

At the top of `src/quantuum/domain/accounts.py` add imports and dataclasses; add `func` to the sqlalchemy/sqlmodel imports and `NatalProfile` to the models import. Add `from dataclasses import dataclass` and `from datetime import datetime`:

```python
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountBalance,
    AccountIdentity,
    NatalProfile,
)
from quantuum.domain.tenants import account_has_role


@dataclass
class CustomerRow:
    account_id: int
    full_name: str | None
    tg_user_id: str | None
    package_credits: int
    status: str


@dataclass
class CustomerCard:
    account_id: int
    full_name: str | None
    tg_user_id: str | None
    package_credits: int
    subscription_active_until: datetime | None
    free_trial_used: bool
    status: str
    ban_reason: str | None
    last_seen_at: datetime | None
```

Then add the three functions:

```python
async def count_tenant_customers(session, tenant_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(Account).where(Account.tenant_id == tenant_id)
    )
    return int(result.scalar_one())


async def list_tenant_customers(
    session, tenant_id: int, *, limit: int, offset: int
) -> list[CustomerRow]:
    """One page of a tenant's accounts, ordered by id, with name / tg id / credits.

    Left-joins so accounts without a balance, profile, or tg identity still appear.
    The provider filter sits in the JOIN ``ON`` (not WHERE) to keep those rows.
    """
    result = await session.execute(
        select(
            Account.id,
            Account.status,
            NatalProfile.full_name,
            AccountBalance.package_credits,
            AccountIdentity.provider_user_id,
        )
        .outerjoin(AccountBalance, AccountBalance.account_id == Account.id)
        .outerjoin(NatalProfile, NatalProfile.account_id == Account.id)
        .outerjoin(
            AccountIdentity,
            (AccountIdentity.account_id == Account.id)
            & (AccountIdentity.provider == "tg_chat"),
        )
        .where(Account.tenant_id == tenant_id)
        .order_by(Account.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        CustomerRow(
            account_id=row[0],
            status=row[1],
            full_name=row[2],
            package_credits=row[3] or 0,
            tg_user_id=row[4],
        )
        for row in result.all()
    ]


async def get_customer_card(
    session, tenant_id: int, account_id: int
) -> CustomerCard | None:
    acc = await session.get(Account, account_id)
    if acc is None or acc.tenant_id != tenant_id:
        return None
    bal = await session.get(AccountBalance, account_id)
    full_name = (
        await session.execute(
            select(NatalProfile.full_name).where(NatalProfile.account_id == account_id)
        )
    ).scalars().first()
    tg_user_id = (
        await session.execute(
            select(AccountIdentity.provider_user_id).where(
                AccountIdentity.account_id == account_id,
                AccountIdentity.provider == "tg_chat",
            )
        )
    ).scalars().first()
    return CustomerCard(
        account_id=acc.id,
        full_name=full_name,
        tg_user_id=tg_user_id,
        package_credits=bal.package_credits if bal is not None else 0,
        subscription_active_until=bal.subscription_active_until if bal is not None else None,
        free_trial_used=bal.free_trial_used if bal is not None else False,
        status=acc.status,
        ban_reason=acc.ban_reason,
        last_seen_at=acc.last_seen_at,
    )
```

Remove the now-duplicated old imports at the top of the file (the original `from sqlmodel import select`, `from quantuum.common.datetime import utcnow`, and `from quantuum.db.models import Account, AccountIdentity` lines) so there's a single import block — `get_tg_chat_id` and `touch_last_seen` keep working with the merged imports.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_accounts_admin_domain.py -v`
Expected: PASS (all tests, old + new).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/accounts.py tests/test_accounts_admin_domain.py
git commit -m "feat(accounts): list/count/card domain helpers for owner console"
```

---

### Task 4: i18n keys (all 10 languages)

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py` (add `ru`+`en` entries)
- Modify: `src/quantuum/i18n/translations/{es,fr,pt,it,de,tr,zh,hi}.py` (add the same keys, translated)
- Test: `tests/test_i18n_translations.py` (already enforces coverage/parity — no edit needed)

These are the **27 canonical keys** with their `ru`+`en` source (the source of truth for translation). Placeholders shown in `{}` must be copied verbatim into every language; emoji must be preserved.

- [ ] **Step 1: Add `ru`+`en` entries to `BASE_STRINGS`**

In `src/quantuum/i18n/seed_strings.py`, add these entries inside the `BASE_STRINGS` dict (before the closing `}` that precedes the translation-merge block at the bottom):

```python
    # -------------------------------------------------------------------------
    # Owner console — user management (list / credits / ban)
    # -------------------------------------------------------------------------
    "owner.manage.kb.users": {"ru": "👥 Пользователи", "en": "👥 Users"},
    "owner.users.header": {
        "ru": "Пользователи бота {display_name}:",
        "en": "Users of {display_name}:",
    },
    "owner.users.empty": {"ru": "Пока нет пользователей.", "en": "No users yet."},
    "owner.users.row": {"ru": "{name} · {credits}💎", "en": "{name} · {credits}💎"},
    "owner.users.unnamed": {"ru": "пользователь #{id}", "en": "user #{id}"},
    "owner.users.nav.prev": {"ru": "◀️", "en": "◀️"},
    "owner.users.nav.next": {"ru": "▶️", "en": "▶️"},
    "owner.user.card": {
        "ru": (
            "👤 {name}\nTelegram ID: {tg_id}\nКредиты: {credits}💎\n"
            "Подписка: {subscription}\nСтатус: {status}"
        ),
        "en": (
            "👤 {name}\nTelegram ID: {tg_id}\nCredits: {credits}💎\n"
            "Subscription: {subscription}\nStatus: {status}"
        ),
    },
    "owner.user.card.banned": {
        "ru": "🚫 Забанен. Причина: {reason}",
        "en": "🚫 Banned. Reason: {reason}",
    },
    "owner.user.status.active": {"ru": "активен", "en": "active"},
    "owner.user.status.banned": {"ru": "забанен", "en": "banned"},
    "owner.user.not_found": {"ru": "Пользователь не найден.", "en": "User not found."},
    "owner.user.kb.grant": {"ru": "💎 Изменить кредиты", "en": "💎 Adjust credits"},
    "owner.user.kb.ban": {"ru": "🚫 Забанить", "en": "🚫 Ban"},
    "owner.user.kb.unban": {"ru": "✅ Разбанить", "en": "✅ Unban"},
    "owner.user.kb.back": {"ru": "⬅️ К списку", "en": "⬅️ To list"},
    "owner.user.grant.prompt": {
        "ru": "Введите число кредитов (можно отрицательное, напр. -3):",
        "en": "Enter the number of credits (can be negative, e.g. -3):",
    },
    "owner.user.grant.invalid": {
        "ru": "Не понял. Введите целое число, напр. 5 или -2.",
        "en": "I didn't get that. Enter a whole number, e.g. 5 or -2.",
    },
    "owner.user.grant.done": {
        "ru": "Готово. Новый баланс: {credits}💎.",
        "en": "Done. New balance: {credits}💎.",
    },
    "owner.user.ban.prompt": {"ru": "Укажите причину бана:", "en": "Enter the ban reason:"},
    "owner.user.ban.invalid": {
        "ru": "Причина не может быть пустой. Укажите причину:",
        "en": "The reason can't be empty. Enter a reason:",
    },
    "owner.user.ban.done": {"ru": "Пользователь забанен.", "en": "User banned."},
    "owner.user.ban.staff_blocked": {
        "ru": "Нельзя забанить владельца или администратора.",
        "en": "You can't ban an owner or admin.",
    },
    "owner.user.unban.done": {"ru": "Пользователь разбанен.", "en": "User unbanned."},
    "owner.user.cancelled": {"ru": "Отменено.", "en": "Cancelled."},
    "account.banned.notice": {
        "ru": "🚫 Доступ к боту ограничен. Причина: {reason}",
        "en": "🚫 Your access to the bot is restricted. Reason: {reason}",
    },
```

- [ ] **Step 2: Run the i18n tests to confirm they now FAIL on coverage**

Run: `pytest tests/test_i18n_translations.py -v`
Expected: FAIL — `test_translation_files_cover_all_keys` and `test_every_key_has_all_platform_langs` report the 27 new keys missing from `es/fr/pt/it/de/tr/zh/hi`.

- [ ] **Step 3: Add the 27 keys to every translation file (per-language)**

For each of `es, fr, pt, it, de, tr, zh, hi`, append the 27 keys to that file's `TRANSLATIONS` dict, translating the **English** values above naturally for that language. **Hard rules:** copy every `{placeholder}` and emoji verbatim; keep the keys byte-identical; do not translate placeholder names. (When executing via subagent-driven-development, dispatch one Sonnet translation subagent per language — write-only, no imports/pytest/commit — exactly as the multilanguage feature did.)

Worked example — append this to `src/quantuum/i18n/translations/es.py`:

```python
    # Owner console — user management
    "owner.manage.kb.users": "👥 Usuarios",
    "owner.users.header": "Usuarios de {display_name}:",
    "owner.users.empty": "Aún no hay usuarios.",
    "owner.users.row": "{name} · {credits}💎",
    "owner.users.unnamed": "usuario #{id}",
    "owner.users.nav.prev": "◀️",
    "owner.users.nav.next": "▶️",
    "owner.user.card": (
        "👤 {name}\nTelegram ID: {tg_id}\nCréditos: {credits}💎\n"
        "Suscripción: {subscription}\nEstado: {status}"
    ),
    "owner.user.card.banned": "🚫 Baneado. Motivo: {reason}",
    "owner.user.status.active": "activo",
    "owner.user.status.banned": "baneado",
    "owner.user.not_found": "Usuario no encontrado.",
    "owner.user.kb.grant": "💎 Ajustar créditos",
    "owner.user.kb.ban": "🚫 Banear",
    "owner.user.kb.unban": "✅ Desbanear",
    "owner.user.kb.back": "⬅️ A la lista",
    "owner.user.grant.prompt": "Introduce el número de créditos (puede ser negativo, p. ej. -3):",
    "owner.user.grant.invalid": "No lo entendí. Introduce un número entero, p. ej. 5 o -2.",
    "owner.user.grant.done": "Hecho. Nuevo saldo: {credits}💎.",
    "owner.user.ban.prompt": "Indica el motivo del baneo:",
    "owner.user.ban.invalid": "El motivo no puede estar vacío. Indica un motivo:",
    "owner.user.ban.done": "Usuario baneado.",
    "owner.user.ban.staff_blocked": "No puedes banear a un propietario o administrador.",
    "owner.user.unban.done": "Usuario desbaneado.",
    "owner.user.cancelled": "Cancelado.",
    "account.banned.notice": "🚫 Tu acceso al bot está restringido. Motivo: {reason}",
```

Produce the equivalent block for `fr, pt, it, de, tr, zh, hi` — same 27 keys, values translated from the English source, placeholders/emoji verbatim.

- [ ] **Step 4: Run the i18n tests to verify they pass**

Run: `pytest tests/test_i18n_translations.py tests/test_i18n_seed.py -v`
Expected: PASS — coverage, placeholder parity, and all-10-langs completeness all green.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/i18n/seed_strings.py src/quantuum/i18n/translations/
git commit -m "feat(i18n): owner user-management strings in all 10 languages"
```

---

### Task 5: Bot — `OwnerUserCb`, list + card handlers, router registration, 👥 button

**Files:**
- Modify: `src/quantuum/bot/ui/callbacks.py` (add `OwnerUserCb`)
- Create: `src/quantuum/bot/handlers/owner_users.py` (list + card; FSM/grant/ban added in Tasks 6–7)
- Modify: `src/quantuum/bot/master_app.py:16-20` (register router)
- Modify: `src/quantuum/bot/handlers/owner_console.py:60-66` (add 👥 button)
- Test: `tests/test_owner_users_handlers.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_owner_users_handlers.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import OwnerUserCb
from quantuum.db.models import Account, AccountIdentity
from quantuum.domain.accounts import set_account_ban
from quantuum.domain.tenants import grant_role

from .conftest import build_translator

TG = 222


class FakeMessage:
    def __init__(self, *, from_user_id=TG, text=""):
        self.text = text
        self.from_user = SimpleNamespace(id=from_user_id)
        self.answers = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup))


class FakeCallbackQuery:
    def __init__(self, *, from_user_id=TG):
        self.from_user = SimpleNamespace(id=from_user_id)
        self.message = FakeMessage(from_user_id=from_user_id)
        self.answers = []  # (text, show_alert)

    async def answer(self, text="", show_alert=False, **kwargs):
        self.answers.append((text, show_alert))


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


async def _owner(session, tenant):
    acc = Account(tenant_id=tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    session.add(AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=str(TG)))
    await session.commit()
    await grant_role(session, tenant_id=tenant.id, account_id=acc.id, role="owner")
    await session.commit()
    return acc


async def test_list_renders_rows(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    await _owner(session, default_tenant)
    await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1000")
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)

    query = FakeCallbackQuery()
    await ou.on_users_list(query, OwnerUserCb(action="list", tenant_id=default_tenant.id, page=0), i18n)

    header, markup = query.message.answers[0]
    assert "Quantuum" in header
    opens = [b for b in _inline(markup) if OwnerUserCb.unpack(b.callback_data).action == "open"]
    assert len(opens) >= 2  # owner + customer accounts


async def test_list_unauthorized(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    i18n = await build_translator(session, default_tenant.id)
    query = FakeCallbackQuery(from_user_id=999)  # no role
    await ou.on_users_list(query, OwnerUserCb(action="list", tenant_id=default_tenant.id, page=0), i18n)
    assert query.answers and query.answers[-1][1] is True  # show_alert no_rights
    assert query.message.answers == []


async def test_open_renders_card_with_ban(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    await _owner(session, default_tenant)
    target = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1000")
    await set_account_ban(session, target.id, reason="spam")
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)

    query = FakeCallbackQuery()
    await ou.on_user_open(query, OwnerUserCb(action="open", tenant_id=default_tenant.id, account_id=target.id), i18n)
    text, markup = query.message.answers[0]
    assert "Telegram ID: 1000" in text
    assert "spam" in text
    labels = {b.text for b in _inline(markup)}
    assert "✅ Разбанить" in labels  # unban offered for a banned user


async def test_open_not_found(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    await _owner(session, default_tenant)
    i18n = await build_translator(session, default_tenant.id)
    query = FakeCallbackQuery()
    await ou.on_user_open(query, OwnerUserCb(action="open", tenant_id=default_tenant.id, account_id=987654), i18n)
    assert query.answers[-1][1] is True  # not_found alert
    assert query.message.answers == []
```

(The handler keeps a defensive `owner.users.empty` branch, but it is unreachable for an authorized owner — the owner is always an account in their own tenant, so the count is never zero — so there is no handler test for it. The empty path is covered at the domain level by `count_tenant_customers` in Task 3.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_owner_users_handlers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.bot.handlers.owner_users'` (and `ImportError` for `OwnerUserCb`).

- [ ] **Step 3: Add the callback**

In `src/quantuum/bot/ui/callbacks.py`, add at the end:

```python
class OwnerUserCb(CallbackData, prefix="ousr"):
    action: str  # list | open | grant | ban | unban
    tenant_id: int = 0
    account_id: int = 0
    page: int = 0
```

- [ ] **Step 4: Create the handler (list + card)**

Create `src/quantuum/bot/handlers/owner_users.py`:

```python
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.ui.callbacks import OwnerUserCb
from quantuum.db.models import Tenant
from quantuum.db.session import get_sessionmaker
from quantuum.domain.accounts import (
    CustomerCard,
    count_tenant_customers,
    get_customer_card,
    list_tenant_customers,
)
from quantuum.domain.owner_console import authorize_tenant_action
from quantuum.i18n import Translator

router = Router()
PAGE_SIZE = 8


@router.callback_query(OwnerUserCb.filter(F.action == "list"))
async def on_users_list(
    query: CallbackQuery, callback_data: OwnerUserCb, i18n: Translator
) -> None:
    tenant_id = callback_data.tenant_id
    page = callback_data.page
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(query.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        tenant = await session.get(Tenant, tenant_id)
        total = await count_tenant_customers(session, tenant_id)
        rows = await list_tenant_customers(
            session, tenant_id, limit=PAGE_SIZE, offset=page * PAGE_SIZE
        )
    if total == 0:
        await query.message.answer(await i18n("owner.users.empty"))
        await query.answer()
        return
    builder = InlineKeyboardBuilder()
    for row in rows:
        name = row.full_name or await i18n("owner.users.unnamed", id=row.account_id)
        label = await i18n("owner.users.row", name=name, credits=row.package_credits)
        if row.status == "disabled":
            label += " 🚫"
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=OwnerUserCb(
                    action="open", tenant_id=tenant_id, account_id=row.account_id
                ).pack(),
            )
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text=await i18n("owner.users.nav.prev"),
                callback_data=OwnerUserCb(action="list", tenant_id=tenant_id, page=page - 1).pack(),
            )
        )
    if (page + 1) * PAGE_SIZE < total:
        nav.append(
            InlineKeyboardButton(
                text=await i18n("owner.users.nav.next"),
                callback_data=OwnerUserCb(action="list", tenant_id=tenant_id, page=page + 1).pack(),
            )
        )
    if nav:
        builder.row(*nav)
    display_name = tenant.display_name if tenant is not None else ""
    await query.message.answer(
        await i18n("owner.users.header", display_name=display_name),
        reply_markup=builder.as_markup(),
    )
    await query.answer()


async def _card_text(card: CustomerCard, i18n: Translator) -> str:
    name = card.full_name or await i18n("owner.users.unnamed", id=card.account_id)
    subscription = (
        card.subscription_active_until.strftime("%Y-%m-%d")
        if card.subscription_active_until is not None
        else "—"
    )
    status = await i18n(
        "owner.user.status.banned" if card.status == "disabled" else "owner.user.status.active"
    )
    text = await i18n(
        "owner.user.card",
        name=name,
        tg_id=card.tg_user_id or "—",
        credits=card.package_credits,
        subscription=subscription,
        status=status,
    )
    if card.status == "disabled":
        text += "\n" + await i18n("owner.user.card.banned", reason=card.ban_reason or "—")
    return text


async def _card_markup(card: CustomerCard, tenant_id: int, i18n: Translator):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.user.kb.grant"),
            callback_data=OwnerUserCb(action="grant", tenant_id=tenant_id, account_id=card.account_id).pack(),
        )
    )
    if card.status == "disabled":
        builder.row(
            InlineKeyboardButton(
                text=await i18n("owner.user.kb.unban"),
                callback_data=OwnerUserCb(action="unban", tenant_id=tenant_id, account_id=card.account_id).pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=await i18n("owner.user.kb.ban"),
                callback_data=OwnerUserCb(action="ban", tenant_id=tenant_id, account_id=card.account_id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.user.kb.back"),
            callback_data=OwnerUserCb(action="list", tenant_id=tenant_id, page=0).pack(),
        )
    )
    return builder.as_markup()


@router.callback_query(OwnerUserCb.filter(F.action == "open"))
async def on_user_open(
    query: CallbackQuery, callback_data: OwnerUserCb, i18n: Translator
) -> None:
    tenant_id = callback_data.tenant_id
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(query.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        card = await get_customer_card(session, tenant_id, callback_data.account_id)
    if card is None:
        await query.answer(await i18n("owner.user.not_found"), show_alert=True)
        return
    await query.message.answer(
        await _card_text(card, i18n),
        reply_markup=await _card_markup(card, tenant_id, i18n),
    )
    await query.answer()
```

- [ ] **Step 5: Register the router in the master bot**

In `src/quantuum/bot/master_app.py`, import and include `owner_users`:

```python
    from quantuum.bot.handlers import (
        master_onboarding,
        master_superadmin,
        owner_console,
        owner_users,
    )

    dp.include_router(master_onboarding.router)
    dp.include_router(owner_console.router)
    dp.include_router(owner_users.router)
    dp.include_router(master_superadmin.router)
```

- [ ] **Step 6: Add the 👥 button to the `/manage` card**

In `src/quantuum/bot/handlers/owner_console.py`, import the callback (extend the existing import line):

```python
from quantuum.bot.ui.callbacks import OwnerManageCb, OwnerUserCb
```

In `on_manage`, add a Users button right after the Stats button (after the `builder.row(... action="stats" ...)` block, before the pause/resume block):

```python
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.manage.kb.users"),
            callback_data=OwnerUserCb(action="list", tenant_id=tenant.id, page=0).pack(),
        )
    )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_owner_users_handlers.py tests/test_owner_console_handlers.py -v`
Expected: PASS (new handler tests + existing owner-console tests still green).

- [ ] **Step 8: Commit**

```bash
git add src/quantuum/bot/ui/callbacks.py src/quantuum/bot/handlers/owner_users.py src/quantuum/bot/master_app.py src/quantuum/bot/handlers/owner_console.py tests/test_owner_users_handlers.py
git commit -m "feat(bot): owner user list + card console (👥 Users)"
```

---

### Task 6: Bot — grant-credits FSM

**Files:**
- Modify: `src/quantuum/bot/handlers/owner_users.py` (FSM states + grant handlers)
- Test: `tests/test_owner_users_handlers.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_owner_users_handlers.py`:

```python
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from quantuum.db.models import AccountBalance


def _fsm():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def test_grant_adds_credits(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    await _owner(session, default_tenant)
    target = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1000")
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)
    state = _fsm()

    query = FakeCallbackQuery()
    await ou.on_user_grant_start(query, OwnerUserCb(action="grant", tenant_id=default_tenant.id, account_id=target.id), state, i18n)
    assert (await state.get_data())["account_id"] == target.id

    msg = FakeMessage(text="5")
    await ou.on_user_grant_amount(msg, state, i18n)
    bal = await session.get(AccountBalance, target.id)
    assert bal.package_credits == 5
    assert await state.get_state() is None


async def test_grant_deduct_clamps(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    await _owner(session, default_tenant)
    target = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1000")
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)
    state = _fsm()
    await state.update_data(tenant_id=default_tenant.id, account_id=target.id)
    await state.set_state(ou.OwnerUserAdmin.awaiting_credit_amount)

    await ou.on_user_grant_amount(FakeMessage(text="-3"), state, i18n)
    bal = await session.get(AccountBalance, target.id)
    assert bal.package_credits == 0


async def test_grant_invalid_stays_in_state(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    await _owner(session, default_tenant)
    target = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1000")
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)
    state = _fsm()
    await state.update_data(tenant_id=default_tenant.id, account_id=target.id)
    await state.set_state(ou.OwnerUserAdmin.awaiting_credit_amount)

    msg = FakeMessage(text="abc")
    await ou.on_user_grant_amount(msg, state, i18n)
    assert "число" in msg.answers[0][0] or "number" in msg.answers[0][0]
    assert await state.get_state() == ou.OwnerUserAdmin.awaiting_credit_amount.state
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_owner_users_handlers.py -k grant -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'on_user_grant_start'`.

- [ ] **Step 3: Implement the grant FSM**

In `src/quantuum/bot/handlers/owner_users.py`, extend the imports and add the FSM + handlers:

```python
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from quantuum.domain.accounts import adjust_package_credits, get_customer_card
from quantuum.domain.audit import record_audit


class OwnerUserAdmin(StatesGroup):
    awaiting_credit_amount = State()
    awaiting_ban_reason = State()


@router.callback_query(OwnerUserCb.filter(F.action == "grant"))
async def on_user_grant_start(
    query: CallbackQuery, callback_data: OwnerUserCb, state: FSMContext, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(query.from_user.id), tenant_id=callback_data.tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
    await state.set_state(OwnerUserAdmin.awaiting_credit_amount)
    await state.update_data(tenant_id=callback_data.tenant_id, account_id=callback_data.account_id)
    await query.message.answer(await i18n("owner.user.grant.prompt"))
    await query.answer()


@router.message(Command("cancel"), OwnerUserAdmin.awaiting_credit_amount)
async def on_grant_cancel(message: Message, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await message.answer(await i18n("owner.user.cancelled"))


@router.message(OwnerUserAdmin.awaiting_credit_amount)
async def on_user_grant_amount(message: Message, state: FSMContext, i18n: Translator) -> None:
    try:
        delta = int((message.text or "").strip())
    except ValueError:
        await message.answer(await i18n("owner.user.grant.invalid"))
        return
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    account_id = data["account_id"]
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await message.answer(await i18n("owner.no_rights"))
            await state.clear()
            return
        card = await get_customer_card(session, tenant_id, account_id)
        if card is None:
            await message.answer(await i18n("owner.user.not_found"))
            await state.clear()
            return
        before = card.package_credits
        after = await adjust_package_credits(session, account_id, delta)
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_account_id=actor,
            action="account.credits_adjust",
            entity_type="account",
            entity_id=account_id,
            payload={"delta": delta, "before": before, "after": after},
        )
        await session.commit()
    await state.clear()
    await message.answer(await i18n("owner.user.grant.done", credits=after))
```

(Merge the new imports into the existing import block — `CallbackQuery`, `InlineKeyboardButton`, `Message` all come from `aiogram.types`; `get_customer_card` is already imported in Task 5, so don't double-import it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_owner_users_handlers.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/owner_users.py tests/test_owner_users_handlers.py
git commit -m "feat(bot): grant/deduct credits FSM in owner user console"
```

---

### Task 7: Bot — ban / unban FSM (with staff guard)

**Files:**
- Modify: `src/quantuum/bot/handlers/owner_users.py` (ban/unban handlers)
- Test: `tests/test_owner_users_handlers.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_owner_users_handlers.py`:

```python
async def test_ban_stores_reason_and_disables(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    await _owner(session, default_tenant)
    target = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1000")
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)
    state = _fsm()

    query = FakeCallbackQuery()
    await ou.on_user_ban_start(query, OwnerUserCb(action="ban", tenant_id=default_tenant.id, account_id=target.id), state, i18n)
    assert await state.get_state() == ou.OwnerUserAdmin.awaiting_ban_reason.state

    await ou.on_user_ban_reason(FakeMessage(text="spamming"), state, i18n)
    row = await session.get(Account, target.id)
    await session.refresh(row)
    assert row.status == "disabled" and row.ban_reason == "spamming"
    assert await state.get_state() is None


async def test_ban_blocked_for_staff(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    owner = await _owner(session, default_tenant)
    i18n = await build_translator(session, default_tenant.id)
    state = _fsm()

    query = FakeCallbackQuery()
    await ou.on_user_ban_start(query, OwnerUserCb(action="ban", tenant_id=default_tenant.id, account_id=owner.id), state, i18n)
    assert query.answers[-1][1] is True  # staff_blocked alert
    assert await state.get_state() is None


async def test_unban_clears(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import owner_users as ou

    _patch_sessionmaker(monkeypatch, ou, session)
    await _owner(session, default_tenant)
    target = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1000")
    await set_account_ban(session, target.id, reason="x")
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)

    query = FakeCallbackQuery()
    await ou.on_user_unban(query, OwnerUserCb(action="unban", tenant_id=default_tenant.id, account_id=target.id), i18n)
    row = await session.get(Account, target.id)
    await session.refresh(row)
    assert row.status == "active" and row.ban_reason is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_owner_users_handlers.py -k "ban or unban" -v`
Expected: FAIL with `AttributeError: ... has no attribute 'on_user_ban_start'`.

- [ ] **Step 3: Implement ban/unban**

In `src/quantuum/bot/handlers/owner_users.py`, add `set_account_ban, clear_account_ban, is_tenant_staff` to the `domain.accounts` import, and add the handlers:

```python
from quantuum.domain.accounts import (
    clear_account_ban,
    is_tenant_staff,
    set_account_ban,
)


@router.callback_query(OwnerUserCb.filter(F.action == "ban"))
async def on_user_ban_start(
    query: CallbackQuery, callback_data: OwnerUserCb, state: FSMContext, i18n: Translator
) -> None:
    tenant_id = callback_data.tenant_id
    account_id = callback_data.account_id
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(query.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        if await is_tenant_staff(session, tenant_id=tenant_id, account_id=account_id):
            await query.answer(await i18n("owner.user.ban.staff_blocked"), show_alert=True)
            return
    await state.set_state(OwnerUserAdmin.awaiting_ban_reason)
    await state.update_data(tenant_id=tenant_id, account_id=account_id)
    await query.message.answer(await i18n("owner.user.ban.prompt"))
    await query.answer()


@router.message(Command("cancel"), OwnerUserAdmin.awaiting_ban_reason)
async def on_ban_cancel(message: Message, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await message.answer(await i18n("owner.user.cancelled"))


@router.message(OwnerUserAdmin.awaiting_ban_reason)
async def on_user_ban_reason(message: Message, state: FSMContext, i18n: Translator) -> None:
    reason = (message.text or "").strip()
    if not reason:
        await message.answer(await i18n("owner.user.ban.invalid"))
        return
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    account_id = data["account_id"]
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await message.answer(await i18n("owner.no_rights"))
            await state.clear()
            return
        if await is_tenant_staff(session, tenant_id=tenant_id, account_id=account_id):
            await message.answer(await i18n("owner.user.ban.staff_blocked"))
            await state.clear()
            return
        await set_account_ban(session, account_id, reason=reason)
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_account_id=actor,
            action="account.ban",
            entity_type="account",
            entity_id=account_id,
            payload={"reason": reason},
        )
        await session.commit()
    await state.clear()
    await message.answer(await i18n("owner.user.ban.done"))


@router.callback_query(OwnerUserCb.filter(F.action == "unban"))
async def on_user_unban(
    query: CallbackQuery, callback_data: OwnerUserCb, i18n: Translator
) -> None:
    tenant_id = callback_data.tenant_id
    account_id = callback_data.account_id
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(query.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        await clear_account_ban(session, account_id)
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_account_id=actor,
            action="account.unban",
            entity_type="account",
            entity_id=account_id,
        )
        await session.commit()
    await query.message.answer(await i18n("owner.user.unban.done"))
    await query.answer()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_owner_users_handlers.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/owner_users.py tests/test_owner_users_handlers.py
git commit -m "feat(bot): ban/unban FSM with staff guard in owner user console"
```

---

### Task 8: Middleware — block banned accounts on the customer bot

**Files:**
- Modify: `src/quantuum/bot/middleware/account.py`
- Test: `tests/test_account_middleware_ban.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_account_middleware_ban.py`:

```python
from types import SimpleNamespace

from quantuum.auth.identity import find_or_create_account_by_tg

from .conftest import build_translator


class FakeMessage:
    def __init__(self, user_id):
        self.from_user = SimpleNamespace(id=user_id, language_code=None)
        self.chat = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


def _patch_sessionmaker(monkeypatch, session):
    from quantuum.bot.middleware import account as mw

    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(mw, "get_sessionmaker", lambda: _Maker())


async def test_disabled_account_is_blocked(session, default_tenant, monkeypatch):
    from quantuum.bot.middleware.account import AccountMiddleware

    await build_translator(session, default_tenant.id)  # seed strings + langs
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="555")
    acc.status = "disabled"
    acc.ban_reason = "spam"
    session.add(acc)
    await session.commit()
    _patch_sessionmaker(monkeypatch, session)

    called = False

    async def handler(event, data):
        nonlocal called
        called = True

    event = FakeMessage(555)
    await AccountMiddleware()(handler, event, {"tenant_id": default_tenant.id})

    assert called is False
    assert any("spam" in t for t in event.answers)


async def test_active_account_passes_through(session, default_tenant, monkeypatch):
    from quantuum.bot.middleware.account import AccountMiddleware

    await build_translator(session, default_tenant.id)
    await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="556")
    await session.commit()
    _patch_sessionmaker(monkeypatch, session)

    called = False

    async def handler(event, data):
        nonlocal called
        called = True

    event = FakeMessage(556)
    await AccountMiddleware()(handler, event, {"tenant_id": default_tenant.id})
    assert called is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_account_middleware_ban.py -v`
Expected: FAIL — `test_disabled_account_is_blocked` fails because the handler is currently called (no ban check) and no notice is sent.

- [ ] **Step 3: Add the ban check to the middleware**

In `src/quantuum/bot/middleware/account.py`, add the `CallbackQuery` import and the disabled-account short-circuit after the translator is built (inside `__call__`, after the `async with` block, before `data["account"] = account`):

```python
from aiogram.types import CallbackQuery
```

```python
        if account.status == "disabled":
            notice = await translator("account.banned.notice", reason=account.ban_reason or "—")
            if isinstance(event, CallbackQuery):
                await event.answer(notice, show_alert=True)
            else:
                answer = getattr(event, "answer", None)
                if answer is not None:
                    await answer(notice)
            return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_account_middleware_ban.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/middleware/account.py tests/test_account_middleware_ban.py
git commit -m "feat(bot): block banned accounts in AccountMiddleware"
```

---

### Task 9: HTTP — ban/unban endpoints + AccountDetailOut fields

**Files:**
- Modify: `src/quantuum/api/schemas.py:435-441` (AccountDetailOut + new `BanIn`)
- Modify: `src/quantuum/api/routes/admin_tenants.py` (helper + 2 endpoints; update `get_tenant_account`)
- Test: `tests/test_api_admin_tenants.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_admin_tenants.py`:

```python
async def _make_customer(session, tenant_id):
    acc = Account(tenant_id=tenant_id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    return acc


async def test_ban_unban_happy_path(client, owner_headers, default_tenant, session):
    target = await _make_customer(session, default_tenant.id)
    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/accounts/{target.id}/ban",
        headers=owner_headers,
        json={"reason": "abuse"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "disabled"
    assert body["ban_reason"] == "abuse"

    r2 = await client.post(
        f"/admin/tenants/{default_tenant.id}/accounts/{target.id}/unban",
        headers=owner_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "active"
    assert r2.json()["ban_reason"] is None


async def test_ban_forbidden_for_customer(client, customer_headers, default_tenant, session):
    target = await _make_customer(session, default_tenant.id)
    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/accounts/{target.id}/ban",
        headers=customer_headers,
        json={"reason": "x"},
    )
    assert r.status_code == 403


async def test_ban_staff_conflict(client, owner_headers, default_tenant, session):
    # The owner account created by owner_headers holds the owner role → cannot be banned.
    owner_acc = (
        await session.execute(select(Account).where(Account.tenant_id == default_tenant.id))
    ).scalars().first()
    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/accounts/{owner_acc.id}/ban",
        headers=owner_headers,
        json={"reason": "x"},
    )
    assert r.status_code == 409


async def test_ban_unknown_account_404(client, owner_headers, default_tenant):
    r = await client.post(
        f"/admin/tenants/{default_tenant.id}/accounts/987654/ban",
        headers=owner_headers,
        json={"reason": "x"},
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_admin_tenants.py -k "ban or unban" -v`
Expected: FAIL with 404/405 (routes don't exist) and `KeyError: 'ban_reason'`.

- [ ] **Step 3: Extend the schemas**

In `src/quantuum/api/schemas.py`, add `status` + `ban_reason` to `AccountDetailOut` and add a `BanIn` model:

```python
class AccountDetailOut(BaseModel):
    id: int
    created_at: datetime
    last_seen_at: datetime | None
    package_credits: int
    subscription_active_until: datetime | None
    free_trial_used: bool
    status: str
    ban_reason: str | None


class BanIn(BaseModel):
    reason: str
```

- [ ] **Step 4: Implement the endpoints + detail helper**

In `src/quantuum/api/routes/admin_tenants.py`:

Add to the imports — `BanIn` from `quantuum.api.schemas` and the domain helpers:

```python
from quantuum.domain.accounts import (
    clear_account_ban,
    is_tenant_staff,
    set_account_ban,
)
```

Add a shared detail builder and refactor `get_tenant_account` to use it (replace the inline `AccountDetailOut(...)` return in `get_tenant_account` with `return _account_detail_out(target, bal)`):

```python
def _account_detail_out(acc: Account, bal: AccountBalance | None) -> AccountDetailOut:
    return AccountDetailOut(
        id=acc.id,
        created_at=acc.created_at,
        last_seen_at=acc.last_seen_at,
        package_credits=bal.package_credits if bal is not None else 0,
        subscription_active_until=(
            bal.subscription_active_until if bal is not None else None
        ),
        free_trial_used=bal.free_trial_used if bal is not None else False,
        status=acc.status,
        ban_reason=acc.ban_reason,
    )
```

Add the two endpoints (next to the accounts routes):

```python
@router.post("/{tenant_id}/accounts/{account_id}/ban", response_model=AccountDetailOut)
async def ban_account(
    tenant_id: int,
    account_id: int,
    body: BanIn,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> AccountDetailOut:
    target = await session.get(Account, account_id)
    if target is None or target.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="account not found")
    if await is_tenant_staff(session, tenant_id=tenant_id, account_id=account_id):
        raise HTTPException(status_code=409, detail="cannot ban staff")
    await set_account_ban(session, account_id, reason=body.reason)
    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="account.ban",
        entity_type="account",
        entity_id=account_id,
        payload={"reason": body.reason},
    )
    await session.commit()
    await session.refresh(target)
    bal = await session.get(AccountBalance, account_id)
    return _account_detail_out(target, bal)


@router.post("/{tenant_id}/accounts/{account_id}/unban", response_model=AccountDetailOut)
async def unban_account(
    tenant_id: int,
    account_id: int,
    account: Account = Depends(require_tenant_role(("owner", "admin"))),
    session: AsyncSession = Depends(get_session),
) -> AccountDetailOut:
    target = await session.get(Account, account_id)
    if target is None or target.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="account not found")
    await clear_account_ban(session, account_id)
    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=account.id,
        action="account.unban",
        entity_type="account",
        entity_id=account_id,
    )
    await session.commit()
    await session.refresh(target)
    bal = await session.get(AccountBalance, account_id)
    return _account_detail_out(target, bal)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_api_admin_tenants.py -v`
Expected: PASS (new ban/unban tests + existing admin-tenant tests still green).

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/api/schemas.py src/quantuum/api/routes/admin_tenants.py tests/test_api_admin_tenants.py
git commit -m "feat(api): ban/unban account endpoints + status/ban_reason in detail"
```

---

### Task 10: Stage gate — full suite + lint

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest -q`
Expected: all tests pass (existing suite + the new tests from Tasks 1–9).

- [ ] **Step 2: Run ruff**

Run: `ruff check src tests`
Expected: no errors. Fix any import-order/unused-import issues introduced (e.g. the merged import blocks in `domain/accounts.py` and `owner_users.py`).

- [ ] **Step 3: Commit any lint fixes (only if needed)**

```bash
git add -u
git commit -m "chore: ruff fixes for owner user management"
```

(Do not stage `docs/other/features.html` / `docs/other/features.md` — those are the user's own uncommitted edits and must stay out of every commit.)

---

## Notes for the executor

- **Don't `git add -A`.** `docs/other/features.{html,md}` carry the user's own uncommitted edits. Stage only the files each task lists.
- **i18n quality (Task 4):** translate the English source naturally per language; copy `{placeholders}` and emoji verbatim. Dispatch one Sonnet translation subagent per language (write-only — no imports, no pytest, no commit; the controller validates with `pytest tests/test_i18n_translations.py` and commits centrally), mirroring the multilanguage feature's parallel-safe pattern.
- **Migration head:** after Task 1, `alembic heads` must show the single head `a7b8c9d0e1f2`. The test schema comes from `SQLModel.metadata`, so tests don't run the migration — its correctness is verified by hand review + `alembic heads`.
- **Deploy:** the new `accounts.ban_reason` column ships in migration `a7b8c9d0e1f2` (applied by the migration container on `up`). No backfill needed (nullable). The ban-enforcement middleware change is in the customer-bot image; the owner console + HTTP endpoints are in the master-bot / api images — recreate them (`docker compose ... up -d --build`).
```
