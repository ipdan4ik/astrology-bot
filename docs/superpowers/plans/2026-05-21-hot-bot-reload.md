# Hot Bot Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load/unload tenant bots in the running polling and webhook workers without a process restart.

**Architecture:** A shared reconcile core (`bot/reload.py`) diffs the DB's active bots for a transport against the live pool and applies the delta. It is driven by `reload_signals`, one loop that fires on either a periodic timeout (~10s) or a Redis pub/sub nudge published at provisioning. Polling spawns/cancels one long-poll task per bot (dispatchers reused, FSM preserved); webhook mutates its in-memory pool dicts.

**Tech Stack:** Python 3.12, aiogram 3, SQLModel/asyncpg, redis.asyncio (5.3.1), arq, pytest (asyncio auto mode).

**Branch:** `feat/hot-bot-reload` (already checked out).

**Test environment:** Tests run from the host against the test PG/redis at 172.30.0.2 / 172.30.0.3 (defaults already wired in `tests/conftest.py`). Run with `uv run pytest`. The `warning: VIRTUAL_ENV=/usr ...` line in output is harmless.

**Conventions to follow:**
- Fixtures: `session` (AsyncSession), `default_tenant` (a `Tenant` with slug `default`). Create a platform tenant inline where needed: `Tenant(slug="platform", display_name="Platform", is_platform=True)`.
- Token crypto: `from quantuum.common.crypto import encrypt_token, decrypt_token`. A token must be aiogram-valid format (`<digits>:<word>`), e.g. `"111111:AABBccDD-eeFF_gghh"`, because `aiogram.Bot(token=...)` validates format on construction.
- Logger: `from quantuum.logging_setup import get_logger`.

---

### Task 1: `BotSpec` + `diff_specs` (pure core)

**Files:**
- Create: `src/quantuum/bot/reload.py`
- Test: `tests/test_bot_reload.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bot_reload.py
from quantuum.bot.reload import BotSpec, diff_specs


def _spec(bot_id: int, is_master: bool = False) -> BotSpec:
    return BotSpec(bot_telegram_id=bot_id, token=f"{bot_id}:tok", is_master=is_master)


def test_diff_specs_adds_new():
    desired = {1: _spec(1), 2: _spec(2)}
    assert diff_specs({1}, desired) == ({2}, set())


def test_diff_specs_removes_missing():
    desired = {1: _spec(1)}
    assert diff_specs({1, 3}, desired) == (set(), {3})


def test_diff_specs_mixed_and_noop():
    desired = {1: _spec(1), 2: _spec(2)}
    assert diff_specs({2, 3}, desired) == ({1}, {3})
    assert diff_specs({1, 2}, desired) == (set(), set())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_reload.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'quantuum.bot.reload'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/quantuum/bot/reload.py
from dataclasses import dataclass

from quantuum.logging_setup import get_logger

logger = get_logger("bot.reload")


@dataclass(frozen=True)
class BotSpec:
    bot_telegram_id: int
    token: str  # decrypted bot token
    is_master: bool  # platform tenant => master dispatcher


def diff_specs(
    current_ids: set[int], desired: dict[int, BotSpec]
) -> tuple[set[int], set[int]]:
    """Return (to_add, to_remove) bot ids. Pure set math."""
    return set(desired) - current_ids, current_ids - set(desired)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_reload.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/reload.py tests/test_bot_reload.py
git commit -m "feat(reload): BotSpec + diff_specs core"
```

---

### Task 2: `load_active_bot_specs` (DB → specs)

