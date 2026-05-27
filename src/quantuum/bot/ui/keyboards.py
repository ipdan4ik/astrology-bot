from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from quantuum.bot.ui.callbacks import BlueprintCb, HistoryCb, LangCb, OnboardCb, ProfileCb, ReadingCb
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenant_features import list_feature_states
from quantuum.i18n import Translator
from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.strings import get_enabled_langs, get_tenant_default_lang

# (i18n keyboard-label key, field name) in display order.
_PROFILE_FIELDS = [
    ("profile.kb.edit_name", "name"),
    ("profile.kb.edit_birth_date", "birth_date"),
    ("profile.kb.edit_birth_time", "birth_time"),
    ("profile.kb.edit_birth_place", "birth_place"),
]

# Native language names for the picker. NOT i18n keys — native names are the same
# in every language and must not be translated. Falls back to the uppercased code.
LANG_LABELS = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
    "es": "🇪🇸 Español",
    "fr": "🇫🇷 Français",
    "pt": "🇵🇹 Português",
    "it": "🇮🇹 Italiano",
    "de": "🇩🇪 Deutsch",
    "tr": "🇹🇷 Türkçe",
    "zh": "🇨🇳 中文",
    "hi": "🇮🇳 हिन्दी",
}


def _fallback_ru(key: str) -> str:
    """RU literal for *key* (used when no i18n Translator is supplied)."""
    return BASE_STRINGS[key]["ru"]


async def _label(i18n: Translator | None, key: str) -> str:
    if i18n is None:
        return _fallback_ru(key)
    return await i18n(key)


async def main_menu_kb(i18n: Translator, tenant_id: int) -> ReplyKeyboardMarkup:
    async with get_sessionmaker()() as session:
        flags = await list_feature_states(session, tenant_id)

    show_readings = any(
        enabled for k, enabled in flags.items() if k.startswith("reading.")
    )

    b = ReplyKeyboardBuilder()
    count = 0

    def _add(text: str) -> None:
        nonlocal count
        b.button(text=text)
        count += 1

    if flags.get("blueprint", True):
        _add(await i18n("btn.generate"))
    if flags.get("qa", True):
        _add(await i18n("btn.ask"))
    if show_readings:
        _add(await i18n("btn.readings"))
    if flags.get("transits", True):
        _add(await i18n("btn.transits"))
    if flags.get("daily", True):
        _add(await i18n("btn.daily"))

    _add(await i18n("btn.profile"))
    _add(await i18n("btn.history"))
    _add(await i18n("btn.help"))
    _add(await i18n("btn.language"))

    layout: list[int] = []
    remaining = count
    while remaining >= 2:
        layout.append(2)
        remaining -= 2
    if remaining:
        layout.append(1)
    if layout:
        b.adjust(*layout)
    return b.as_markup(resize_keyboard=True, is_persistent=True)


async def language_picker_kb(tenant_id: int, *, action: str) -> InlineKeyboardMarkup:
    """Inline picker of the tenant's enabled languages, default lang first.

    Owns its own DB session (no session is injected into handlers). *action* is
    "setup" (first-entry flow) or "set" (menu change), carried in the callback.
    """
    async with get_sessionmaker()() as session:
        enabled = await get_enabled_langs(session, tenant_id)
        default = await get_tenant_default_lang(session, tenant_id)
    if default in enabled:
        ordered = [default, *sorted(c for c in enabled if c != default)]
    else:
        ordered = sorted(enabled)
    b = InlineKeyboardBuilder()
    for code in ordered:
        b.button(
            text=LANG_LABELS.get(code, code.upper()),
            callback_data=LangCb(action=action, lang=code),
        )
    b.adjust(2)
    return b.as_markup()


READING_KINDS: tuple[str, ...] = (
    "bazi", "numerology", "human_design", "astrology",
    "vedic", "gene_keys", "mayan", "aspects",
)


async def readings_menu_kb(i18n: Translator, tenant_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard listing only the enabled reading kinds for this tenant."""
    async with get_sessionmaker()() as session:
        flags = await list_feature_states(session, tenant_id)

    b = InlineKeyboardBuilder()
    visible: list[str] = [k for k in READING_KINDS if flags.get(f"reading.{k}", True)]
    for kind in visible:
        label = await i18n(f"readings.kind.{kind}")
        b.button(text=label, callback_data=ReadingCb(action="generate", kind=kind))

    if visible:
        layout: list[int] = []
        remaining = len(visible)
        while remaining >= 2:
            layout.append(2)
            remaining -= 2
        if remaining:
            layout.append(1)
        b.adjust(*layout)
    return b.as_markup()


async def profile_kb(has_profile: bool, i18n: Translator | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if has_profile:
        for key, field in _PROFILE_FIELDS:
            b.button(
                text=await _label(i18n, key),
                callback_data=ProfileCb(action="edit", field=field),
            )
        b.adjust(2, 2)
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
