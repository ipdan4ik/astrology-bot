from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.owner_console import (
    on_features_open,
    on_features_toggle,
)
from quantuum.bot.ui.callbacks import OwnerFeatureCb
from quantuum.db.models import TenantConfig, TenantRole
from quantuum.domain.tenant_features import is_feature_enabled
from tests.conftest import build_translator


async def _make_owner(session, tenant_id, *, tg):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=tg
    )
    session.add(TenantRole(tenant_id=tenant_id, account_id=acc.id, role="owner"))
    await session.commit()
    return acc


def _make_query(tg_user_id: str):
    query = MagicMock()
    query.from_user = MagicMock()
    query.from_user.id = int(tg_user_id)
    query.message = MagicMock()
    query.message.edit_text = AsyncMock()
    query.message.edit_reply_markup = AsyncMock()
    query.message.answer = AsyncMock()
    query.answer = AsyncMock()
    return query


async def test_features_open_renders_all_fourteen_toggles(session, default_tenant):
    await _make_owner(session, default_tenant.id, tg="100")
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = _make_query("100")
    cb = OwnerFeatureCb(action="open", tenant_id=default_tenant.id, key="")
    await on_features_open(query, cb, i18n)

    query.message.edit_text.assert_called_once()
    _, kwargs = query.message.edit_text.call_args
    markup = kwargs.get("reply_markup")
    assert markup is not None
    button_data = [
        btn.callback_data for row in markup.inline_keyboard for btn in row
        if btn.callback_data is not None
    ]
    toggle_count = sum(1 for cd in button_data if cd.startswith("ofeat:toggle"))
    # 4 top-level (qa/blueprint/transits/daily) + 10 reading kinds (8 chart + tarot/iching)
    assert toggle_count == 14


async def test_features_toggle_persists_and_round_trips(session, default_tenant):
    await _make_owner(session, default_tenant.id, tg="101")
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = _make_query("101")
    cb = OwnerFeatureCb(action="toggle", tenant_id=default_tenant.id, key="qa")
    await on_features_toggle(query, cb, i18n)

    # Flipped from default ON to OFF.
    assert await is_feature_enabled(session, default_tenant.id, "qa") is False
    # Second toggle flips it back.
    await on_features_toggle(query, cb, i18n)
    assert await is_feature_enabled(session, default_tenant.id, "qa") is True


async def test_non_owner_cannot_toggle(session, default_tenant):
    # Just an account, no TenantRole(owner).
    await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="999"
    )
    await session.commit()

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = _make_query("999")
    cb = OwnerFeatureCb(action="toggle", tenant_id=default_tenant.id, key="qa")
    await on_features_toggle(query, cb, i18n)

    # No row was written.
    rows = (
        await session.execute(
            select(TenantConfig).where(
                TenantConfig.tenant_id == default_tenant.id,
                TenantConfig.key == "feature.qa",
            )
        )
    ).all()
    assert rows == []
    # And the user was told they have no rights via show_alert.
    query.answer.assert_awaited_once()
    args, kwargs = query.answer.await_args
    # show_alert is the kwarg; the text is the first positional arg.
    text_arg = args[0] if args else kwargs.get("text", "")
    assert text_arg, "no answer text was sent"
    assert kwargs.get("show_alert") is True
