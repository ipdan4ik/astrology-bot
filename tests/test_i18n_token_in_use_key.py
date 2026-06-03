from quantuum.i18n.seed_strings import BASE_STRINGS

ALL_LANGS = {"ru", "en", "de", "es", "fr", "hi", "it", "pt", "tr", "zh"}


def test_token_in_use_key_present_in_all_langs():
    assert "master.onboard.token_in_use" in BASE_STRINGS
    entry = BASE_STRINGS["master.onboard.token_in_use"]
    assert ALL_LANGS.issubset(entry.keys())
    for lang in ALL_LANGS:
        assert entry[lang].strip(), f"empty translation for {lang}"