**Files:**
- Modify: `src/quantuum/bot/reload.py`
- Test: `tests/test_bot_reload.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_bot_reload.py
from quantuum.bot.reload import load_active_bot_specs
from quantuum.common.crypto import encrypt_token
from quantuum.db.models import Tenant, TenantBot

_TOKEN = "111111:AABBccDD-eeFF_gghh"


async def _add_bot(session, tenant_id, bot_tg_id, *, transport="polling", status="active", token=_TOKEN):
    session.add(
        TenantBot(
            tenant_id=tenant_id,
            bot_telegram_id=bot_tg_id,
            bot_token_enc=encrypt_token(token),
            transport=transport,
            webhook_secret_path=f"sec-{bot_tg_id}",
            status=status,
        )
    )
    await session.commit()


async def test_load_active_bot_specs_keys_decrypts_and_flags_master(session, default_tenant):
    platform = Tenant(slug="platform", display_name="Platform", is_platform=True)
    session.add(platform)
    await session.commit()
    await session.refresh(platform)

    await _add_bot(session, default_tenant.id, 1001)  # customer
    await _add_bot(session, platform.id, 2002)  # master

    specs = await load_active_bot_specs(session, "polling")

    assert set(specs) == {1001, 2002}
    assert specs[1001].token == _TOKEN  # decrypted
    assert specs[1001].is_master is False
    assert specs[2002].is_master is True


async def test_load_active_bot_specs_excludes_inactive_and_other_transport(session, default_tenant):
    await _add_bot(session, default_tenant.id, 1, status="paused")
    await _add_bot(session, default_tenant.id, 2, transport="webhook")
    await _add_bot(session, default_tenant.id, 3)  # active polling — the only match

    specs = await load_active_bot_specs(session, "polling")
    assert set(specs) == {3}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_reload.py -k load_active_bot_specs -q`
Expected: FAIL — `ImportError: cannot import name 'load_active_bot_specs'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/quantuum/bot/reload.py` (imports at top, function below `diff_specs`):

```python
from quantuum.common.crypto import decrypt_token
from quantuum.domain.tenants import get_platform_tenant_id, list_active_tenant_bots


async def load_active_bot_specs(session, transport: str) -> dict[int, BotSpec]:
    """All active tenant bots for `transport`, keyed by bot_telegram_id.

    Token is decrypted; is_master = the bot belongs to the platform tenant. Rows with a
    null bot_telegram_id or empty token are skipped.
    """
    platform_id = await get_platform_tenant_id(session)
    specs: dict[int, BotSpec] = {}
    for tb in await list_active_tenant_bots(session, transport):
        if tb.bot_telegram_id is None or not tb.bot_token_enc:
            continue
        specs[tb.bot_telegram_id] = BotSpec(
            bot_telegram_id=tb.bot_telegram_id,
            token=decrypt_token(tb.bot_token_enc),
            is_master=(tb.tenant_id == platform_id),
        )
    return specs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_reload.py -k load_active_bot_specs -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/reload.py tests/test_bot_reload.py
git commit -m "feat(reload): load_active_bot_specs from DB"
```

---

### Task 3: Redis nudge — `publish_bot_reload` + `reload_signals`

**Files:**
- Modify: `src/quantuum/redis_client.py`
- Modify: `src/quantuum/bot/reload.py`
- Test: `tests/test_bot_reload.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_bot_reload.py
import asyncio

from quantuum.bot.reload import reload_signals
from quantuum.redis_client import publish_bot_reload


async def test_reload_signals_yields_on_publish():
    gen = reload_signals(interval=5.0)
    waiter = asyncio.create_task(gen.__anext__())
    await asyncio.sleep(0.2)  # let the subscription register before publishing
    await publish_bot_reload()
    await asyncio.wait_for(waiter, timeout=3.0)  # nudge wakes it well before the 5s interval
    await gen.aclose()


async def test_reload_signals_yields_on_timeout():
    gen = reload_signals(interval=0.2)
    await asyncio.wait_for(gen.__anext__(), timeout=3.0)  # no publish -> interval tick
    await gen.aclose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_reload.py -k reload_signals -q`
Expected: FAIL — `ImportError: cannot import name 'publish_bot_reload'` (or `reload_signals`)

- [ ] **Step 3: Write minimal implementation**

Add to `src/quantuum/redis_client.py` (after `pop_update`):

```python
BOT_RELOAD_CHANNEL = "bot:reload"


async def publish_bot_reload() -> None:
    """Nudge the bot workers to reconcile their bot pools immediately."""
    await get_redis().publish(BOT_RELOAD_CHANNEL, "1")
```

