"""Human Design calculator.

Ported from humandesign.ts — behavior must match exactly.

HD treats the ecliptic as a 64-gate wheel (5.625 deg per gate), starting at
02 deg 00' Aquarius (= 302 deg tropical) with Gate 41. Each gate is divided
into 6 lines (0.9375 deg each), then each line into 6 colors, 6 tones, 5 bases.

The "Personality" chart is computed from positions at the moment of birth.
The "Design" chart is computed at the moment when the Sun was 88 solar degrees
earlier — so we iterate to find the precise time.

JS->Python parity notes:
- find_sun_longitude_time iterates on INTEGER epoch-milliseconds, matching the
  JS `new Date(t.getTime() + dDays * 86400000)` which truncates the float to an
  integer instant toward zero. Use int() (truncation), not round(), inside the
  loop.
- defined_centers is INSERTION-ORDERED (JS Set semantics). It is built by
  iterating active_channels in order, adding GATE_TO_CENTER[gates[0]] then
  GATE_TO_CENTER[gates[1]], deduping while preserving first-insertion order.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from .astro import (
    ecliptic_longitude,
    mean_lunar_node_longitude,
)
from .util import norm360

# 64 gates around the wheel, in order starting at 302 deg (Gate 41).
GATE_ORDER = (
    41, 19, 13, 49, 30, 55, 37, 63, 22, 36,
    25, 17, 21, 51, 42, 3, 27, 24, 2, 23,
    8, 20, 16, 35, 45, 12, 15, 52, 39, 53,
    62, 56, 31, 33, 7, 4, 29, 59, 40, 64,
    47, 6, 46, 18, 48, 57, 32, 50, 28, 44,
    1, 43, 14, 34, 9, 5, 26, 11, 10, 58,
    38, 54, 61, 60,
)

GATE_START = 302  # 2 deg 00' Aquarius (Aquarius starts at 300 deg)
GATE_SIZE = 360 / 64  # 5.625
LINE_SIZE = GATE_SIZE / 6  # 0.9375
COLOR_SIZE = LINE_SIZE / 6
TONE_SIZE = COLOR_SIZE / 6
BASE_SIZE = TONE_SIZE / 5

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass
class GateActivation:
    gate: int
    line: int  # 1-6
    color: int  # 1-6
    tone: int  # 1-6
    base: int  # 1-5
    longitude: float


def longitude_to_gate(longitude: float) -> GateActivation:
    lon = norm360(longitude)
    offset = norm360(lon - GATE_START)
    idx = math.floor(offset / GATE_SIZE)
    gate = GATE_ORDER[idx]
    into_gate = offset - idx * GATE_SIZE
    line = math.floor(into_gate / LINE_SIZE) + 1
    into_line = into_gate - (line - 1) * LINE_SIZE
    color = math.floor(into_line / COLOR_SIZE) + 1
    into_color = into_line - (color - 1) * COLOR_SIZE
    tone = math.floor(into_color / TONE_SIZE) + 1
    into_tone = into_color - (tone - 1) * TONE_SIZE
    base = min(5, math.floor(into_tone / BASE_SIZE) + 1)
    return GateActivation(
        gate=gate, line=line, color=color, tone=tone, base=base, longitude=lon
    )


def _from_ms(ms: int) -> datetime:
    return _EPOCH + timedelta(milliseconds=ms)


def _to_ms(dt: datetime) -> int:
    return round((dt.astimezone(timezone.utc) - _EPOCH).total_seconds() * 1000)


def find_sun_longitude_time(birth_ms: int, target_lon: float) -> int:
    """Return integer epoch-ms when the Sun's ecliptic longitude == target_lon.

    Sun moves ~0.9856 deg/day, so 88 deg ~= 89.3 days. Start from -89 days.
    The integer-ms truncation matches JS `new Date(float)` exactly.
    """
    t_ms = birth_ms - 89 * 86400000
    for _ in range(30):
        lon = ecliptic_longitude("Sun", _from_ms(t_ms))
        diff = ((target_lon - lon + 540) % 360) - 180  # signed
        if abs(diff) < 1e-7:
            break
        # dlambda/dt ~= 0.9856 deg/day
        d_days = diff / 0.9856
        t_ms = int(t_ms + d_days * 86400000)  # int() truncates toward zero == JS new Date(float)
    return t_ms


# Bodies tracked in HD chart (geocentric apparent positions).
# "Earth" is exactly 180 deg from the Sun. "South Node" is 180 deg from North Node.
HD_BODIES = (
    "Sun",
    "Earth",
    "Moon",
    "NorthNode",
    "SouthNode",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
)
HdBody = Literal[
    "Sun",
    "Earth",
    "Moon",
    "NorthNode",
    "SouthNode",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
]


def body_longitude(body: HdBody, date: datetime) -> float:
    if body == "Earth":
        return norm360(ecliptic_longitude("Sun", date) + 180)
    if body == "NorthNode":
        return mean_lunar_node_longitude(date)
    if body == "SouthNode":
        return norm360(mean_lunar_node_longitude(date) + 180)
    return ecliptic_longitude(body, date)  # type: ignore[arg-type]


# Centers and the gates each one owns.
CenterName = Literal[
    "Head",
    "Ajna",
    "Throat",
    "G",
    "Heart",
    "Spleen",
    "Sacral",
    "Solar Plexus",
    "Root",
]

GATES_BY_CENTER: dict[CenterName, list[int]] = {
    "Head": [64, 61, 63],
    "Ajna": [47, 24, 4, 17, 43, 11],
    "Throat": [62, 23, 56, 16, 35, 12, 45, 33, 8, 31, 20],
    "G": [7, 1, 13, 25, 46, 2, 15, 10],
    "Heart": [21, 26, 51, 40],
    "Spleen": [48, 57, 44, 50, 32, 28, 18],
    "Sacral": [5, 14, 29, 59, 9, 3, 42, 27, 34],
    "Solar Plexus": [36, 22, 37, 6, 49, 55, 30],
    "Root": [53, 60, 52, 19, 39, 41, 58, 38, 54],
}

GATE_TO_CENTER: dict[int, str] = {}
for _center, _gates in GATES_BY_CENTER.items():
    for _g in _gates:
        GATE_TO_CENTER[_g] = _center


@dataclass
class Channel:
    gates: tuple[int, int]
    name: str


# All 36 channels of the body graph.
CHANNELS: list[Channel] = [
    Channel((1, 8), "Inspiration"),
    Channel((2, 14), "The Beat"),
    Channel((3, 60), "Mutation"),
    Channel((4, 63), "Logic"),
    Channel((5, 15), "Rhythm"),
    Channel((6, 59), "Mating"),
    Channel((7, 31), "The Alpha"),
    Channel((9, 52), "Concentration"),
    Channel((10, 20), "Awakening"),
    Channel((10, 34), "Exploration"),
    Channel((10, 57), "Perfected Form"),
    Channel((11, 56), "Curiosity"),
    Channel((12, 22), "Openness"),
    Channel((13, 33), "The Prodigal"),
    Channel((16, 48), "The Wavelength"),
    Channel((17, 62), "Acceptance"),
    Channel((18, 58), "Judgment"),
    Channel((19, 49), "Synthesis"),
    Channel((20, 34), "Charisma"),
    Channel((20, 57), "The Brain Wave"),
    Channel((21, 45), "Money"),
    Channel((23, 43), "Structuring"),
    Channel((24, 61), "Awareness"),
    Channel((25, 51), "Initiation"),
    Channel((26, 44), "Surrender"),
    Channel((27, 50), "Preservation"),
    Channel((28, 38), "Struggle"),
    Channel((29, 46), "Discovery"),
    Channel((30, 41), "Recognition"),
    Channel((32, 54), "Transformation"),
    Channel((34, 57), "Power"),
    Channel((35, 36), "Transitoriness"),
    Channel((37, 40), "Community"),
    Channel((39, 55), "Emoting"),
    Channel((42, 53), "Maturation"),
    Channel((47, 64), "Abstraction"),
]

# Motor centers (used to determine HD type & manifestor capacity).
MOTORS: list[str] = ["Sacral", "Solar Plexus", "Heart", "Root"]

HdType = Literal[
    "Manifestor",
    "Generator",
    "Manifesting Generator",
    "Projector",
    "Reflector",
]

HdAuthority = Literal[
    "Solar Plexus (Emotional)",
    "Sacral",
    "Splenic",
    "Ego (Manifested)",
    "Ego (Projected)",
    "Self-Projected (G)",
    "Mental (Outer)",
    "Lunar (Reflector)",
]


@dataclass(frozen=True)
class Definition:
    kind: str
    components: int


class OrderedCenterSet:
    """Insertion-ordered set of center names (JS Set semantics).

    Preserves first-insertion order for iteration while supporting O(1)
    membership tests and a `.size` accessor matching the TS code.
    """

    def __init__(self) -> None:
        self._d: dict[str, None] = {}

    def add(self, center: CenterName) -> None:
        self._d.setdefault(center, None)

    def has(self, center: CenterName) -> bool:
        return center in self._d

    def __contains__(self, center: object) -> bool:
        return center in self._d

    def __iter__(self):
        return iter(self._d)

    def __len__(self) -> int:
        return len(self._d)

    @property
    def size(self) -> int:
        return len(self._d)


def center_links(active_channels: list[Channel]) -> dict[str, set[str]]:
    """Build a graph of which centers connect to which via active channels."""
    adj: dict[str, set[str]] = {c: set() for c in GATES_BY_CENTER}
    for ch in active_channels:
        a = GATE_TO_CENTER[ch.gates[0]]
        b = GATE_TO_CENTER[ch.gates[1]]
        adj[a].add(b)
        adj[b].add(a)
    return adj


def path_exists(adj: dict[str, set[str]], frm: str, to: str) -> bool:
    """Is there a path between two centers in the active-channel graph (BFS)?"""
    seen = {frm}
    queue = deque([frm])
    while queue:
        c = queue.popleft()
        if c == to:
            return True
        for n in adj[c]:
            if n not in seen:
                seen.add(n)
                queue.append(n)
    return False


def determine_type(defined: OrderedCenterSet, active_channels: list[Channel]) -> HdType:
    if defined.size == 0:
        return "Reflector"
    adj = center_links(active_channels)
    sacral_defined = defined.has("Sacral")
    throat_defined = defined.has("Throat")
    motor_to_throat = throat_defined and any(
        c in MOTORS and path_exists(adj, c, "Throat") for c in defined
    )
    if sacral_defined and motor_to_throat:
        return "Manifesting Generator"
    if sacral_defined:
        return "Generator"
    if motor_to_throat:
        return "Manifestor"
    return "Projector"


def determine_authority(type_: HdType, defined: OrderedCenterSet) -> HdAuthority:
    if type_ == "Reflector":
        return "Lunar (Reflector)"
    if defined.has("Solar Plexus"):
        return "Solar Plexus (Emotional)"
    if defined.has("Sacral"):
        return "Sacral"
    if defined.has("Spleen"):
        return "Splenic"
    if defined.has("Heart"):
        return "Ego (Manifested)" if type_ == "Manifestor" else "Ego (Projected)"
    if defined.has("G"):
        return "Self-Projected (G)"
    return "Mental (Outer)"


def determine_strategy(type_: HdType) -> str:
    return {
        "Manifestor": "Inform before acting",
        "Generator": "Wait to respond",
        "Manifesting Generator": "Wait to respond, then inform",
        "Projector": "Wait for the invitation",
        "Reflector": "Wait a lunar cycle (28 days) before deciding",
    }[type_]


def determine_signature(type_: HdType) -> str:
    if type_ == "Manifestor":
        return "Peace"
    if type_ in ("Generator", "Manifesting Generator"):
        return "Satisfaction"
    if type_ == "Projector":
        return "Success"
    return "Surprise"  # Reflector


def determine_not_self(type_: HdType) -> str:
    if type_ == "Manifestor":
        return "Anger"
    if type_ in ("Generator", "Manifesting Generator"):
        return "Frustration"
    if type_ == "Projector":
        return "Bitterness"
    return "Disappointment"  # Reflector


def determine_definition(
    defined: OrderedCenterSet, active_channels: list[Channel]
) -> Definition:
    """Count connected components of defined centers reachable via active channels."""
    if defined.size == 0:
        return Definition(kind="None (Reflector)", components=0)
    adj = center_links(active_channels)
    seen: set[str] = set()
    components = 0
    for c in defined:
        if c in seen:
            continue
        components += 1
        stack = [c]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            for n in adj[x]:
                if defined.has(n) and n not in seen:
                    stack.append(n)
    kind_map = {
        1: "Single Definition",
        2: "Split Definition",
        3: "Triple-Split Definition",
        4: "Quadruple-Split Definition",
    }
    return Definition(
        kind=kind_map.get(components, f"{components} components"),
        components=components,
    )


def classify_incarnation_cross(p_sun_line: int, d_sun_line: int) -> str:
    """Name the cross by sun-line pattern (Right Angle / Left Angle / Juxtaposition)."""
    lines = {p_sun_line, d_sun_line}
    if len(lines) == 1 and 4 in lines:
        return "Juxtaposition Cross"
    if p_sun_line >= 4 and d_sun_line >= 4:
        return "Left Angle Cross"
    return "Right Angle Cross"


@dataclass
class HdActivation:
    body: str
    longitude: float
    gate: int
    line: int
    color: int
    tone: int
    base: int


@dataclass
class IncarnationCross:
    name: str
    personality_sun: GateActivation
    personality_earth: GateActivation
    design_sun: GateActivation
    design_earth: GateActivation


@dataclass
class Variables:
    right_left_mind: str
    right_left_body: str


@dataclass
class HumanDesignChart:
    design_ms: int
    personality: list[HdActivation]
    design: list[HdActivation]
    active_gates: set[int]
    defined_centers: OrderedCenterSet
    active_channels: list[Channel]
    type: HdType
    strategy: str
    authority: HdAuthority
    profile: str
    signature: str
    not_self: str
    definition: Definition
    incarnation_cross: IncarnationCross
    variables: Variables


def activations_for(date: datetime) -> list[HdActivation]:
    out: list[HdActivation] = []
    for body in HD_BODIES:
        lon = body_longitude(body, date)
        ga = longitude_to_gate(lon)
        out.append(
            HdActivation(
                body=body,
                longitude=lon,
                gate=ga.gate,
                line=ga.line,
                color=ga.color,
                tone=ga.tone,
                base=ga.base,
            )
        )
    return out


def calculate_human_design(birth: datetime) -> HumanDesignChart:
    birth_ms = _to_ms(birth)
    personality_sun_lon = ecliptic_longitude("Sun", birth)
    design_sun_target = norm360(personality_sun_lon - 88)
    design_ms = find_sun_longitude_time(birth_ms, design_sun_target)

    personality = activations_for(birth)
    design = activations_for(_from_ms(design_ms))

    active_gates: set[int] = set()
    for a in personality:
        active_gates.add(a.gate)
    for a in design:
        active_gates.add(a.gate)

    # Active channels: where BOTH gate ends are active.
    active_channels = [
        ch
        for ch in CHANNELS
        if ch.gates[0] in active_gates and ch.gates[1] in active_gates
    ]

    # A center is "defined" iff at least one of its gates participates in an
    # active channel. Insertion-ordered (JS Set semantics).
    defined_centers = OrderedCenterSet()
    for ch in active_channels:
        defined_centers.add(GATE_TO_CENTER[ch.gates[0]])
        defined_centers.add(GATE_TO_CENTER[ch.gates[1]])

    type_ = determine_type(defined_centers, active_channels)
    authority = determine_authority(type_, defined_centers)
    definition = determine_definition(defined_centers, active_channels)
    strategy = determine_strategy(type_)
    signature = determine_signature(type_)
    not_self = determine_not_self(type_)

    personality_sun = personality[0]
    design_sun = design[0]
    personality_earth = personality[1]
    design_earth = design[1]

    profile = f"{personality_sun.line}/{design_sun.line}"
    cross_class = classify_incarnation_cross(personality_sun.line, design_sun.line)
    cross_name = (
        f"{cross_class} of ({personality_sun.gate}/{personality_earth.gate} "
        f"| {design_sun.gate}/{design_earth.gate})"
    )

    # Variables — color of Personality & Design Sun give Mind & Body arrows.
    # Convention: colors 1-3 = Right, 4-6 = Left.
    variables = Variables(
        right_left_mind="Right" if design_sun.color <= 3 else "Left",
        right_left_body="Right" if personality_sun.color <= 3 else "Left",
    )

    def _ga(a: HdActivation) -> GateActivation:
        return GateActivation(
            gate=a.gate,
            line=a.line,
            color=a.color,
            tone=a.tone,
            base=a.base,
            longitude=a.longitude,
        )

    return HumanDesignChart(
        design_ms=design_ms,
        personality=personality,
        design=design,
        active_gates=active_gates,
        defined_centers=defined_centers,
        active_channels=active_channels,
        type=type_,
        strategy=strategy,
        authority=authority,
        profile=profile,
        signature=signature,
        not_self=not_self,
        definition=definition,
        incarnation_cross=IncarnationCross(
            name=cross_name,
            personality_sun=_ga(personality_sun),
            personality_earth=_ga(personality_earth),
            design_sun=_ga(design_sun),
            design_earth=_ga(design_earth),
        ),
        variables=variables,
    )
