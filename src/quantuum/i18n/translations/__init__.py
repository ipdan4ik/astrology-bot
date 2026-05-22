"""Per-language UI string translations for the non-base languages.

Each sibling module (e.g. ``es.py``) defines ``TRANSLATIONS: dict[str, str]``
mapping every BASE_STRINGS key to its translation. Modules are auto-discovered,
so adding a new ``<lang>.py`` registers it with no edits here.
"""

import importlib
import pkgutil

LANGUAGES: dict[str, dict[str, str]] = {}

for _info in pkgutil.iter_modules(__path__):
    _mod = importlib.import_module(f"{__name__}.{_info.name}")
    LANGUAGES[_info.name] = _mod.TRANSLATIONS
