from quantuum.llm.reading_polish import _KIND_LABEL, READING_PROMPTS


def test_tarot_and_iching_registered():
    assert "tarot" in READING_PROMPTS
    assert "iching" in READING_PROMPTS
    assert "tarot" in _KIND_LABEL
    assert "iching" in _KIND_LABEL


def test_prompt_files_exist():
    assert READING_PROMPTS["tarot"].is_file()
    assert READING_PROMPTS["iching"].is_file()
