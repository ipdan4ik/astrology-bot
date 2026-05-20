from quantuum.bot.ui import text
from quantuum.bot.ui.callbacks import BlueprintCb, HistoryCb, OnboardCb, ProfileCb
from quantuum.bot.ui.keyboards import (
    blueprint_detail_kb,
    cancel_kb,
    history_list_kb,
    main_menu_kb,
    profile_kb,
)


def _reply_texts(kb):
    return [b.text for row in kb.keyboard for b in row]


def _inline(kb):
    return [b for row in kb.inline_keyboard for b in row]


def test_main_menu_has_four_buttons():
    assert set(_reply_texts(main_menu_kb())) == {
        text.BTN_GENERATE, text.BTN_PROFILE, text.BTN_HISTORY, text.BTN_HELP
    }


def test_profile_kb_with_profile_has_field_edit_buttons():
    kb = profile_kb(has_profile=True)
    fields = {ProfileCb.unpack(b.callback_data).field for b in _inline(kb)}
    assert {"name", "birth_date", "birth_time", "birth_place", "coords", "timezone"} <= fields


def test_profile_kb_without_profile_has_fill_button():
    kb = profile_kb(has_profile=False)
    actions = {OnboardCb.unpack(b.callback_data).action for b in _inline(kb)}
    assert "start" in actions


def test_history_list_kb_pager_conditional():
    entries = [(1, "🔮 20.05 · готов"), (2, "🔮 19.05 · готов")]
    kb = history_list_kb(entries, page=0, has_next=True)
    datas = [b.callback_data for b in _inline(kb)]
    assert any(HistoryCb.unpack(d) == HistoryCb(action="open", bp_id=1) for d in datas)
    assert any(HistoryCb.unpack(d) == HistoryCb(action="page", page=1) for d in datas)
    assert not any(HistoryCb.unpack(d).action == "page" and HistoryCb.unpack(d).page == -1 for d in datas)


def test_blueprint_detail_kb_download_only_when_available():
    with_dl = [BlueprintCb.unpack(b.callback_data).action for b in _inline(blueprint_detail_kb(5, can_download=True))]
    assert "download" in with_dl and "back" in with_dl
    without = [BlueprintCb.unpack(b.callback_data).action for b in _inline(blueprint_detail_kb(5, can_download=False))]
    assert "download" not in without and "back" in without


def test_cancel_kb():
    actions = [OnboardCb.unpack(b.callback_data).action for b in _inline(cancel_kb())]
    assert actions == ["cancel"]
