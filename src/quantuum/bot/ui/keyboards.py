from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from quantuum.bot.ui.callbacks import BlueprintCb, HistoryCb, OnboardCb, ProfileCb
from quantuum.i18n import Translator
from quantuum.i18n.seed_strings import BASE_STRINGS

# (i18n keyboard-label key, field name) in display order.
_PROFILE_FIELDS = [
    ("profile.kb.edit_name", "name"),
    ("profile.kb.edit_birth_date", "birth_date"),
    ("profile.kb.edit_birth_time", "birth_time"),
    ("profile.kb.edit_birth_place", "birth_place"),
    ("profile.kb.edit_coords", "coords"),
    ("profile.kb.edit_timezone", "timezone"),
]


def _fallback_ru(key: str) -> str:
    """RU literal for *key* (used when no i18n Translator is supplied)."""
    return BASE_STRINGS[key]["ru"]


async def _label(i18n: Translator | None, key: str) -> str:
    if i18n is None:
        return _fallback_ru(key)
    return await i18n(key)


async def main_menu_kb(i18n: Translator) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text=await i18n("btn.generate"))
    b.button(text=await i18n("btn.ask"))
    b.button(text=await i18n("btn.transits"))
    b.button(text=await i18n("btn.daily"))
    b.button(text=await i18n("btn.profile"))
    b.button(text=await i18n("btn.history"))
    b.button(text=await i18n("btn.help"))
    b.adjust(2, 2, 2, 1)
    return b.as_markup(resize_keyboard=True, is_persistent=True)


async def profile_kb(has_profile: bool, i18n: Translator | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if has_profile:
        for key, field in _PROFILE_FIELDS:
            b.button(
                text=await _label(i18n, key),
                callback_data=ProfileCb(action="edit", field=field),
            )
        b.adjust(2, 2, 2)
    else:
        b.button(
            text=await _label(i18n, "profile.kb.fill"),
            callback_data=OnboardCb(action="start"),
        )
        b.adjust(1)
    return b.as_markup()


async def history_list_kb(
    entries: list, page: int, has_next: bool, i18n: Translator | None = None
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for bp_id, label in entries:
        b.button(text=label, callback_data=HistoryCb(action="open", bp_id=bp_id))
    b.adjust(1)
    pager = InlineKeyboardBuilder()
    if page > 0:
        pager.button(
            text=await _label(i18n, "history.kb.prev_page"),
            callback_data=HistoryCb(action="page", page=page - 1),
        )
    if has_next:
        pager.button(
            text=await _label(i18n, "history.kb.next_page"),
            callback_data=HistoryCb(action="page", page=page + 1),
        )
    if page > 0 or has_next:
        b.attach(pager)
    return b.as_markup()


async def blueprint_detail_kb(
    bp_id: int, can_download: bool, i18n: Translator | None = None
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if can_download:
        b.button(
            text=await _label(i18n, "history.kb.download"),
            callback_data=BlueprintCb(action="download", bp_id=bp_id),
        )
        b.button(
            text=await _label(i18n, "history.kb.preview"),
            callback_data=BlueprintCb(action="preview", bp_id=bp_id),
        )
    b.button(
        text=await _label(i18n, "history.kb.back"),
        callback_data=BlueprintCb(action="back", bp_id=bp_id),
    )
    b.adjust(2, 1)
    return b.as_markup()


async def cancel_kb(i18n: Translator | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=await _label(i18n, "kb.cancel"), callback_data=OnboardCb(action="cancel"))
    return b.as_markup()
