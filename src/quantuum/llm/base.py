from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int


class LLMError(RuntimeError):
    pass


@runtime_checkable
class LLMClient(Protocol):
    async def complete(
        self, *, system: str, user: str, model: str, temperature: float, max_tokens: int
    ) -> LLMResult: ...
