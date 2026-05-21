import json
from pathlib import Path

import pytest

from quantuum.astrology.blueprint import BlueprintInput, build_blueprint

FIX = Path(__file__).parent / "fixtures" / "calc"
NAMES = ["anna", "nikita", "regina", "victoria"]


def _load_input(name: str) -> BlueprintInput:
    data = json.loads((FIX / f"{name}.json").read_text())
    return BlueprintInput(
        full_name=data["fullName"],
        birth_date=data["birthDate"],
        birth_time=data["birthTime"],
        birth_place=data.get("birthPlace"),
        latitude=data["latitude"],
        longitude=data["longitude"],
        timezone=data["timezone"],
        for_year=data.get("forYear"),
    )


@pytest.mark.parametrize("name", NAMES)
def test_calc_md_is_character_exact(name):
    expected = (FIX / f"{name}.calc.md").read_text()
    actual = build_blueprint(_load_input(name))
    assert actual == expected
