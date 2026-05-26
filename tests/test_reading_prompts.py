from quantuum.llm.reading_polish import READING_PROMPTS


def test_every_reading_prompt_requires_field_overview_fragment():
    for kind, path in READING_PROMPTS.items():
        text = path.read_text()
        assert "<!-- field-overview-start -->" in text, f"{kind}: missing fragment start marker contract"
        assert "<!-- field-overview-end -->" in text, f"{kind}: missing fragment end marker contract"
        assert "CRITICAL FACT RULES" in text, f"{kind}: missing CRITICAL FACT RULES block"


def test_every_reading_prompt_demands_language_obedience():
    for kind, path in READING_PROMPTS.items():
        text = path.read_text()
        assert "Write in the language requested" in text, f"{kind}: missing language directive"


def test_every_reading_prompt_forbids_invention():
    for kind, path in READING_PROMPTS.items():
        text = path.read_text()
        assert "Do not invent" in text or "do not invent" in text, f"{kind}: missing invention prohibition"
