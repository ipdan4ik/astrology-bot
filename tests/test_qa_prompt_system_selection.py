from pathlib import Path

PROMPT = Path(__file__).resolve().parent.parent / "src" / "quantuum" / "llm" / "prompts" / "qa_astrologer.txt"


def test_qa_prompt_has_system_selection_block():
    text = PROMPT.read_text()
    assert "SYSTEM SELECTION" in text
    assert "BaZi" in text and "numerology" in text and "Human Design" in text
    assert "If the question explicitly names a system" in text
