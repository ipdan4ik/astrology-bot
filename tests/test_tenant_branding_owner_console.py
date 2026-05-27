from unittest.mock import AsyncMock, MagicMock

from aiogram.types import Message

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.owner_console import on_manage
from quantuum.bot.ui.callbacks import OwnerBrandingCb
from quantuum.db.models import TenantRole
from tests.conftest import build_translator


async def _make_owner(session, tenant_id, *, tg):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=tg
    )
    session.add(TenantRole(tenant_id=tenant_id, account_id=acc.id, role="owner"))
    await session.commit()
    return acc


def _make_message(tg_user_id: str) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock()
    msg.from_user.id = int(tg_user_id)
    msg.answer = AsyncMock()
    return msg


async def test_manage_keyboard_includes_branding_button(session, default_tenant):
    await _make_owner(session, default_tenant.id, tg="201")
    i18n = await build_translator(session, default_tenant.id, lang="ru")

    msg = _make_message("201")
    command = MagicMock()
    command.args = default_tenant.slug
    await on_manage(msg, command, i18n)

    msg.answer.assert_awaited_once()
    _, kwargs = msg.answer.await_args
    markup = kwargs.get("reply_markup")
    assert markup is not None
    button_datas = [
        btn.callback_data for row in markup.inline_keyboard for btn in row
        if btn.callback_data is not None
    ]
    branding_buttons = [
        cd for cd in button_datas if cd.startswith("obrand:")
    ]
    assert len(branding_buttons) == 1
    assert branding_buttons[0].startswith("obrand:open")


def test_owner_branding_cb_class_exists():
    cb = OwnerBrandingCb(action="open", tenant_id=1, key="")
    assert cb.pack().startswith("obrand:")
