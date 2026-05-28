from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from quantuum.bot.handlers.gift import on_amount_received, show_gift_screen
from quantuum.bot.ui.text import MENU_BUTTON_KEYS
from quantuum.db.models import AccountBalance


def test_btn_gift_in_menu_button_keys():
    assert "btn.gift" in MENU_BUTTON_KEYS


async def _seed_sender(session, t_id, tg="1001", credits=50):
    from quantuum.auth.identity import find_or_create_account_by_tg
    acc = await find_or_create_account_by_tg(
        session, tenant_id=t_id, tg_user_id=tg
    )
    bal = await session.get(AccountBalance, acc.id)
    bal.package_credits = credits
    await session.flush()
    return acc


async def test_show_gift_screen_renders_balance_and_history(session, default_tenant):
    sender = await _seed_sender(session, default_tenant.id)
    await session.commit()

    msg = MagicMock()
    msg.answer = AsyncMock()
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}:{kw}>")

    await show_gift_screen(
        msg, account_id=sender.id, tenant_id=default_tenant.id, i18n=i18n
    )
    body = msg.answer.await_args.args[0]
    assert "gift.title" in body
    assert "gift.balance_line" in body
    assert "gift.history_empty" in body


async def test_show_gift_screen_blocked_when_feature_off(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.domain.tenant_features import set_feature_enabled

    sender = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="1001"
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="gifts",
        enabled=False,
        by_account_id=sender.id,
    )
    await session.commit()

    msg = MagicMock()
    msg.answer = AsyncMock()
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}>")

    await show_gift_screen(
        msg, account_id=sender.id, tenant_id=default_tenant.id, i18n=i18n
    )
    body = msg.answer.await_args.args[0]
    assert body == "<gift.disabled>"


async def test_show_gift_screen_runs_sweep(session, default_tenant):
    from quantuum.common.datetime import utcnow
    from quantuum.domain.gifts import create_gift

    sender = await _seed_sender(session, default_tenant.id, credits=100)
    tok = await create_gift(
        session, sender_account_id=sender.id,
        tenant_id=default_tenant.id, amount=15,
    )
    tok.expires_at = utcnow() - timedelta(seconds=1)
    await session.commit()

    msg = MagicMock()
    msg.answer = AsyncMock()
    i18n = AsyncMock(side_effect=lambda key, **kw: f"<{key}:{kw}>")

    await show_gift_screen(
        msg, account_id=sender.id, tenant_id=default_tenant.id, i18n=i18n
    )

    bal = await session.get(AccountBalance, sender.id)
    await session.refresh(bal)
    assert bal.package_credits == 100  # 100 - 15 (gift) + 15 (refund) = 100


async def test_create_flow_emits_link(session, default_tenant):
    """End-to-end of the amount-received handler."""
    sender = await _seed_sender(session, default_tenant.id, credits=50)
    from quantuum.db.models import TenantBot
    session.add(TenantBot(
        tenant_id=default_tenant.id,
        bot_username="t_bot",
        bot_token_enc=b"x",
        webhook_secret_path="/wh",
    ))
    await session.commit()

    msg = MagicMock()
    msg.text = "10"
    msg.from_user = MagicMock()
    msg.from_user.id = 1001
    msg.answer = AsyncMock()

    state = MagicMock()
    state.get_data = AsyncMock(return_value={
        "account_id": sender.id,
        "tenant_id": default_tenant.id,
        "max_amount": 50,
    })
    state.clear = AsyncMock()

    i18n = AsyncMock(side_effect=lambda key, **kw: f"{key}:{kw}")

    await on_amount_received(
        msg,
        state=state,
        i18n=i18n,
        account=MagicMock(id=sender.id),
        tenant_id=default_tenant.id,
    )

    body = msg.answer.await_args.args[0]
    assert "gift.created" in body
    assert "https://t.me/t_bot?start=" in body
