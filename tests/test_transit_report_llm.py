from quantuum.llm.base import LLMResult
from quantuum.llm.transit_report import transit_report


class CaptureLLM:
    def __init__(self):
        self.system = None
        self.user = None

    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.system = system
        self.user = user
        self.model = model
        return LLMResult(text="READING", tokens_in=1, tokens_out=2, model=model)


async def test_transit_report_wraps_inputs():
    client = CaptureLLM()
    result = await transit_report(
        client, "NATAL_MD", "TRANSIT_MD", lang="ru",
        model="claude-x", temperature=0.4, max_tokens=1500,
    )
    assert result.text == "READING"
    # System prompt loaded from the file (non-empty, mentions transits).
    assert client.system and "transit" in client.system.lower()
    # User message wraps both groundings + the language line.
    assert "NATAL CHART:" in client.user
    assert "NATAL_MD" in client.user
    assert "TRANSITS:" in client.user
    assert "TRANSIT_MD" in client.user
    assert "Russian" in client.user and "native" in client.user
