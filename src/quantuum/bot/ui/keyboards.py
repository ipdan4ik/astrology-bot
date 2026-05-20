from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from quantuum.bot.ui import text
from quantuum.bot.ui.callbacks import BlueprintCb, HistoryCb, OnboardCb, ProfileCb

_PROFILE_FIELDS = [
    ("Имя", "name"),
    ("Дата", "birth_date"),
    ("Время", "birth_time"),
    ("Место", "birth_place"),
    ("Координаты", "coords"),
    ("Таймзона", "timezone"),
]


def main_menu_kb() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text=text.BTN_GENERATE)
    b.button(text=text.BTN_PROFILE)
    b.button(text=text.BTN_HISTORY)
    b.button(text=text.BTN_HELP)
    b.adjust(2, 2)
    return b.as_markup(resize_keyboard=True, is_persistent=True)


def profile_kb(has_profile: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if has_profile:
        for label, field in _PROFILE_FIELDS:
            b.button(text=f"✏️ {label}", callback_data=ProfileCb(action="edit", field=field))
        b.adjust(2, 2, 2)
    else:
        b.button(text="📝 Заполнить профиль", callback_data=OnboardCb(action="start"))
        b.adjust(1)
    return b.as_markup()


def history_list_kb(entries: list, page: int, has_next: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for bp_id, label in entries:
        b.button(text=label, callback_data=HistoryCb(action="open", bp_id=bp_id))
    b.adjust(1)
    pager = InlineKeyboardBuilder()
    if page > 0:
        pager.button(text="← Пред", callback_data=HistoryCb(action="page", page=page - 1))
    if has_next:
        pager.button(text="След →", callback_data=HistoryCb(action="page", page=page + 1))
    if page > 0 or has_next:
        b.attach(pager)
    return b.as_markup()


def blueprint_detail_kb(bp_id: int, can_download: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if can_download:
        b.button(text="📥 Скачать .md", callback_data=BlueprintCb(action="download", bp_id=bp_id))
        b.button(text="👁 Превью", callback_data=BlueprintCb(action="preview", bp_id=bp_id))
    b.button(text="← Назад", callback_data=BlueprintCb(action="back", bp_id=bp_id))
    b.adjust(2, 1)
    return b.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✖️ Отмена", callback_data=OnboardCb(action="cancel"))
    return b.as_markup()
