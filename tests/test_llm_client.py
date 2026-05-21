from quantuum.llm.base import LLMClient, LLMResult
from quantuum.llm.anthropic_client import AnthropicClient
from quantuum.llm.blueprint_polish import polish_blueprint


class FakeLLM:
    def __init__(self):
        self.calls = []

    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.calls.append({"system": system, "user": user, "model": model})
        return LLMResult(text="POLISHED", model=model, tokens_in=11, tokens_out=22)


def test_fake_satisfies_protocol():
    assert isinstance(FakeLLM(), LLMClient)


async def test_polish_blueprint_wraps_calc_md():
    fake = FakeLLM()
    res = await polish_blueprint(fake, "# calc", model="m", temperature=0.1, max_tokens=1000)
    assert res.text == "POLISHED" and res.tokens_in == 11
    call = fake.calls[0]
    assert "CALCULATED MARKDOWN:" in call["user"] and "# calc" in call["user"]
    assert "Quantuum Blueprint Writer" in call["system"]


async def test_anthropic_client_parses_and_strips_fence(monkeypatch):
    client = AnthropicClient(api_key="x")

    class _Block:
        type = "text"
        text = "```markdown\nHELLO\n```"

    class _Resp:
        content = [_Block()]
        usage = type("U", (), {"input_tokens": 5, "output_tokens": 7})()
        model = "claude-x"

    class _Msgs:
        async def create(self, **kw):
            self.kw = kw
            return _Resp()

    fake_sdk = type("C", (), {"messages": _Msgs()})()
    monkeypatch.setattr(client, "_client", fake_sdk)
    res = await client.complete(system="s", user="u", model="claude-x", temperature=0.5, max_tokens=100)
    assert res.text == "HELLO"  # fence stripped
    assert res.tokens_in == 5 and res.tokens_out == 7 and res.model == "claude-x"


def test_registry_returns_none_without_key():
    from quantuum.llm.registry import get_llm_client

    class S:
        llm_provider = "anthropic"
        llm_api_key = ""

    assert get_llm_client(S()) is None


def test_registry_returns_client_with_key():
    from quantuum.llm.registry import get_llm_client
    from quantuum.llm.anthropic_client import AnthropicClient

    class S:
        llm_provider = "anthropic"
        llm_api_key = "sk-test"

    assert isinstance(get_llm_client(S()), AnthropicClient)
