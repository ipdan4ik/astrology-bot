import pytest

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import de, es, fr, hi, it, pt, tr, zh

FEATURE_I18N_KEYS = [
    "feature.disabled_generic",
    "owner.features.title",
    "owner.features.btn",
    "owner.features.section.readings",
    "owner.features.label.qa",
    "owner.features.label.blueprint",
    "owner.features.label.transits",
    "owner.features.label.daily",
]


@pytest.mark.parametrize("key", FEATURE_I18N_KEYS)
def test_base_strings_has_key_in_ru_and_en(key):
    assert key in BASE_STRINGS, f"missing {key} in BASE_STRINGS"
    entry = BASE_STRINGS[key]
    assert "ru" in entry and "en" in entry
    assert entry["ru"] and entry["en"]


@pytest.mark.parametrize(
    "lang_mod, lang_code",
    [(de, "de"), (es, "es"), (fr, "fr"), (hi, "hi"), (it, "it"), (pt, "pt"), (tr, "tr"), (zh, "zh")],
)
@pytest.mark.parametrize("key", FEATURE_I18N_KEYS)
def test_translation_modules_have_all_keys(lang_mod, lang_code, key):
    assert key in lang_mod.TRANSLATIONS, f"missing {key} in {lang_code}"
    assert lang_mod.TRANSLATIONS[key], f"empty {key} in {lang_code}"
