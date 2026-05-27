import pytest

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import de, es, fr, hi, it, pt, tr, zh

REFERRAL_I18N_KEYS = (
    "btn.invite",
    "invite.title",
    "invite.link_label",
    "invite.earned",
    "invite.share_text",
    "invite.disabled",
    "invite.unknown_code",
    "owner.referrals.title",
    "owner.referrals.current_value",
    "owner.referrals.prompt",
    "owner.referrals.saved",
    "owner.referrals.reset",
    "owner.referrals.too_large",
    "owner.referrals.not_a_number",
    "owner.referrals.cancel_hint",
    "owner.referrals.menu_button",
)

LOCALE_MODULES = {
    "de": de,
    "es": es,
    "fr": fr,
    "hi": hi,
    "it": it,
    "pt": pt,
    "tr": tr,
    "zh": zh,
}


@pytest.mark.parametrize("key", REFERRAL_I18N_KEYS)
def test_base_strings_has_ru_en(key: str):
    assert key in BASE_STRINGS, f"missing key {key} in BASE_STRINGS"
    assert "ru" in BASE_STRINGS[key]
    assert "en" in BASE_STRINGS[key]
    assert BASE_STRINGS[key]["ru"].strip()
    assert BASE_STRINGS[key]["en"].strip()


@pytest.mark.parametrize("lang,mod", LOCALE_MODULES.items())
@pytest.mark.parametrize("key", REFERRAL_I18N_KEYS)
def test_locale_module_has_key(key: str, lang: str, mod):
    assert hasattr(mod, "TRANSLATIONS"), f"{lang} module lacks TRANSLATIONS"
    assert key in mod.TRANSLATIONS, f"key {key} missing in {lang} module"
    assert mod.TRANSLATIONS[key].strip()


def test_invite_earned_uses_template_vars():
    assert "{credits}" in BASE_STRINGS["invite.earned"]["ru"]
    assert "{friends}" in BASE_STRINGS["invite.earned"]["ru"]


def test_owner_referrals_current_value_uses_template_var():
    assert "{value}" in BASE_STRINGS["owner.referrals.current_value"]["ru"]


def test_owner_referrals_prompt_uses_max_var():
    assert "{max}" in BASE_STRINGS["owner.referrals.prompt"]["ru"]
