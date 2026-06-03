"""Tests for polish_blueprint — composite orchestrator shape.

The single-LLM-call contract (blueprint_writer.txt system prompt, CALC_MD in
user payload) no longer applies: polish_blueprint now delegates to 8 parallel
polish_reading calls and stitches the results.  The language and model
threading is covered by test_blueprint_compose.py.  This file keeps a focused
smoke-test on the language-pass-through behaviour using the new signature.
"""

import pytest

from quantuum.astrology.blueprint import BlueprintInput
from quantuum.llm.base import LLMResult
from quantuum.llm.blueprint_polish import polish_blueprint


def _sample_input() -> BlueprintInput:
    return BlueprintInput(
        full_name="Test User",
        birth_date="1990-01-01",
        birth_time="12:00",
        birth_place="Moscow",
        latitude=55.75,
        longitude=37.62,
        timezone="Europe/Moscow",
        for_year=2026,
    )


class _CaptureLLM:
    """Records every complete() call; returns a generic LLMResult."""

    def __init__(self):
        self.calls: list[dict] = []

    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.calls.append({"system": system, "user": user, "model": model})
        return LLMResult(text="POLISHED", tokens_in=1, tokens_out=2, model=model)


async def test_polish_blueprint_passes_language_to_all_readings():
    """Language is forwarded to each of the 8 polish_reading calls."""
    inp = _sample_input()
    client = _CaptureLLM()
    result = await polish_blueprint(
        client, "CALC_MD",
        lang="es", model="m", temperature=0.4, max_tokens=100,
        build_input=inp,
    )
    # Exactly 8 parallel polish_reading calls must have been made.
    assert len(client.calls) == 8
    for call in client.calls:
        assert "Spanish" in call["user"] and "native" in call["user"]
    # Stitched result must be a valid composite document.
    assert "Test User" in result.text
    assert "## 🌌 FIELD OVERVIEW" in result.text
    assert result.tokens_in == 8
    assert result.tokens_out == 16
