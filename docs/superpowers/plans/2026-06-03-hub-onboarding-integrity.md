# Hub-Bot Onboarding Integrity (Workstream C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent two tenants from claiming the same bot, stop a slow Telegram `getMe` from hanging onboarding, and consume an invite use on success (not on start) so an abandoned onboarding leaves the invite usable — while preventing one invite from spawning duplicate un-finalized tenants.

**Architecture:** Today `create_tenant_from_onboarding` (`domain/provisioning.py:23`) increments `invite.used_count` immediately and creates a provisioning `Tenant` + `TenantBot`; `finalize_provisioning` (`:92`) later activates them without checking that the bot's `bot_telegram_id` isn't already an active `TenantBot`. We (1) link a provisioning `Tenant` to its invite via a new `Tenant.invite_id` column, (2) reuse an existing provisioning tenant for the same invite instead of duplicating, (3) move the invite-use increment into `finalize_provisioning`, (4) reject finalize when the bot id is already in use (new domain error → new i18n key), and (5) wrap `getMe` calls in `asyncio.wait_for`.

**Tech Stack:** aiogram master-bot handlers, SQLAlchemy async, Alembic, pytest (`uv run pytest`). Current alembic head: `f3a4b5c6d7e8`.

**FSM context available at finalize:** the onboarding FSM carries `invite_id`, `tenant_id`, `default_lang` (see `bot/handlers/master_onboarding.py`). Finalize handlers are `on_managed_bot_created` (:198) and `on_manual_token` (:227).

**Test command:** `uv run pytest <path> -v`. asyncio auto mode (no decorator); fixtures `session`, `default_tenant`. For each task READ the existing provisioning tests first (`grep -rln "create_tenant_from_onboarding\|finalize_provisioning" tests/`) and mirror their setup helpers (building a `TenantInvite`, owner tg ids, etc.). Do NOT weaken assertions.

---

### Task 1: i18n key `master.onboard.token_in_use`

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py` (BASE_STRINGS, near the other `master.onboard.*` keys ~line 516)
- Modify: all 8 `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py`
- Test: `tests/test_i18n_token_in_use_key.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_i18n_token_in_use_key.py
from quantuum.i18n.seed_strings import BASE_STRINGS

ALL_LANGS = {"ru", "en", "de", "es", "fr", "hi", "it", "pt", "tr", "zh"}


def test_token_in_use_key_present_in_all_langs():
    assert "master.onboard.token_in_use" in BASE_STRINGS
    entry = BASE_STRINGS["master.onboard.token_in_use"]
    assert ALL_LANGS.issubset(entry.keys())
    for lang in ALL_LANGS:
        assert entry[lang].strip(), f"empty translation for {lang}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_i18n_token_in_use_key.py -v`
Expected: FAIL.

- [ ] **Step 3: Add to BASE_STRINGS**

In `src/quantuum/i18n/seed_strings.py`, near the other `master.onboard.*` entries, add:

```python
    "master.onboard.token_in_use": {
        "ru": "Этот бот уже привязан к другому проекту. Используй другого бота.",
        "en": "This bot is already linked to another project. Use a different bot.",
    },
```

- [ ] **Step 4: Add to every translation file**

