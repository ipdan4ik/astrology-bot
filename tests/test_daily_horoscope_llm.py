from quantuum.llm.base import LLMResult
from quantuum.llm.daily_horoscope import daily_horoscope


class CaptureLLM:
    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.system = system
        self.user = user
        return LLMResult(text="BLURB", tokens_in=1, tokens_out=2, model=model)


async def test_daily_horoscope_wraps_inputs():
    client = CaptureLLM()
    result = await daily_horoscope(
        client, "NATAL_MD", "TRANSIT_MD", lang="ru",
        model="claude-x", temperature=0.5, max_tokens=300,
    )
    assert result.text == "BLURB"
    assert client.system and "horoscope" in client.system.lower()
    assert "NATAL CHART:" in client.user and "NATAL_MD" in client.user
    assert "TRANSITS:" in client.user and "TRANSIT_MD" in client.user
    assert "Answer in language: ru." in client.user
