import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.bot.reload import BotSpec, diff_specs, load_active_bot_specs, reload_signals, PollingSupervisor, poll_one
from quantuum.redis_client import publish_bot_reload
from quantuum.common.crypto import encrypt_token
from quantuum.db.models import Tenant, TenantBot


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


async def test_poll_one_survives_feed_update_error():
    u1 = SimpleNamespace(update_id=1)
    u2 = SimpleNamespace(update_id=2)
    bot = SimpleNamespace(
        id=7,
        delete_webhook=AsyncMock(),
        get_updates=AsyncMock(side_effect=[[u1, u2], asyncio.CancelledError()]),
    )
    dp = SimpleNamespace(feed_update=AsyncMock(side_effect=[RuntimeError("boom"), None]))

    with __import__("pytest").raises(asyncio.CancelledError):
        await poll_one(dp, bot, allowed_updates=["message"])

    assert dp.feed_update.await_count == 2  # u1 raised but u2 was still processed (loop survived)


async def test_polling_supervisor_restarts_dead_task(monkeypatch):
    import quantuum.bot.reload as reload_mod

    desired = {1: _spec(1)}

    async def fake_load(session, transport):
        return dict(desired)

    monkeypatch.setattr(reload_mod, "load_active_bot_specs", fake_load)

    spawn_calls: list[int] = []

    def fake_spawn(spec):
        spawn_calls.append(spec.bot_telegram_id)

        async def _noop():
            return None

        bot = SimpleNamespace(session=SimpleNamespace(close=AsyncMock()))
        return bot, asyncio.create_task(_noop())  # completes immediately -> done()

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
    await asyncio.sleep(0)  # let the spawned task finish so it is done()
    await sup.reconcile()  # should detect the dead task and respawn it

    assert spawn_calls.count(1) == 2  # spawned initially, then restarted
    assert set(sup.live) == {1}


def test_default_spawn_routes_master_vs_customer(monkeypatch):
    import quantuum.bot.reload as reload_mod

    class _FakeBot:
        def __init__(self, token):
            self.session = SimpleNamespace(close=AsyncMock())

    used_dps: list = []

    def fake_poll_one(dp, bot, allowed):
        used_dps.append(dp)

        async def _n():
            return None

        return _n()

    def fake_create_task(coro):
        coro.close()  # avoid 'coroutine never awaited' warning
        return "TASK"

    monkeypatch.setattr(reload_mod, "Bot", _FakeBot)
    monkeypatch.setattr(reload_mod, "poll_one", fake_poll_one)
    monkeypatch.setattr(reload_mod.asyncio, "create_task", fake_create_task)

    customer_dp = SimpleNamespace(resolve_used_update_types=lambda: ["message"])
    master_dp = SimpleNamespace(resolve_used_update_types=lambda: ["message"])
    sup = PollingSupervisor(None, customer_dp=customer_dp, master_dp=master_dp)

    sup._default_spawn(_spec(1, is_master=False))
    sup._default_spawn(_spec(2, is_master=True))

    assert used_dps == [customer_dp, master_dp]


async def test_load_active_bot_specs_skips_null_id_and_empty_token(session, default_tenant):
    session.add(
        TenantBot(
            tenant_id=default_tenant.id, bot_telegram_id=None,
            bot_token_enc=encrypt_token(_TOKEN), transport="polling",
            webhook_secret_path="sec-nullid", status="active",
        )
    )
    session.add(
        TenantBot(
            tenant_id=default_tenant.id, bot_telegram_id=555,
            bot_token_enc=b"", transport="polling",
            webhook_secret_path="sec-emptytok", status="active",
        )
    )
    await session.commit()

    specs = await load_active_bot_specs(session, "polling")
    assert specs == {}


def test_polling_run_is_supervised():
    import inspect

    import quantuum.bot.polling as polling

    src = inspect.getsource(polling.run)
    assert "PollingSupervisor" in src
    assert "reload_signals" in src