`de.py`: `"master.onboard.token_in_use": "Dieser Bot ist bereits mit einem anderen Projekt verknüpft. Verwende einen anderen Bot.",`
`es.py`: `"master.onboard.token_in_use": "Este bot ya está vinculado a otro proyecto. Usa un bot diferente.",`
`fr.py`: `"master.onboard.token_in_use": "Ce bot est déjà lié à un autre projet. Utilise un autre bot.",`
`hi.py`: `"master.onboard.token_in_use": "यह बॉट पहले से किसी अन्य प्रोजेक्ट से जुड़ा है। कोई दूसरा बॉट इस्तेमाल करें।",`
`it.py`: `"master.onboard.token_in_use": "Questo bot è già collegato a un altro progetto. Usa un bot diverso.",`
`pt.py`: `"master.onboard.token_in_use": "Este bot já está vinculado a outro projeto. Use um bot diferente.",`
`tr.py`: `"master.onboard.token_in_use": "Bu bot zaten başka bir projeye bağlı. Farklı bir bot kullan.",`
`zh.py`: `"master.onboard.token_in_use": "该机器人已绑定到另一个项目。请使用其他机器人。",`

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_i18n_token_in_use_key.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/i18n/seed_strings.py src/quantuum/i18n/translations/ tests/test_i18n_token_in_use_key.py
git commit -m "feat(i18n): master.onboard.token_in_use key in all 10 languages"
```

---

### Task 2: Time-box `getMe` calls

**Files:**
- Modify: `src/quantuum/domain/provisioning.py` — add a module-level timeout constant; wrap the `get_me()` in `master_can_manage_bots` (:19) and `validate_bot_token` (:75) with `asyncio.wait_for`; move the `aiogram` imports in `validate_bot_token` to module level so tests can patch `provisioning.Bot`.
- Test: `tests/test_provisioning_getme_timeout.py` (create)

- [ ] **Step 1: Write the failing test**

`master_can_manage_bots(bot)` takes an injectable bot, so test it. A fake bot whose `get_me` never returns must cause a timeout → the function returns False (cannot confirm the capability).

```python
# tests/test_provisioning_getme_timeout.py
import asyncio

import quantuum.domain.provisioning as prov


class _HangingBot:
    async def get_me(self):
        await asyncio.sleep(5)
        return object()


async def test_master_can_manage_bots_times_out(monkeypatch):
    monkeypatch.setattr(prov, "GETME_TIMEOUT_S", 0.01)
    result = await prov.master_can_manage_bots(_HangingBot())
    assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_provisioning_getme_timeout.py -v`
Expected: FAIL — currently `master_can_manage_bots` has no timeout and no `GETME_TIMEOUT_S` attribute (AttributeError on monkeypatch), and without a timeout it would hang/await 5s.

- [ ] **Step 3: Implement**

In `src/quantuum/domain/provisioning.py`:
- Add at top: `import asyncio` and the module-level imports `from aiogram import Bot` and `from aiogram.utils.token import TokenValidationError, validate_token` (move them out of `validate_bot_token`).
- Add a constant near the top: `GETME_TIMEOUT_S = 10.0`
- `master_can_manage_bots`:
  ```python
  async def master_can_manage_bots(bot) -> bool:
      try:
          me = await asyncio.wait_for(bot.get_me(), timeout=GETME_TIMEOUT_S)
      except (asyncio.TimeoutError, Exception):
          return False
      return bool(getattr(me, "can_manage_bots", False))
  ```
  (Keep the existing docstring.)
- `validate_bot_token`: wrap the get_me call:
  ```python
  async def validate_bot_token(token: str) -> tuple[int, str] | None:
      try:
          validate_token(token)
      except TokenValidationError:
          return None
      bot = Bot(token=token)
      try:
          me = await asyncio.wait_for(bot.get_me(), timeout=GETME_TIMEOUT_S)
          return me.id, me.username
      except Exception:
          return None
      finally:
          await bot.session.close()
  ```
  (`asyncio.TimeoutError` is an `Exception`, so the broad `except Exception` already returns None on timeout.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_provisioning_getme_timeout.py -v`
Expected: PASS (returns within ~0.01s, not 5s).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/provisioning.py tests/test_provisioning_getme_timeout.py
git commit -m "fix(provisioning): time-box getMe calls to avoid hung onboarding"
```

---

### Task 3: `Tenant.invite_id` column + migration

**Files:**
- Modify: `src/quantuum/db/models.py` (Tenant model — add `invite_id`)
- Create: `alembic/versions/<new_id>_tenant_invite_id.py`
- Test: `tests/test_provisioning.py` or wherever provisioning is tested (add a tiny model test)

- [ ] **Step 1: Write the failing test**

```python
async def test_tenant_has_invite_id_column(session, default_tenant):
    from quantuum.db.models import Tenant
    t = await session.get(Tenant, default_tenant.id)
    # column exists and defaults to None
    assert hasattr(t, "invite_id")
    assert t.invite_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest <test file> -k has_invite_id_column -v`
Expected: FAIL — `AttributeError`/no such column.

- [ ] **Step 3: Add the column to the model**

In `src/quantuum/db/models.py`, in the `Tenant` model, add:

```python
    invite_id: int | None = Field(default=None, foreign_key="tenant_invites.id", index=True)
