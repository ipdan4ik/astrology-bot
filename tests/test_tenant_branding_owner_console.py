from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.owner_console import (
    on_branding_edit,
    on_branding_open,
    on_branding_value,
    on_manage,
)
from quantuum.bot.ui.callbacks import OwnerBrandingCb
from quantuum.db.models import TenantRole
from quantuum.domain.tenant_branding import (
    get_branding_text,
    set_branding_text,
)
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


def _make_query(tg_user_id: str):
    query = MagicMock()
    query.from_user = MagicMock()
    # Store as string so str() round-trip in handlers matches identity lookup.
    query.from_user.id = tg_user_id
    query.message = MagicMock()
    query.message.edit_text = AsyncMock()
    query.message.answer = AsyncMock()
    query.answer = AsyncMock()
    return query


def _make_fsm():
    state = MagicMock(spec=FSMContext)
    state.set_state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state


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


async def test_branding_submenu_renders_four_entries(session, default_tenant):
    await _make_owner(session, default_tenant.id, tg="210")
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = _make_query("210")
    cb = OwnerBrandingCb(action="open", tenant_id=default_tenant.id, key="")
    await on_branding_open(query, cb, i18n)

    query.message.edit_text.assert_awaited_once()
    _, kwargs = query.message.edit_text.await_args
    markup = kwargs.get("reply_markup")
    button_datas = [
        btn.callback_data for row in markup.inline_keyboard for btn in row
        if btn.callback_data is not None
    ]
    edit_callbacks = [cd for cd in button_datas if cd.startswith("obrand:edit")]
    assert len(edit_callbacks) == 4


async def test_non_owner_cannot_open_branding(session, default_tenant):
    await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="999b"
    )
    await session.commit()
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = _make_query("999b")
    cb = OwnerBrandingCb(action="open", tenant_id=default_tenant.id, key="")
    await on_branding_open(query, cb, i18n)

    query.message.edit_text.assert_not_called()
    query.answer.assert_awaited_once()
    args, kwargs = query.answer.await_args
    assert kwargs.get("show_alert") is True


async def test_branding_edit_flow_saves_override(session, default_tenant):
    await _make_owner(session, default_tenant.id, tg="220")
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    state = _make_fsm()

    query = _make_query("220")
    cb = OwnerBrandingCb(
        action="edit", tenant_id=default_tenant.id, key="start.welcome"
    )
    await on_branding_edit(query, cb, state, i18n)
    state.set_state.assert_awaited_once()
    state.update_data.assert_awaited_once()

    state.get_data = AsyncMock(
        return_value={
            "tenant_id": default_tenant.id,
            "key": "start.welcome",
            "lang": "ru",
        }
    )
    msg = _make_message("220")
    msg.text = "Custom welcome from Mystic Oracle"
    await on_branding_value(msg, state, i18n)

    stored = await get_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="start.welcome",
        lang="ru",
    )
    assert stored == "Custom welcome from Mystic Oracle"
    state.clear.assert_awaited_once()


async def test_branding_edit_flow_validates_too_long(session, default_tenant):
    await _make_owner(session, default_tenant.id, tg="221")
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    state = _make_fsm()
    state.get_data = AsyncMock(
        return_value={
            "tenant_id": default_tenant.id,
            "key": "brand.signature",
            "lang": "ru",
        }
    )
    msg = _make_message("221")
    msg.text = "x" * 1000

    await on_branding_value(msg, state, i18n)

    msg.answer.assert_awaited_once()
    args, _ = msg.answer.await_args
    assert "макси" in args[0].lower() or "max" in args[0].lower()
    stored = await get_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
    )
    assert stored is None
    state.clear.assert_not_called()


async def test_branding_edit_flow_display_name_newline_rejected(
    session, default_tenant
):
    await _make_owner(session, default_tenant.id, tg="222")
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    state = _make_fsm()
    state.get_data = AsyncMock(
        return_value={
            "tenant_id": default_tenant.id,
            "key": "display_name",
            "lang": "ru",
        }
    )
    msg = _make_message("222")
    msg.text = "bad\nname"

    await on_branding_value(msg, state, i18n)

    msg.answer.assert_awaited_once()
    state.clear.assert_not_called()


async def test_branding_reset_clears_override(session, default_tenant):
    acc = await _make_owner(session, default_tenant.id, tg="223")
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
        text="© will be reset",
        by_account_id=acc.id,
    )
    await session.commit()

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    state = _make_fsm()
    state.get_data = AsyncMock(
        return_value={
            "tenant_id": default_tenant.id,
            "key": "brand.signature",
            "lang": "ru",
        }
    )
    msg = _make_message("223")
    msg.text = "/reset"

    await on_branding_value(msg, state, i18n)

    stored = await get_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
    )
    assert stored is None
    state.clear.assert_awaited_once()


async def test_branding_per_lang_scoping(session, default_tenant):
    """Override saved while owner.lang=ru does not leak to en."""
    await _make_owner(session, default_tenant.id, tg="224")
    i18n_ru = await build_translator(session, default_tenant.id, lang="ru")
    state = _make_fsm()
    state.get_data = AsyncMock(
        return_value={
            "tenant_id": default_tenant.id,
            "key": "start.welcome",
            "lang": "ru",
        }
    )
    msg = _make_message("224")
    msg.text = "Russian welcome"
    await on_branding_value(msg, state, i18n_ru)

    assert (
        await get_branding_text(
            session,
            tenant_id=default_tenant.id,
            key="start.welcome",
            lang="ru",
        )
        == "Russian welcome"
    )
    assert (
        await get_branding_text(
            session,
            tenant_id=default_tenant.id,
            key="start.welcome",
            lang="en",
        )
        is None
    )
