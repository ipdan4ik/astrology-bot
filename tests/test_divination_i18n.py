import re

import pytest

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import de, es, fr, hi, it, pt, tr, zh

DIVINATION_KEYS = [
    "readings.kind.tarot", "readings.kind.iching",
    "divination.question_prompt", "divination.question_hint",
    "divination.skip_btn", "divination.no_question",
    "tarot.position.past", "tarot.position.present", "tarot.position.future",
    "tarot.orientation.upright", "tarot.orientation.reversed",
    "iching.judgment_label", "iching.image_label",
    "iching.changing_line_label", "iching.transformed_label",
]

PLACEHOLDERS = {
    "iching.changing_line_label": {"n"},
}

LOCALE_MODULES = {
    "de": de.TRANSLATIONS, "es": es.TRANSLATIONS, "fr": fr.TRANSLATIONS,
    "hi": hi.TRANSLATIONS, "it": it.TRANSLATIONS, "pt": pt.TRANSLATIONS,
    "tr": tr.TRANSLATIONS, "zh": zh.TRANSLATIONS,
}

_PATTERN = re.compile(r"\{(\w+)\}")


@pytest.mark.parametrize("key", DIVINATION_KEYS)
def test_key_present_in_base_strings_ru_en(key):
    assert key in BASE_STRINGS
    assert "ru" in BASE_STRINGS[key] and "en" in BASE_STRINGS[key]


@pytest.mark.parametrize("locale_code, translations", LOCALE_MODULES.items())
@pytest.mark.parametrize("key", DIVINATION_KEYS)
def test_key_present_in_locale(locale_code, translations, key):
    assert key in translations, f"missing in {locale_code}: {key}"


@pytest.mark.parametrize("key, expected", PLACEHOLDERS.items())
def test_placeholder_integrity_base(key, expected):
    for lang in ("ru", "en"):
        found = set(_PATTERN.findall(BASE_STRINGS[key][lang]))
        assert found == expected


@pytest.mark.parametrize("locale_code, translations", LOCALE_MODULES.items())
@pytest.mark.parametrize("key, expected", PLACEHOLDERS.items())
def test_placeholder_integrity_locale(locale_code, translations, key, expected):
    found = set(_PATTERN.findall(translations[key]))
    assert found == expected
