from quantuum.llm.base import LLMResult
from quantuum.llm.blueprint_polish import polish_blueprint


class CaptureLLM:
    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.system = system
        self.user = user
        return LLMResult(text="BP", tokens_in=1, tokens_out=2, model=model)


async def test_polish_blueprint_passes_language():
    client = CaptureLLM()
    result = await polish_blueprint(
        client, "CALC_MD", lang="es", model="m", temperature=0.4, max_tokens=100
    )
    assert result.text == "BP"
    assert "CALC_MD" in client.user
    assert "Answer in language: es." in client.user
