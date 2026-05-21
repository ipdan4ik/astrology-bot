from quantuum.bot.reload import BotSpec, diff_specs, load_active_bot_specs
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
