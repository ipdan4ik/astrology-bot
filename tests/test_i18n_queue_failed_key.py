from quantuum.i18n.seed_strings import BASE_STRINGS

ALL_LANGS = {"ru", "en", "de", "es", "fr", "hi", "it", "pt", "tr", "zh"}


def test_queue_failed_key_present_in_all_langs():
    assert "errors.queue_failed" in BASE_STRINGS
    entry = BASE_STRINGS["errors.queue_failed"]
    assert ALL_LANGS.issubset(entry.keys())
    for lang in ALL_LANGS:
        assert entry[lang].strip(), f"empty translation for {lang}"
