from quantuum.i18n.seed_strings import BASE_STRINGS

ALL_LANGS = {"ru", "en", "de", "es", "fr", "hi", "it", "pt", "tr", "zh"}
KEYS = [
    "owner.manage.kb.back",
    "owner.features.label.referrals",
    "owner.features.label.gifts",
    "master.provision.manual_prompt",
    "master.provision.managed_prompt",
    "master.provision.managed_button",
]


def test_console_ux_keys_present_in_all_langs():
    for key in KEYS:
        assert key in BASE_STRINGS, key
        for lang in ALL_LANGS:
            assert BASE_STRINGS[key].get(lang, "").strip(), f"{key}/{lang}"
