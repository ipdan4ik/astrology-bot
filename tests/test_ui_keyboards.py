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


async def test_main_menu_has_localised_buttons(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    await session.commit()
    kb = await main_menu_kb(i18n, default_tenant.id)
    assert set(_reply_texts(kb)) == {
        "❓ Спросить астролога", "🔮 Blueprint", "📖 Разборы", "🔔 Ежедневный гороскоп",
        "👤 Профиль", "📜 История", "ℹ️ Помощь", "🌐 Язык", "🎁 Пригласить друга",
        "💳 Купить",
    }


async def test_main_menu_respects_lang(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id, lang="en")
    await session.commit()
    kb = await main_menu_kb(i18n, default_tenant.id)
    assert set(_reply_texts(kb)) == {
        "❓ Ask the astrologer", "🔮 Blueprint", "📖 Readings", "🔔 Daily horoscope",
        "👤 Profile", "📜 History", "ℹ️ Help", "🌐 Language", "🎁 Invite a friend",
        "💳 Buy",
    }


async def test_profile_kb_with_profile_has_field_edit_buttons(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    kb = await profile_kb(has_profile=True, i18n=i18n)
    fields = {ProfileCb.unpack(b.callback_data).field for b in _inline(kb)}
    assert fields == {"name", "birth_date", "birth_time", "birth_place"}
    labels = {b.text for b in _inline(kb)}
    assert "✏️ Имя" in labels
    assert "✏️ Таймзона" not in labels  # timezone no longer editable


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


async def test_blueprint_detail_kb_back_button_carries_page():
    from quantuum.bot.ui.keyboards import blueprint_detail_kb
    from quantuum.bot.ui.callbacks import BlueprintCb

    kb = await blueprint_detail_kb(5, can_download=False, i18n=None, page=3)
    btns = [b for row in kb.inline_keyboard for b in row]
    back_btn = next(b for b in btns if BlueprintCb.unpack(b.callback_data).action == "back")
    assert BlueprintCb.unpack(back_btn.callback_data).page == 3


async def test_blueprint_detail_kb_back_page_defaults_to_zero():
    from quantuum.bot.ui.keyboards import blueprint_detail_kb
    from quantuum.bot.ui.callbacks import BlueprintCb

    kb = await blueprint_detail_kb(5, can_download=False, i18n=None)
    btns = [b for row in kb.inline_keyboard for b in row]
    back_btn = next(b for b in btns if BlueprintCb.unpack(b.callback_data).action == "back")
    assert BlueprintCb.unpack(back_btn.callback_data).page == 0


def test_btn_gift_has_emoji():
    from quantuum.i18n.seed_strings import BASE_STRINGS
    assert BASE_STRINGS["btn.gift"]["ru"].startswith("🎁"), "ru btn.gift must start with 🎁"
    assert BASE_STRINGS["btn.gift"]["en"].startswith("🎁"), "en btn.gift must start with 🎁"


async def test_main_menu_has_buy_button(session, default_tenant):
    from tests.conftest import build_translator

    i18n = await build_translator(session, default_tenant.id)
    await session.commit()
    kb = await main_menu_kb(i18n, default_tenant.id)
    texts = [b.text for row in kb.keyboard for b in row]
    assert "💳 Купить" in texts
