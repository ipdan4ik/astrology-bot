import pytest

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import de, es, fr, hi, it, pt, tr, zh

MODERATION_KEYS = [
    "moderation.self_harm",
    "moderation.violence",
    "moderation.hate",
    "moderation.medical",
    "moderation.legal",
    "moderation.blocked_generic",
    "moderation.helpline_url",
]


@pytest.mark.parametrize("key", MODERATION_KEYS)
def test_base_strings_has_key_in_ru_and_en(key):
    assert key in BASE_STRINGS, f"missing {key} in BASE_STRINGS"
    entry = BASE_STRINGS[key]
    assert "ru" in entry and "en" in entry
    assert entry["ru"] and entry["en"]


@pytest.mark.parametrize(
    "lang_mod, lang_code",
    [(de, "de"), (es, "es"), (fr, "fr"), (hi, "hi"), (it, "it"), (pt, "pt"), (tr, "tr"), (zh, "zh")],
)
@pytest.mark.parametrize("key", MODERATION_KEYS)
def test_translation_modules_have_all_keys(lang_mod, lang_code, key):
    assert key in lang_mod.TRANSLATIONS, f"missing {key} in {lang_code}"
    assert lang_mod.TRANSLATIONS[key], f"empty {key} in {lang_code}"


def test_self_harm_message_contains_helpline_placeholder():
    assert "{helpline_url}" in BASE_STRINGS["moderation.self_harm"]["ru"]
    assert "{helpline_url}" in BASE_STRINGS["moderation.self_harm"]["en"]


def test_helpline_url_identical_across_locales():
    url = BASE_STRINGS["moderation.helpline_url"]["en"]
    assert url.startswith("https://")
    for mod in (de, es, fr, hi, it, pt, tr, zh):
        assert mod.TRANSLATIONS["moderation.helpline_url"] == url
