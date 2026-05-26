import pytest

from quantuum.llm.reading_polish import READING_PROMPTS, polish_reading


class _FakeClient:
    def __init__(self):
        self.calls = []
    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.calls.append({"system": system, "user": user, "model": model})
        class R:
            text = "POLISHED"
            tokens_in = 10
            tokens_out = 20
        R.model = model
        return R()


@pytest.mark.parametrize("kind", list(READING_PROMPTS.keys()))
async def test_polish_reading_uses_per_kind_prompt(kind):
    client = _FakeClient()
    calc = f"# Stub calc for {kind}"
    result = await polish_reading(client, kind, calc, lang="en",
                                  model="m", temperature=0.5, max_tokens=1000)
    assert result.text == "POLISHED"
    call = client.calls[0]
    assert call["system"] == READING_PROMPTS[kind].read_text()
    assert "Answer in language: en." in call["user"]
    assert calc in call["user"]


async def test_polish_reading_unknown_kind_raises():
    with pytest.raises(KeyError):
        await polish_reading(_FakeClient(), "unknown", "x", lang="en",
                             model="m", temperature=0.5, max_tokens=1000)


def test_all_eight_kinds_registered():
    assert set(READING_PROMPTS.keys()) == {
        "bazi", "numerology", "human_design", "astrology",
        "vedic", "gene_keys", "mayan", "aspects",
    }
