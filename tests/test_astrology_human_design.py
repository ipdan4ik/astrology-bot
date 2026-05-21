from datetime import datetime, timedelta, timezone

from quantuum.astrology.human_design import (
    Channel,
    OrderedCenterSet,
    calculate_human_design,
    determine_type,
)

ANNA = datetime(1980, 6, 24, 7, 0, 0, tzinfo=timezone.utc)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _iso_z(ms: int) -> str:
    dt = EPOCH + timedelta(milliseconds=ms)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def test_anna_hd_summary():
    hd = calculate_human_design(ANNA)
    assert hd.type == "Generator"
    assert hd.strategy == "Wait to respond"
    assert hd.authority == "Solar Plexus (Emotional)"
    assert hd.profile == "5/2"
    assert hd.definition.kind == "Triple-Split Definition"
    assert hd.signature == "Satisfaction"
    assert hd.not_self == "Frustration"
    assert list(hd.defined_centers) == [
        "Solar Plexus",
        "Sacral",
        "G",
        "Spleen",
        "Ajna",
        "Throat",
    ]
    assert sorted(hd.active_gates) == [
        1, 4, 6, 10, 11, 14, 15, 17, 18, 23, 26, 29, 30, 32,
        37, 43, 45, 47, 49, 56, 57, 59, 62,
    ]
    assert hd.variables.right_left_mind == "Right"
    assert hd.variables.right_left_body == "Left"
    assert hd.incarnation_cross.name == "Right Angle Cross of (15/10 | 17/18)"


def test_anna_design_date_iso_millisecond_exact():
    hd = calculate_human_design(ANNA)
    assert _iso_z(hd.design_ms) == "1980-03-25T09:57:09.855Z"


def test_anna_activations():
    hd = calculate_human_design(ANNA)
    assert hd.personality[0].body == "Sun"
    assert hd.personality[0].gate == 15
    assert hd.personality[0].line == 5
    assert hd.personality[1].body == "Earth"
    assert hd.personality[1].gate == 10
    assert hd.personality[1].line == 5
    assert hd.design[0].body == "Sun"
    assert hd.design[0].gate == 17
    assert hd.design[0].line == 2


def test_anna_active_channels():
    hd = calculate_human_design(ANNA)
    chans = [(tuple(ch.gates), ch.name) for ch in hd.active_channels]
    assert ((6, 59), "Mating") in chans
    assert ((10, 57), "Perfected Form") in chans
    assert ((11, 56), "Curiosity") in chans
    assert ((17, 62), "Acceptance") in chans
    assert ((23, 43), "Structuring") in chans
    assert len(hd.active_channels) == 5


def test_determine_type_reflector():
    # Empty defined-centers set with no channels → Reflector
    defined = OrderedCenterSet()
    assert determine_type(defined, []) == "Reflector"


def test_determine_type_projector():
    # Defined centers without Sacral and without a motor→Throat connection → Projector.
    # Channel (4, 63) connects Ajna–Head; neither is a Motor and neither is Throat.
    defined = OrderedCenterSet()
    defined.add("Ajna")
    defined.add("Head")
    channels = [Channel((4, 63), "Logic")]
    assert determine_type(defined, channels) == "Projector"
