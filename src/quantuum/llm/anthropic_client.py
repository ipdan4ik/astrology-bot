import re

import anthropic

from quantuum.llm.base import LLMError, LLMResult

_FENCE_RE = re.compile(r"^```(?:markdown|md)?\s*\n([\s\S]*?)\n```$", re.IGNORECASE | re.DOTALL)


def _strip_markdown_fence(text: str) -> str:
    """Remove a leading/trailing markdown code fence if present."""
    trimmed = text.strip()
    m = _FENCE_RE.match(trimmed)
    return m.group(1).strip() if m else trimmed


class AnthropicClient:
    """Wraps anthropic.AsyncAnthropic.

    The underlying SDK object is stored as ``self._client`` so tests can
    monkeypatch it without making network calls.
    """

    def __init__(self, *, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResult:
        try:
            resp = await self._client.messages.create(
                model=model,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.AnthropicError as exc:
            raise LLMError(str(exc)) from exc
        except Exception as exc:
            raise LLMError(str(exc)) from exc

        raw_text = "".join(
            getattr(block, "text", "")
            for block in resp.content
            if getattr(block, "type", "text") == "text"
        )
        text = _strip_markdown_fence(raw_text)
        return LLMResult(
            text=text,
            model=resp.model,
            tokens_in=resp.usage.input_tokens,
            tokens_out=resp.usage.output_tokens,
        )
