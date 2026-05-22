"""Validation for per-language UI translations. These iterate over whatever
languages are currently present, so they pass before any translation exists and
must stay green as each language file is added."""

import re

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import LANGUAGES


def _tokens(s: str) -> set[str]:
    """The set of ``{placeholder}`` names in a string."""
    return set(re.findall(r"{(\w+)}", s))


def test_translation_files_cover_all_keys():
    base_keys = set(BASE_STRINGS)
    for lang, mapping in LANGUAGES.items():
        assert set(mapping) == base_keys, (
            f"{lang}: translation keys differ from BASE_STRINGS "
            f"(missing={base_keys - set(mapping)}, extra={set(mapping) - base_keys})"
        )


def test_translation_placeholder_parity():
    for lang, mapping in LANGUAGES.items():
        for key, text in mapping.items():
            assert _tokens(text) == _tokens(BASE_STRINGS[key]["en"]), (
                f"{lang}/{key}: placeholder tokens differ from English source"
            )


def test_every_key_has_all_platform_langs():
    from quantuum.i18n.langs import PLATFORM_LANGS

    expected = set(PLATFORM_LANGS)
    for key, langs in BASE_STRINGS.items():
        assert set(langs) == expected, (
            f"{key}: languages {set(langs)} != platform set {expected}"
        )