```

- [ ] **Step 4: Write the migration**

First confirm an unused revision id: `grep -rn "^revision" alembic/versions/ | grep -i <candidate>` must return nothing. Use a clearly-unused id such as `a1c2e3f405d6` (VERIFY it's unused first).

Create `alembic/versions/a1c2e3f405d6_tenant_invite_id.py`:

```python
"""tenants.invite_id link to onboarding invite

Revision ID: a1c2e3f405d6
Revises: f3a4b5c6d7e8
Create Date: 2026-06-03 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1c2e3f405d6"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("invite_id", sa.Integer(), nullable=True),
    )
    op.create_index(op.f("ix_tenants_invite_id"), "tenants", ["invite_id"], unique=False)
    op.create_foreign_key(
        "fk_tenants_invite_id", "tenants", "tenant_invites", ["invite_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_tenants_invite_id", "tenants", type_="foreignkey")
    op.drop_index(op.f("ix_tenants_invite_id"), table_name="tenants")
    op.drop_column("tenants", "invite_id")
```

- [ ] **Step 5: Run test + confirm single head**

Run: `uv run pytest <test file> -k has_invite_id_column -v` → PASS
Run: `uv run alembic heads` → single head `a1c2e3f405d6`.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/db/models.py alembic/versions/a1c2e3f405d6_tenant_invite_id.py <test file>
git commit -m "feat(db): tenants.invite_id links a provisioning tenant to its invite"
```

---

### Task 4: Consume invite on finalize, not on start; reuse provisioning tenant

**Files:**
- Modify: `src/quantuum/domain/provisioning.py` — `create_tenant_from_onboarding` (:23) and `finalize_provisioning` (:92)
- Test: `tests/test_provisioning.py` (or the provisioning test file)

- [ ] **Step 1: Write the failing tests**

Mirror the existing provisioning test setup (building a `TenantInvite` with `max_uses`, calling the two functions). Add three tests:

```python
async def test_create_onboarding_does_not_consume_invite(session):
    # build an invite with max_uses=1, used_count=0, status="active"
    invite = ...  # reuse the file's invite helper
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="cabbage", display_name="Cabbage",
        default_lang="en", owner_tg_id=111, owner_chat_id=111,
    )
    await session.refresh(invite)
    assert invite.used_count == 0          # NOT consumed at start
    assert invite.status == "active"
    assert tenant.invite_id == invite.id   # linked

async def test_finalize_consumes_invite(session):
    invite = ...  # max_uses=1
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="kale", display_name="Kale",
        default_lang="en", owner_tg_id=222, owner_chat_id=222,
    )
    await finalize_provisioning(
        session, tenant_id=tenant.id, token="123456:ABC-DEF",
        bot_telegram_id=500001, bot_username="kalebot", default_lang="en",
    )
    await session.refresh(invite)
    assert invite.used_count == 1
    assert invite.status == "used"

async def test_second_onboarding_reuses_provisioning_tenant(session):
    invite = ...  # max_uses=1
    t1 = await create_tenant_from_onboarding(
        session, invite=invite, slug="leek1", display_name="Leek",
        default_lang="en", owner_tg_id=333, owner_chat_id=333,
    )
    t2 = await create_tenant_from_onboarding(
        session, invite=invite, slug="leek2", display_name="Leek2",
        default_lang="en", owner_tg_id=333, owner_chat_id=333,
    )
    assert t2.id == t1.id            # reused, not duplicated
    assert t2.slug == "leek2"        # details updated to latest attempt
    from sqlalchemy import select, func
    from quantuum.db.models import Tenant, TenantBot
    n_tenants = (await session.execute(
        select(func.count()).select_from(Tenant).where(Tenant.invite_id == invite.id)
    )).scalar()
    n_bots = (await session.execute(
        select(func.count()).select_from(TenantBot).where(TenantBot.tenant_id == t1.id)
    )).scalar()
    assert n_tenants == 1 and n_bots == 1
```

NOTE: `finalize_provisioning` calls `find_or_create_account_by_tg` and `seed_tenant_defaults`; ensure the test invite/tenant have the fields these need (the helper reads `tenant.owner_tg_id`). The token string `"123456:ABC-DEF"` is only stored (encrypted), not validated, inside finalize.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest <test file> -k "consume_invite or reuses_provisioning" -v`
Expected: FAIL — current code consumes at start (`used_count == 1` after create) and creates a second tenant on the second call.

- [ ] **Step 3: Implement `create_tenant_from_onboarding`**

Replace the body so it (a) reuses an existing provisioning tenant for this invite, (b) sets `invite_id`, (c) does NOT touch `used_count`:

```python
async def create_tenant_from_onboarding(
    session,
    *,
    invite: TenantInvite,
    slug: str,
    display_name: str,
    default_lang: str,
    owner_tg_id: int | str,
    owner_chat_id: int | str,
    transport: str = "polling",
) -> Tenant:
    """Create (or reuse) a provisioning tenant + bot row for this invite.

    The invite use is consumed in finalize_provisioning (on success), not here,
    so an abandoned onboarding leaves the invite usable. A second onboarding for
    the same invite reuses the existing un-finalized tenant instead of spawning a
    duplicate.
    """
    existing = (
        await session.execute(
            select(Tenant).where(
                Tenant.invite_id == invite.id,
                Tenant.status == "provisioning",
            )
        )
    ).scalars().first()
    if existing is not None:
        existing.slug = slug
        existing.display_name = display_name
        existing.owner_tg_id = str(owner_tg_id)
        existing.owner_chat_id = str(owner_chat_id)
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing

    tenant = Tenant(
        slug=slug,
        display_name=display_name,
        tier=invite.tier,
        status="provisioning",
        owner_tg_id=str(owner_tg_id),
        owner_chat_id=str(owner_chat_id),
        invite_id=invite.id,
    )
    session.add(tenant)
    await session.flush()
    session.add(
        TenantBot(
            tenant_id=tenant.id,
            bot_token_enc=b"",
            transport=transport,
            webhook_secret_path=url_safe_token(16),
            status="provisioning",
        )
    )
    await session.commit()
    await session.refresh(tenant)
    return tenant
```

- [ ] **Step 4: Implement the increment in `finalize_provisioning`**

In `finalize_provisioning`, capture the pre-activation status and, after flipping to active (before `await session.commit()`), consume the invite once:

```python
    was_provisioning = tenant.status == "provisioning"
    # ... existing activation lines (set token, status="active", etc.) ...
    if was_provisioning and tenant.invite_id is not None:
        invite = await session.get(TenantInvite, tenant.invite_id)
        if invite is not None:
            invite.used_count += 1
            if invite.used_count >= invite.max_uses:
                invite.status = "used"
                invite.used_at = utcnow()
            session.add(invite)
```

(`TenantInvite` and `utcnow` are already imported in this module.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest <test file> -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/domain/provisioning.py <test file>
git commit -m "fix(provisioning): consume invite on finalize and reuse provisioning tenant"
```

---

### Task 5: Reject finalize when the bot id is already in use

**Files:**
- Modify: `src/quantuum/domain/provisioning.py` — add `BotAlreadyInUseError`; guard in `finalize_provisioning`
- Modify: `src/quantuum/bot/handlers/master_onboarding.py` — catch the error in `on_managed_bot_created` and `on_manual_token`, show `master.onboard.token_in_use`
- Test: `tests/test_provisioning.py` and `tests/test_master_onboarding*.py` (grep for the onboarding handler tests)

- [ ] **Step 1: Write the failing tests**

Domain test:

```python
async def test_finalize_rejects_bot_already_in_use(session):
    import pytest
    from quantuum.db.models import Tenant, TenantBot
    from quantuum.domain.provisioning import (
        BotAlreadyInUseError, finalize_provisioning,
    )
    # tenant A already active with bot id 600001
    a = Tenant(slug="taken", display_name="Taken", status="active",
               owner_tg_id="900", owner_chat_id="900")
    session.add(a); await session.flush()
    session.add(TenantBot(
        tenant_id=a.id, bot_token_enc=b"x", transport="polling",
        webhook_secret_path="s1", status="active", bot_telegram_id=600001,
    ))
    # tenant B provisioning, trying to claim the SAME bot id
    b = Tenant(slug="claimer", display_name="Claimer", status="provisioning",
               owner_tg_id="901", owner_chat_id="901")
    session.add(b); await session.flush()
    session.add(TenantBot(
        tenant_id=b.id, bot_token_enc=b"", transport="polling",
        webhook_secret_path="s2", status="provisioning",
    ))
    await session.commit()

    with pytest.raises(BotAlreadyInUseError):
        await finalize_provisioning(
            session, tenant_id=b.id, token="123456:ABC-DEF",
            bot_telegram_id=600001, bot_username="dupe", default_lang="en",
        )
    # B not activated
    b2 = await session.get(Tenant, b.id); await session.refresh(b2)
    assert b2.status == "provisioning"
```

Handler test: mirror the existing onboarding handler tests for `on_manual_token`. Patch `validate_bot_token` to return a `(bot_id, username)` whose `bot_id` is already an active TenantBot, run `on_manual_token`, and assert the rendered `master.onboard.token_in_use` message is sent and the tenant stays provisioning. (Grep the onboarding handler test file for how it builds `message`/`state`/`i18n` and patches `validate_bot_token`/`finalize_provisioning`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest <provisioning test file> -k rejects_bot_already_in_use -v`
Expected: FAIL — no `BotAlreadyInUseError` raised; B gets activated.

- [ ] **Step 3: Implement the domain guard**

In `src/quantuum/domain/provisioning.py`, add near the top:

```python
class BotAlreadyInUseError(Exception):
    """The bot_telegram_id is already claimed by another active TenantBot."""
```

In `finalize_provisioning`, after resolving `tenant_bot` and BEFORE mutating it, add:

```python
    clash = (
        await session.execute(
            select(TenantBot).where(
                TenantBot.bot_telegram_id == bot_telegram_id,
                TenantBot.status == "active",
                TenantBot.tenant_id != tenant_id,
            )
        )
    ).scalars().first()
    if clash is not None:
        raise BotAlreadyInUseError(
            f"bot {bot_telegram_id} already used by tenant {clash.tenant_id}"
        )
```

- [ ] **Step 4: Implement the handler catch**

In `src/quantuum/bot/handlers/master_onboarding.py`, import the error:

```python
from quantuum.domain.provisioning import (
    BotAlreadyInUseError,
    create_tenant_from_onboarding,
    finalize_provisioning,
    validate_bot_token,
)
```

In `on_manual_token`, wrap the finalize call:

```python
    async with get_sessionmaker()() as session:
        try:
            tenant_bot = await finalize_provisioning(
                session,
                tenant_id=data["tenant_id"],
                token=token,
                bot_telegram_id=bot_id,
                bot_username=username,
                default_lang=data.get("default_lang", "ru"),
            )
        except BotAlreadyInUseError:
            await message.answer(await i18n("master.onboard.token_in_use"))
            return
```

(Leaving the FSM in `ManualToken.awaiting` so the owner can paste a different token.)

In `on_managed_bot_created`, wrap the finalize call the same way:

```python
        try:
            tenant_bot = await finalize_provisioning(...)
        except BotAlreadyInUseError:
            await message.answer(await i18n("master.onboard.token_in_use"))
            return
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest <provisioning test file> <onboarding handler test file> -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/domain/provisioning.py src/quantuum/bot/handlers/master_onboarding.py <test files>
git commit -m "fix(provisioning): reject finalize when bot id already in use"
```

---

### Task 6: Stage regression — full suite

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: all green (prior baseline 2038 passed + this plan's new tests).

- [ ] **Step 2: If anything fails**

The likely regression is an existing provisioning test asserting `used_count == 1` right after `create_tenant_from_onboarding`. That behavior intentionally changed (consume moved to finalize). If such a test exists, update it to reflect the new contract (assert `used_count == 0` after create, `== 1` after finalize) — this is an intended behavior change, not a weakening. Confirm `uv run alembic heads` shows a single head.

- [ ] **Step 3: Commit** any test updates with a clear message.

---

## Notes / scope

- The bot-id uniqueness check guards `finalize` (the activation point). The `TenantBot.bot_telegram_id` column is nullable (provisioning rows have NULL), so a partial unique DB index is not added here — the app-level check at the single activation path is sufficient and avoids churn on the nullable column.
- After this plan, update the `audit-fix-sweep-progress` memory: C DONE. Spec order next: E → F → G.
