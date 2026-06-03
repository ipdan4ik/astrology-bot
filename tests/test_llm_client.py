from quantuum.llm.base import LLMClient, LLMResult
from quantuum.llm.blueprint_polish import polish_blueprint
from quantuum.llm.openai_client import OpenAIClient, _strip_markdown_fence


class FakeLLM:
    def __init__(self):
        self.calls = []

    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.calls.append({"system": system, "user": user, "model": model})
        return LLMResult(text="POLISHED", model=model, tokens_in=11, tokens_out=22)


def test_fake_satisfies_protocol():
    assert isinstance(FakeLLM(), LLMClient)


async def test_polish_blueprint_composes_eight_reading_polishes():
    from quantuum.astrology.blueprint import BlueprintInput

    inp = BlueprintInput(
        full_name="Test", birth_date="1990-08-15", birth_time="14:30",
        birth_place="X", latitude=55.7558, longitude=37.6173,
        timezone="Europe/Moscow", for_year=2026,
    )
    fake = FakeLLM()
    res = await polish_blueprint(
        fake, "irrelevant", lang="en", model="m",
        temperature=0.1, max_tokens=1000, build_input=inp,
    )
    # 8 section polishes, one LLM call each
    assert len(fake.calls) == 8
    # Aggregated token counts (FakeLLM returns 11/22 per call)
    assert res.tokens_in == 11 * 8
    assert res.tokens_out == 22 * 8
    # Stitched output includes the ceremonial header and field overview
    assert "Test — QUANTUUM SOULMAP BLUEPRINT" in res.text
    assert "## 🌌 FIELD OVERVIEW" in res.text
    # Language was forwarded to every call
    for call in fake.calls:
        assert "English" in call["user"] and "native" in call["user"]


async def test_openai_client_parses_and_strips_fence(monkeypatch):
    client = OpenAIClient(api_key="x")

    class _Msg:
        content = "```markdown\nHELLO\n```"

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]
        usage = type("U", (), {"prompt_tokens": 5, "completion_tokens": 7})()
        model = "gpt-4o"

    class _Completions:
        async def create(self, **kw):
            self.kw = kw
            return _Resp()

    class _Chat:
        completions = _Completions()

    fake_sdk = type("C", (), {"chat": _Chat()})()
    monkeypatch.setattr(client, "_client", fake_sdk)
    res = await client.complete(system="s", user="u", model="gpt-4o", temperature=0.5, max_tokens=100)
    assert res.text == "HELLO"  # fence stripped
    assert res.tokens_in == 5 and res.tokens_out == 7 and res.model == "gpt-4o"


async def test_openai_client_sends_system_and_user_messages(monkeypatch):
    client = OpenAIClient(api_key="x")
    captured = {}

    class _Msg:
        content = "OK"

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]
        usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 2})()
        model = "gpt-4o"

    class _Completions:
        async def create(self, **kw):
            captured.update(kw)
            return _Resp()

    class _Chat:
        completions = _Completions()

    monkeypatch.setattr(client, "_client", type("C", (), {"chat": _Chat()})())
    await client.complete(system="SYS", user="USR", model="gpt-4o", temperature=0.3, max_tokens=50)
    assert captured["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USR"},
    ]
    assert captured["model"] == "gpt-4o"
    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 50


def test_strip_markdown_fence_variants():
    # uppercase fence tag
    assert _strip_markdown_fence("```MARKDOWN\nHELLO\n```") == "HELLO"
    # trailing spaces after tag
    assert _strip_markdown_fence("```markdown  \nHELLO\n```") == "HELLO"
    # inner whitespace trimmed
    assert _strip_markdown_fence("```markdown\n  HELLO  \n```") == "HELLO"
    # non-fenced text stripped
    assert _strip_markdown_fence("  plain text  ") == "plain text"


def test_registry_returns_none_without_key():
    from quantuum.llm.registry import get_llm_client

    class S:
        llm_provider = "openai"
        llm_api_key = ""

    assert get_llm_client(S()) is None


def test_registry_returns_client_with_key():
    from quantuum.llm.openai_client import OpenAIClient
    from quantuum.llm.registry import get_llm_client

    class S:
        llm_provider = "openai"
        llm_api_key = "sk-test"

    assert isinstance(get_llm_client(S()), OpenAIClient)
