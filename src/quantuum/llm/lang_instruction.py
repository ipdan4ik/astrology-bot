_LANG_NAMES: dict[str, str] = {
    "ru": "Russian",
    "en": "English",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
    "it": "Italian",
    "pt": "Portuguese",
    "tr": "Turkish",
    "zh": "Chinese (Simplified)",
    "hi": "Hindi",
}


def lang_instruction(lang: str) -> str:
    """Return a language instruction line for the LLM user message.

    Uses the full language name and asks for native-quality prose, not a
    translation. Falls back to the raw code if the language is unknown.
    """
    name = _LANG_NAMES.get(lang, lang)
    return (
        f"Write the entire response in {name}. "
        f"Write as a native {name} speaker: natural, idiomatic, fluent. "
        f"Never translate literally from English — adapt phrasing and expressions "
        f"so they feel at home in {name}."
    )
