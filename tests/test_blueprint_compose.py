from dataclasses import dataclass

import pytest

from quantuum.astrology.blueprint import BlueprintInput
from quantuum.llm.blueprint_polish import polish_blueprint


@dataclass
class _R:
    text: str
    model: str = "m"
    tokens_in: int = 5
    tokens_out: int = 9


class _Fake:
    def __init__(self):
        self.calls = []

    async def complete(self, *, system, user, **kw):
        self.calls.append({"system": system, "user": user})
        for kind_label, marker in [
            ("BaZi", "BaZi"),
            ("Numerology", "Numerology"),
            ("Gene Keys", "Gene Keys"),
            ("Human Design", "Human Design"),
            ("Tropical", "Tropical"),
            ("Vedic", "Vedic"),
            ("Mayan", "Mayan"),
            ("Aspects", "Aspects"),
        ]:
            if marker in user:
                body = (
                    "<!-- field-overview-start -->\n"
                    f"| {kind_label} | sample |\n"
                    "<!-- field-overview-end -->\n"
                    f"## section body for {kind_label}\n"
                    "content here"
                )
                return _R(text=body)
        return _R(text="?")


def _sample() -> BlueprintInput:
    return BlueprintInput(
        full_name="Desmond Test",
        birth_date="1990-08-15",
        birth_time="14:30",
        birth_place="Moscow, RU",
        latitude=55.7558,
        longitude=37.6173,
        timezone="Europe/Moscow",
        for_year=2026,
    )


async def test_polish_blueprint_runs_eight_polishes_and_stitches():
    inp = _sample()
    client = _Fake()
    calc_md = "irrelevant for this test"
    result = await polish_blueprint(client, calc_md, lang="en",
                                    model="m", temperature=0.5, max_tokens=1000,
                                    build_input=inp)
    assert len(client.calls) == 8
    text = result.text
    assert "Desmond Test" in text
    for marker in ["BaZi", "Numerology", "Human Design", "Tropical",
                   "Vedic", "Gene Keys", "Mayan", "Aspects"]:
        assert f"section body for {marker}" in text
    # Fragments stripped from sections and merged at top of overview block
    assert "<!-- field-overview-start -->" not in text
    assert "## 🌌 FIELD OVERVIEW" in text
    assert result.tokens_in == 5 * 8
    assert result.tokens_out == 9 * 8


async def test_polish_blueprint_one_section_failure_propagates():
    inp = _sample()

    class _Flaky(_Fake):
        async def complete(self, *, system, user, **kw):
            if "BaZi" in user:
                raise RuntimeError("LLM down on BaZi")
            return await super().complete(system=system, user=user, **kw)

    with pytest.raises(RuntimeError):
        await polish_blueprint(_Flaky(), "x", lang="en", model="m",
                               temperature=0.5, max_tokens=1000, build_input=inp)
