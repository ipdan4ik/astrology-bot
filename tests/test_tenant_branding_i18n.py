import pytest

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import de, es, fr, hi, it, pt, tr, zh

BRANDING_I18N_KEYS = [
    "brand.signature",
    "owner.branding.btn",
    "owner.branding.title",
    "owner.branding.label.name",
    "owner.branding.label.welcome",
    "owner.branding.label.help",
    "owner.branding.label.signature",
    "owner.branding.prompt",
    "owner.branding.saved",
    "owner.branding.reset_done",
    "owner.branding.cancelled",
    "owner.branding.too_long",
    "owner.branding.bad_format",
    "owner.branding.empty_value",
    "owner.branding.preview_empty",
]


@pytest.mark.parametrize("key", BRANDING_I18N_KEYS)
def test_base_strings_has_key_in_ru_and_en(key):
    assert key in BASE_STRINGS, f"missing {key} in BASE_STRINGS"
    entry = BASE_STRINGS[key]
    assert "ru" in entry, f"missing ru for {key}"
    assert "en" in entry, f"missing en for {key}"


@pytest.mark.parametrize(
    "lang_mod, lang_code",
    [(de, "de"), (es, "es"), (fr, "fr"), (hi, "hi"), (it, "it"), (pt, "pt"), (tr, "tr"), (zh, "zh")],
)
@pytest.mark.parametrize("key", BRANDING_I18N_KEYS)
def test_translation_modules_have_all_keys(lang_mod, lang_code, key):
    # brand.signature is intentionally seeded as empty string; assert key presence only.
    assert key in lang_mod.TRANSLATIONS, f"missing {key} in {lang_code}"
    if key != "brand.signature":
        assert lang_mod.TRANSLATIONS[key], f"empty {key} in {lang_code}"