Add to `src/quantuum/bot/reload.py`:

```python
from collections.abc import AsyncIterator

from quantuum.redis_client import BOT_RELOAD_CHANNEL, get_redis


async def reload_signals(interval: float) -> AsyncIterator[None]:
    """Yield once per nudge OR per `interval` seconds, whichever comes first.

    Each yield should drive one reconcile, so a missed nudge is still corrected within
    `interval` (self-healing). Redundant nudges coalesce into harmless extra reconciles.
    """
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(BOT_RELOAD_CHANNEL)
    try:
        while True:
            await pubsub.get_message(ignore_subscribe_messages=True, timeout=interval)
            yield
    finally:
        await pubsub.unsubscribe(BOT_RELOAD_CHANNEL)
        await pubsub.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_reload.py -k reload_signals -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/redis_client.py src/quantuum/bot/reload.py tests/test_bot_reload.py
git commit -m "feat(reload): publish_bot_reload + reload_signals (periodic + nudge)"
```

---

### Task 4: `poll_one` + `PollingSupervisor`

**Files:**
- Modify: `src/quantuum/bot/reload.py`
- Test: `tests/test_bot_reload.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_bot_reload.py
from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.bot.reload import PollingSupervisor, poll_one


async def test_poll_one_feeds_updates_then_stops_on_cancel():
    update = SimpleNamespace(update_id=10)
    bot = SimpleNamespace(
        id=1,
        delete_webhook=AsyncMock(),
        get_updates=AsyncMock(side_effect=[[update], asyncio.CancelledError()]),
    )
    dp = SimpleNamespace(feed_update=AsyncMock())

    with __import__("pytest").raises(asyncio.CancelledError):
        await poll_one(dp, bot, allowed_updates=["message"])

    bot.delete_webhook.assert_awaited_once()
    dp.feed_update.assert_awaited_once_with(bot, update)


async def test_polling_supervisor_reconcile_spawns_and_cancels(monkeypatch):
    import quantuum.bot.reload as reload_mod

    # Control the desired set without touching the DB.
    desired = {1: _spec(1), 2: _spec(2, is_master=True)}

    async def fake_load(session, transport):
        return dict(desired)

    monkeypatch.setattr(reload_mod, "load_active_bot_specs", fake_load)

    spawned: list[int] = []

    def fake_spawn(spec):
        spawned.append(spec.bot_telegram_id)
        bot = SimpleNamespace(session=SimpleNamespace(close=AsyncMock()))
        task = asyncio.create_task(asyncio.sleep(3600))
        return bot, task

    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return None
        async def __aexit__(self, *a):
            return False

    sup = PollingSupervisor(_Maker(), customer_dp=None, master_dp=None, spawn=fake_spawn)

    await sup.reconcile()
    assert sorted(spawned) == [1, 2]
    assert set(sup.live) == {1, 2}

    removed_bot, removed_task = sup.live[1]
    desired.pop(1)  # bot 1 deactivated
    await sup.reconcile()

    assert set(sup.live) == {2}
    assert removed_task.cancelled()
    removed_bot.session.close.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_reload.py -k "poll_one or polling_supervisor" -q`
Expected: FAIL — `ImportError: cannot import name 'PollingSupervisor'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/quantuum/bot/reload.py`:

```python
import asyncio

from aiogram import Bot


async def poll_one(dp, bot: Bot, allowed_updates: list[str]) -> None:
    """Long-poll a single bot, feeding updates into `dp`. Resilient to transient errors."""
    await bot.delete_webhook(drop_pending_updates=True)
    offset = None
    while True:
        try:
            updates = await bot.get_updates(
                offset=offset, timeout=30, allowed_updates=allowed_updates
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("poll_error", bot_id=getattr(bot, "id", None))
            await asyncio.sleep(3)
            continue
        for u in updates:
            offset = u.update_id + 1
            await dp.feed_update(bot, u)


class PollingSupervisor:
    """Keeps one long-poll task per active bot, reconciling against the DB on demand.

    Dispatchers are created once and reused, so in-progress FSM state survives reconciles
    and existing bots are never interrupted when others come or go.
    """

    def __init__(self, sessionmaker, customer_dp, master_dp, *, spawn=None) -> None:
        self.sessionmaker = sessionmaker
        self.customer_dp = customer_dp
        self.master_dp = master_dp
        self.live: dict[int, tuple[Bot, asyncio.Task]] = {}
        self._spawn = spawn or self._default_spawn

    def _default_spawn(self, spec: BotSpec) -> tuple[Bot, asyncio.Task]:
        bot = Bot(token=spec.token)
        dp = self.master_dp if spec.is_master else self.customer_dp
        allowed = dp.resolve_used_update_types()
        return bot, asyncio.create_task(poll_one(dp, bot, allowed))

    async def reconcile(self) -> None:
        async with self.sessionmaker() as session:
            desired = await load_active_bot_specs(session, "polling")
        to_add, to_remove = diff_specs(set(self.live), desired)
        for bot_id in to_add:
            self.live[bot_id] = self._spawn(desired[bot_id])
        for bot_id in to_remove:
            bot, task = self.live.pop(bot_id)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await bot.session.close()
        if to_add or to_remove:
            logger.info("polling_reconciled", added=len(to_add), removed=len(to_remove))
```

Note: move the `import asyncio` and `from aiogram import Bot` to the top of the file with the other imports (don't leave mid-file imports).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_reload.py -k "poll_one or polling_supervisor" -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/reload.py tests/test_bot_reload.py
git commit -m "feat(reload): poll_one + PollingSupervisor (per-bot poll tasks)"
```

---

### Task 5: Webhook `WebhookConsumer.reconcile`

**Files:**
- Modify: `src/quantuum/bot/runner.py`
- Test: `tests/test_bot_runner_reload.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bot_runner_reload.py
from quantuum.bot.runner import WebhookConsumer
from quantuum.common.crypto import encrypt_token
from quantuum.db.models import Tenant, TenantBot

_TOKEN = "222222:CCDDeeFF-gghh_iijj"


async def _add_webhook_bot(session, tenant_id, bot_tg_id, status="active"):
    session.add(
        TenantBot(
            tenant_id=tenant_id,
            bot_telegram_id=bot_tg_id,
            bot_token_enc=encrypt_token(_TOKEN),
            transport="webhook",
            webhook_secret_path=f"wh-{bot_tg_id}",
            status=status,
        )
    )
    await session.commit()


def _maker(session):
    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *a):
            return False

    return _Maker()


async def test_webhook_reconcile_adds_then_removes(session, default_tenant):
    platform = Tenant(slug="platform", display_name="Platform", is_platform=True)
    session.add(platform)
    await session.commit()
    await session.refresh(platform)

    consumer = WebhookConsumer(
        customer_dp=None, master_dp=None,
        customer_pool={}, master_pool={},
        sessionmaker=_maker(session),
    )

    await _add_webhook_bot(session, default_tenant.id, 3001)  # customer
    await _add_webhook_bot(session, platform.id, 4002)  # master
    await consumer.reconcile()

    assert set(consumer.customer_pool) == {3001}
    assert set(consumer.master_pool) == {4002}

    # Deactivate the customer bot; reconcile drops it.
    tb = (await session.execute(
        __import__("sqlmodel").select(TenantBot).where(TenantBot.bot_telegram_id == 3001)
    )).scalar_one()
    tb.status = "paused"
    await session.commit()
    await consumer.reconcile()

    assert set(consumer.customer_pool) == set()
    assert set(consumer.master_pool) == {4002}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_runner_reload.py -q`
Expected: FAIL — `TypeError: WebhookConsumer.__init__() got an unexpected keyword argument 'sessionmaker'`

- [ ] **Step 3: Write minimal implementation**

In `src/quantuum/bot/runner.py`, add the import near the top:

```python
from quantuum.bot.reload import diff_specs, load_active_bot_specs
```

Extend `WebhookConsumer.__init__` to accept and store `sessionmaker` (add the parameter to the signature and `self.sessionmaker = sessionmaker`), and add the method:

```python
    async def reconcile(self) -> None:
        async with self.sessionmaker() as session:
            desired = await load_active_bot_specs(session, "webhook")
        live = set(self.customer_pool) | set(self.master_pool)
        to_add, to_remove = diff_specs(live, desired)
        for bot_id in to_add:
            spec = desired[bot_id]
            bot = Bot(token=spec.token)
            (self.master_pool if spec.is_master else self.customer_pool)[bot_id] = bot
        for bot_id in to_remove:
            bot = self.customer_pool.pop(bot_id, None) or self.master_pool.pop(bot_id, None)
            if bot is not None:
                await bot.session.close()
        if to_add or to_remove:
            logger.info("webhook_reconciled", added=len(to_add), removed=len(to_remove))
