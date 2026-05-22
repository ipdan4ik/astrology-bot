from quantuum.llm.base import LLMResult
from quantuum.llm.qa_answer import qa_answer


class FakeLLM:
    def __init__(self):
        self.calls = []

    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return LLMResult(text="ANSWER", model=model, tokens_in=7, tokens_out=9)


async def test_qa_answer_wraps_chart_and_question():
    fake = FakeLLM()
    res = await qa_answer(
        fake,
        "# Quantuum Blueprint — X",
        "Какое у меня Солнце?",
        lang="ru",
        model="m",
        temperature=0.5,
        max_tokens=900,
    )
    assert res.text == "ANSWER" and res.tokens_in == 7
    call = fake.calls[0]
    assert "CALCULATED CHART:" in call["user"]
    assert "# Quantuum Blueprint — X" in call["user"]
    assert "QUESTION:" in call["user"]
    assert "Какое у меня Солнце?" in call["user"]
    assert call["model"] == "m" and call["max_tokens"] == 900
    # the grounded prompt is loaded as system
    assert len(call["system"]) > 100
    assert "only" in call["system"].lower()  # fact-discipline phrasing present


async def test_qa_answer_passes_language():
    from quantuum.llm.base import LLMResult
    from quantuum.llm.qa_answer import qa_answer

    class CaptureLLM:
        async def complete(self, *, system, user, model, temperature, max_tokens):
            self.user = user
            return LLMResult(text="A", tokens_in=1, tokens_out=2, model=model)

    client = CaptureLLM()
    result = await qa_answer(
        client, "CALC_MD", "What is my path?", lang="it",
        model="m", temperature=0.4, max_tokens=100,
    )
    assert result.text == "A"
    assert "What is my path?" in client.user
    assert "Answer in language: it." in client.user
