import re

import pytest

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import de, es, fr, hi, it, pt, tr, zh

GIFT_KEYS = [
    "btn.gift", "gift.title", "gift.balance_line", "gift.amount_prompt",
    "gift.cancel_hint", "gift.too_small", "gift.too_large", "gift.not_a_number",
    "gift.no_balance", "gift.created", "gift.share_text", "gift.disabled",
    "gift.received", "gift.self_blocked", "gift.history_title",
    "gift.history_empty", "gift.history_row", "gift.status.active",
    "gift.status.claimed", "gift.status.refunded", "gift.btn.create_new",
    "owner.gifts.menu_button", "owner.gifts.title", "owner.gifts.current_value",
    "owner.gifts.prompt", "owner.gifts.saved", "owner.gifts.reset",
    "owner.gifts.too_small", "owner.gifts.too_large", "owner.gifts.not_a_number",
    "owner.gifts.cancel_hint",
]

PLACEHOLDERS = {
    "gift.balance_line": {"balance"},
    "gift.amount_prompt": {"max"},
    "gift.too_large": {"max"},
    "gift.created": {"amount", "link"},
    "gift.received": {"amount"},
    "gift.history_row": {"date", "amount", "status"},
    "owner.gifts.current_value": {"value"},
    "owner.gifts.prompt": {"min", "max"},
    "owner.gifts.too_small": {"min"},
    "owner.gifts.too_large": {"max"},
}

LOCALE_MODULES = {
    "de": de.TRANSLATIONS, "es": es.TRANSLATIONS, "fr": fr.TRANSLATIONS,
    "hi": hi.TRANSLATIONS, "it": it.TRANSLATIONS, "pt": pt.TRANSLATIONS,
    "tr": tr.TRANSLATIONS, "zh": zh.TRANSLATIONS,
}

_PATTERN = re.compile(r"\{(\w+)\}")


@pytest.mark.parametrize("key", GIFT_KEYS)
def test_key_present_in_base_strings_ru_en(key):
    assert key in BASE_STRINGS, f"missing in BASE_STRINGS: {key}"
    assert "ru" in BASE_STRINGS[key], f"BASE_STRINGS[{key}] missing 'ru'"
    assert "en" in BASE_STRINGS[key], f"BASE_STRINGS[{key}] missing 'en'"


@pytest.mark.parametrize("locale_code, translations", LOCALE_MODULES.items())
@pytest.mark.parametrize("key", GIFT_KEYS)
def test_key_present_in_locale(locale_code, translations, key):
    assert key in translations, f"missing in {locale_code}: {key}"


@pytest.mark.parametrize("key, expected", PLACEHOLDERS.items())
def test_placeholder_integrity_base(key, expected):
    for lang in ("ru", "en"):
        found = set(_PATTERN.findall(BASE_STRINGS[key][lang]))
        assert found == expected, (
            f"BASE_STRINGS[{key}][{lang}] placeholders {found} != {expected}"
        )


@pytest.mark.parametrize("locale_code, translations", LOCALE_MODULES.items())
@pytest.mark.parametrize("key, expected", PLACEHOLDERS.items())
def test_placeholder_integrity_locale(locale_code, translations, key, expected):
    found = set(_PATTERN.findall(translations[key]))
    assert found == expected, (
        f"{locale_code}[{key}] placeholders {found} != {expected}"
    )