```

(`Bot` and `logger` are already imported in `runner.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_runner_reload.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/runner.py tests/test_bot_runner_reload.py
git commit -m "feat(reload): WebhookConsumer.reconcile mutates pools live"
```

---

### Task 6: Settings — `bot_reload_interval_seconds`

**Files:**
- Modify: `src/quantuum/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_settings.py (inside test_settings_have_2b_defaults, or a new test)
def test_bot_reload_interval_default():
    from quantuum.settings import Settings

    assert Settings.model_fields["bot_reload_interval_seconds"].default == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings.py::test_bot_reload_interval_default -q`
Expected: FAIL — `KeyError: 'bot_reload_interval_seconds'`

- [ ] **Step 3: Write minimal implementation**

Add to the `Settings` class in `src/quantuum/settings.py` (near the other bot fields):

```python
    bot_reload_interval_seconds: float = 10.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_settings.py::test_bot_reload_interval_default -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/settings.py tests/test_settings.py
git commit -m "feat(reload): bot_reload_interval_seconds setting"
```

---

### Task 7: Publish reload after `finalize_provisioning`

**Files:**
- Modify: `src/quantuum/bot/handlers/master_onboarding.py`
- Test: `tests/test_master_onboarding.py`

- [ ] **Step 1: Write the failing test**

The existing `test_managed_bot_created_finalizes` and `test_manual_token_finalizes` set up a finalized tenant. Add a publish spy to **both** and assert it fired. Add this new focused test (it reuses the managed path setup):

```python
# add to tests/test_master_onboarding.py
async def test_finalize_publishes_bot_reload(session, default_tenant, monkeypatch):
    """After a managed bot is created and provisioning is finalized, the worker is nudged
    to reconcile so the new bot serves without a restart."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import master_onboarding as mo
    from quantuum.domain.invites import create_invite
    from quantuum.domain.provisioning import create_tenant_from_onboarding

    _patch_sessionmaker(monkeypatch, mo, session)
    i18n = await build_translator(session, default_tenant.id)

    published = AsyncMock()
    monkeypatch.setattr(mo, "publish_bot_reload", published)

    invite = await create_invite(session, created_by_account_id=None)
    await session.commit()
    tenant = await create_tenant_from_onboarding(
        session, invite=invite, slug="zen", display_name="Zen",
        default_lang="ru", owner_tg_id=777, owner_chat_id=777,
    )
    state = _FakeState({"tenant_id": tenant.id, "default_lang": "ru"})
    created = SimpleNamespace(bot_user=SimpleNamespace(id=900, username="zen_managed_bot"))
    message = SimpleNamespace(managed_bot_created=created, answer=AsyncMock())
    bot = AsyncMock(return_value="900:managedtoken")

    await mo.on_managed_bot_created(message, state, i18n=i18n, bot=bot)

    published.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_master_onboarding.py::test_finalize_publishes_bot_reload -q`
Expected: FAIL — `AttributeError: <module 'quantuum.bot.handlers.master_onboarding'> does not have the attribute 'publish_bot_reload'`

- [ ] **Step 3: Write minimal implementation**

In `src/quantuum/bot/handlers/master_onboarding.py` add the import:

```python
from quantuum.redis_client import publish_bot_reload
```

In `on_managed_bot_created`, after the `async with get_sessionmaker()() as session: tenant_bot = await finalize_provisioning(...)` block and before `await state.clear()`, add:

```python
    await publish_bot_reload()
```

Do the same in `on_manual_token`: after its `finalize_provisioning` block, before `await state.clear()`, add `await publish_bot_reload()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_master_onboarding.py -q`
Expected: PASS (all master-onboarding tests, including the new one)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/master_onboarding.py tests/test_master_onboarding.py
git commit -m "feat(reload): nudge workers after finalize_provisioning"
```

---

### Task 8: Wire the polling runner to the supervisor

**Files:**
- Modify: `src/quantuum/bot/polling.py`
- Test: `tests/test_bot_reload.py` (smoke)

This is integration glue around the unit-tested `PollingSupervisor`. There is no clean way to unit-test a real polling loop without network, so the test is a structural smoke check; correctness rests on Task 4 plus the manual verification at the end.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_bot_reload.py
def test_polling_run_is_supervised():
    import inspect

    import quantuum.bot.polling as polling

    src = inspect.getsource(polling.run)
    assert "PollingSupervisor" in src
    assert "reload_signals" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_reload.py::test_polling_run_is_supervised -q`
Expected: FAIL — assertion error (`PollingSupervisor` not yet referenced in `polling.run`)

- [ ] **Step 3: Write minimal implementation**

Replace the body of `run()` in `src/quantuum/bot/polling.py` so it builds a `PollingSupervisor` and drives it with `reload_signals`. Keep the existing bootstrap (`ensure_*`, `ensure_tenant_default_language`) calls. Replace the file with:

```python
"""Local/dev long-polling entrypoint: customer + master bots, hot-reloaded without restart."""

import asyncio

from quantuum.bot.app import create_dispatcher
from quantuum.bot.master_app import create_master_dispatcher
from quantuum.bot.reload import PollingSupervisor, reload_signals
from quantuum.db.bootstrap import (
    ensure_base_strings,
    ensure_default_tenant,
    ensure_default_tenant_bot,
    ensure_master_bot,
    ensure_platform_stars_provider,
    ensure_platform_tenant,
    ensure_tenant_default_language,
)
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import get_default_tenant_id
from quantuum.logging_setup import configure_logging, get_logger
from quantuum.settings import get_settings

logger = get_logger("bot.polling")


async def run() -> None:
    configure_logging()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        platform = await ensure_platform_tenant(session)
        await ensure_master_bot(session)
        await ensure_platform_stars_provider(session)
        await ensure_base_strings(session)
        default_tenant_id = await get_default_tenant_id(session)
        await ensure_tenant_default_language(session, default_tenant_id)
        await ensure_tenant_default_language(session, platform.id, default_lang="ru")

    supervisor = PollingSupervisor(
        sessionmaker,
        customer_dp=create_dispatcher(),
        master_dp=create_master_dispatcher(),
    )
    await supervisor.reconcile()
    logger.info("bot_polling_started", bots=len(supervisor.live))
    interval = get_settings().bot_reload_interval_seconds
    async for _ in reload_signals(interval):
        try:
            await supervisor.reconcile()
        except Exception:
            logger.exception("polling_reconcile_failed")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_reload.py::test_polling_run_is_supervised -q`
Expected: PASS

Also verify the module imports cleanly:
Run: `uv run python -c "import quantuum.bot.polling"`
Expected: no error.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/polling.py tests/test_bot_reload.py
git commit -m "feat(reload): polling runner driven by PollingSupervisor + reload loop"
```

---

### Task 9: Wire the webhook runner to reconcile loop

**Files:**
- Modify: `src/quantuum/bot/runner.py`
- Test: `tests/test_bot_runner_reload.py` (smoke)

Integration glue around the unit-tested `WebhookConsumer.reconcile`. Structural smoke test only; correctness rests on Task 5 plus manual verification.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_bot_runner_reload.py
def test_runner_run_reconciles_and_starts_empty():
    import inspect

    import quantuum.bot.runner as runner

    src = inspect.getsource(runner.run)
    assert "reconcile" in src
    assert "reload_signals" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot_runner_reload.py::test_runner_run_reconciles_and_starts_empty -q`
Expected: FAIL — assertion error (`reconcile`/`reload_signals` not referenced in `runner.run`)

- [ ] **Step 3: Write minimal implementation**

In `src/quantuum/bot/runner.py`, add the import:

```python
from quantuum.bot.reload import reload_signals
```

Replace `run()` so the consumer starts with empty pools, reconciles once, runs the reconcile loop as a background task, and keeps the existing `pop_update` loop. New `run()`:

```python
async def run() -> None:
    configure_logging()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        platform = await ensure_platform_tenant(session)
        await ensure_master_bot(session)
        await ensure_platform_stars_provider(session)
        await ensure_base_strings(session)
        default_tenant_id = await get_default_tenant_id(session)
        await ensure_tenant_default_language(session, default_tenant_id)
        await ensure_tenant_default_language(session, platform.id, default_lang="ru")

    consumer = WebhookConsumer(
        customer_dp=create_dispatcher(),
        master_dp=create_master_dispatcher(),
        customer_pool={},
        master_pool={},
        sessionmaker=sessionmaker,
    )
    await consumer.reconcile()
    logger.info(
        "bot_runner_started",
        customer_bots=len(consumer.customer_pool),
        master_bots=len(consumer.master_pool),
    )

    async def _reload_loop() -> None:
        interval = get_settings().bot_reload_interval_seconds
        async for _ in reload_signals(interval):
            try:
                await consumer.reconcile()
            except Exception:
                logger.exception("webhook_reconcile_failed")

    asyncio.create_task(_reload_loop())

    while True:
        envelope = await pop_update(timeout=5)
        if envelope is None:
            continue
        try:
            await consumer.process(envelope)
        except Exception:
            logger.exception("update_processing_failed", bot_id=envelope.get("bot_id"))
```

Add the imports `import asyncio` and `from quantuum.settings import get_settings` at the top if not already present. Remove the now-unused `build_bots`, `get_platform_tenant_id`, and `list_active_tenant_bots` imports if they are no longer referenced (run ruff to confirm).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bot_runner_reload.py -q`
Expected: PASS (2 passed)

Run: `uv run python -c "import quantuum.bot.runner"`
Expected: no error.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/runner.py tests/test_bot_runner_reload.py
git commit -m "feat(reload): webhook runner reconcile loop (starts empty, self-heals)"
```

---

### Task 10: Full suite + lint gate

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: all green (573 existing + the new reload tests).

- [ ] **Step 2: Lint**

Run: `uv run ruff check src/ tests/`
Expected: `All checks passed!`

- [ ] **Step 3: Commit (only if ruff auto-fixed anything)**

```bash
git add -A
git commit -m "chore(reload): lint" || echo "nothing to commit"
```

---

## Manual verification (after docker daemon is back)

The Docker daemon is currently down; these steps confirm the feature end-to-end once it is restarted (`sudo systemctl start docker`).

1. Rebuild + restart the polling stack:
   `docker compose -f docker-compose.yml -f docker-compose.polling.yml up -d --build`
2. In the master bot, onboard a brand-new tenant bot (invite → slug → name → lang → confirm → create).
3. **Without restarting any container**, open the new bot and send `/start`. It should respond within ~1s (nudge) — at most `bot_reload_interval_seconds` (~10s).
4. Confirm in logs: `docker compose logs task-worker | grep bot:reload` (publish) and `docker compose logs bot-worker | grep polling_reconciled` (pickup).

## Out of scope (per spec)

- Registering Telegram `set_webhook` for new webhook bots (a provisioning concern).
- Deactivation/suspension UX (the `bot:reload` channel is reused for it later).
- Code/handler hot-reload (this is bot-set reload only).
