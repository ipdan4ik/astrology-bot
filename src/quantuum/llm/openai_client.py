import re

import openai

from quantuum.llm.base import LLMError, LLMResult

_FENCE_RE = re.compile(r"^```(?:markdown|md)?\s*\n([\s\S]*?)\n```$", re.IGNORECASE | re.DOTALL)


def _strip_markdown_fence(text: str) -> str:
    """Remove a leading/trailing markdown code fence if present."""
    trimmed = text.strip()
    m = _FENCE_RE.match(trimmed)
    return m.group(1).strip() if m else trimmed


class OpenAIClient:
    """Wraps openai.AsyncOpenAI.

    The underlying SDK object is stored as ``self._client`` so tests can
    monkeypatch it without making network calls.
    """

    def __init__(self, *, api_key: str) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)

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
            resp = await self._client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except openai.OpenAIError as exc:
            raise LLMError(str(exc)) from exc
        except Exception as exc:
            raise LLMError(str(exc)) from exc

        raw_text = resp.choices[0].message.content or ""
        text = _strip_markdown_fence(raw_text)
        usage = resp.usage
        return LLMResult(
            text=text,
            model=resp.model,
            tokens_in=getattr(usage, "prompt_tokens", 0) if usage else 0,
            tokens_out=getattr(usage, "completion_tokens", 0) if usage else 0,
        )
