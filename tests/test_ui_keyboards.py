from quantuum.bot.ui.callbacks import BlueprintCb, HistoryCb, OnboardCb, ProfileCb
from quantuum.bot.ui.keyboards import (
    blueprint_detail_kb,
    cancel_kb,
    history_list_kb,
    main_menu_kb,
    profile_kb,
)

from .conftest import build_translator


def _reply_texts(kb):
    return [b.text for row in kb.keyboard for b in row]


def _inline(kb):
    return [b for row in kb.inline_keyboard for b in row]


async def test_main_menu_has_four_localised_buttons(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    kb = await main_menu_kb(i18n)
    assert set(_reply_texts(kb)) == {
        "🔮 Разбор", "👤 Профиль", "📜 История", "ℹ️ Помощь"
    }


async def test_main_menu_respects_lang(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id, lang="en")
    kb = await main_menu_kb(i18n)
    assert set(_reply_texts(kb)) == {
        "🔮 Reading", "👤 Profile", "📜 History", "ℹ️ Help"
    }


async def test_profile_kb_with_profile_has_field_edit_buttons(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    kb = await profile_kb(has_profile=True, i18n=i18n)
    fields = {ProfileCb.unpack(b.callback_data).field for b in _inline(kb)}
    assert {"name", "birth_date", "birth_time", "birth_place", "coords", "timezone"} <= fields
    # Labels resolved via i18n (ru)
    labels = {b.text for b in _inline(kb)}
    assert "✏️ Имя" in labels and "✏️ Таймзона" in labels


async def test_profile_kb_without_profile_has_fill_button(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    kb = await profile_kb(has_profile=False, i18n=i18n)
    actions = {OnboardCb.unpack(b.callback_data).action for b in _inline(kb)}
    assert "start" in actions
    assert {b.text for b in _inline(kb)} == {"📝 Заполнить профиль"}


async def test_history_list_kb_pager_conditional():
    entries = [(1, "🔮 20.05 · готов"), (2, "🔮 19.05 · готов")]
    kb = await history_list_kb(entries, page=0, has_next=True, i18n=None)
    datas = [b.callback_data for b in _inline(kb)]
    assert any(HistoryCb.unpack(d) == HistoryCb(action="open", bp_id=1) for d in datas)
    assert any(HistoryCb.unpack(d) == HistoryCb(action="page", page=1) for d in datas)
    assert not any(HistoryCb.unpack(d).action == "page" and HistoryCb.unpack(d).page == -1 for d in datas)


async def test_blueprint_detail_kb_download_only_when_available():
    with_dl = [BlueprintCb.unpack(b.callback_data).action for b in _inline(await blueprint_detail_kb(5, can_download=True, i18n=None))]
    assert "download" in with_dl and "back" in with_dl
    without = [BlueprintCb.unpack(b.callback_data).action for b in _inline(await blueprint_detail_kb(5, can_download=False, i18n=None))]
    assert "download" not in without and "back" in without


async def test_cancel_kb_localised(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    kb = await cancel_kb(i18n)
    btns = _inline(kb)
    assert [OnboardCb.unpack(b.callback_data).action for b in btns] == ["cancel"]
    assert [b.text for b in btns] == ["✖️ Отмена"]


async def test_cancel_kb_no_i18n_falls_back_to_ru():
    # Backwards-compatible call (onboarding flow) keeps RU literal without i18n.
    kb = await cancel_kb()
    btns = _inline(kb)
    assert [b.text for b in btns] == ["✖️ Отмена"]
