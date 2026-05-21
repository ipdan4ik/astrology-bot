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
