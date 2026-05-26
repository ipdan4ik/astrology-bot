"""Per-system blueprint section builders.

Each builder is pure: given a BlueprintInput and a precomputed BlueprintContext,
it returns the Markdown chunk for one astrology system (BaZi, Numerology, …).
build_blueprint() in blueprint.py orchestrates them; build_reading_calc_md()
wraps a single section with a minimal birth-data header and a footer so it
can be consumed standalone by polish_reading().

The exact bytes produced by each builder must, when concatenated in the order
declared in BLUEPRINT_SECTION_ORDER, reproduce the historic build_blueprint()
output byte-for-byte. See tests/test_astrology_blueprint_golden.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from quantuum.astrology.blueprint import BlueprintInput

from quantuum.astrology.astro import (
    ascendant_longitude,
    find_aspect,
    house_of,
    lunar_nodes,
    midheaven_longitude,
    nakshatra,
    placidus_cusps,
    planet_position,
    sidereal_longitude,
    whole_sign_houses,
)
from quantuum.astrology.chinese import chinese_pillars_from_local, pillar_summary
from quantuum.astrology.gene_keys import calculate_gene_keys
from quantuum.astrology.human_design import calculate_human_design
from quantuum.astrology.mayan import tzolkin
from quantuum.astrology.numerology import calculate_numerology
from quantuum.astrology.util import (
    ELEMENTS,
    MODALITIES,
    fmt_deg,
    to_fixed,
    to_sign_degree,
)


ALL_PLANETS: list[str] = [
    "Sun", "Moon", "Mercury", "Venus", "Mars",
    "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
]

PLANET_GLYPH: dict[str, str] = {
    "Sun": "☉", "Moon": "☽", "Mercury": "☿", "Venus": "♀", "Mars": "♂",
    "Jupiter": "♃", "Saturn": "♄", "Uranus": "♅", "Neptune": "♆", "Pluto": "♇",
}

PERSONAL_YEAR_THEMES: dict[int, dict[str, str]] = {
    1: {"theme": "Initiation", "focus": "New cycle, identity, direction"},
    2: {"theme": "Partnership", "focus": "Sensitivity, patience, relational attunement"},
    3: {"theme": "Expression", "focus": "Creativity, visibility, voice"},
    4: {"theme": "Foundation", "focus": "Structure, discipline, embodied systems"},
    5: {"theme": "Change", "focus": "Freedom, movement, adaptation"},
    6: {"theme": "Responsibility", "focus": "Home, service, care, repair"},
    7: {"theme": "Inner Inquiry", "focus": "Study, solitude, spiritual refinement"},
    8: {"theme": "Power", "focus": "Leadership, resources, material mastery"},
    9: {"theme": "Completion", "focus": "Release, compassion, harvest"},
    11: {"theme": "Illumination", "focus": "Intuition, vision, inspired service"},
    22: {"theme": "Master Builder", "focus": "Large-scale structure, service in form"},
    33: {"theme": "Master Teacher", "focus": "Compassionate guidance, healing service"},
}

MATRIX_MAPPING: list[dict[str, str]] = [
    {"matrix_center": "ROOT", "hd_center": "Root", "theme": "Foundation"},
    {"matrix_center": "SACRAL", "hd_center": "Sacral", "theme": "Creativity"},
    {"matrix_center": "SOLAR PLEXUS", "hd_center": "Solar Plexus", "theme": "Power"},
    {"matrix_center": "HEART", "hd_center": "Heart", "theme": "Service"},
    {"matrix_center": "THROAT", "hd_center": "Throat", "theme": "Expression"},
    {"matrix_center": "THIRD EYE", "hd_center": "Ajna", "theme": "Vision"},
    {"matrix_center": "CROWN", "hd_center": "Head", "theme": "Spirit"},
]

_UNDEFINED_CENTER_ORDER = [
    "Head", "Ajna", "Throat", "G", "Heart",
    "Spleen", "Sacral", "Solar Plexus", "Root",
]


def _bump(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _personal_year_theme(personal_year: int) -> dict[str, str]:
    return PERSONAL_YEAR_THEMES.get(
        personal_year,
        {
            "theme": f"Personal Year {personal_year}",
            "focus": "Use the calculated personal-year number as the timing anchor",
        },
    )


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(str(v) for v in r) + " |" for r in rows)
    return "\n".join([head, sep, body])


def _fmt_pos(p) -> str:
    return f"{fmt_deg(p)}{' ℞' if p.retrograde else ''}"


@dataclass
class BlueprintContext:
    birth: datetime
    birth_ms: int
    yyyy: int
    mm: int
    dd: int
    birth_hour: int
    birth_minute: int
    planets: dict[str, Any]
    asc_lon: float
    mc_lon: float
    asc_sd: Any
    mc_sd: Any
    ws_cusps_raw: list[float]
    porphyry_cusps_raw: list[float]
    ws_houses: list[Any]
    porphyry_houses: list[Any]
    nodes: dict[str, Any]
    house_assignments: list[dict[str, Any]]
    aspect_rows: list[dict[str, str]]
    for_year: int


def build_blueprint_context(inp: "BlueprintInput") -> BlueprintContext:
    from quantuum.astrology.blueprint import EPOCH, parse_birth_instant

    birth = parse_birth_instant(inp)
    for_year = inp.for_year if inp.for_year is not None else datetime.now(timezone.utc).year
    yyyy, mm, dd = (int(x) for x in inp.birth_date.split("-"))
    birth_hour, birth_minute = (int(x) for x in inp.birth_time.split(":"))
    birth_ms = round((birth.astimezone(timezone.utc) - EPOCH).total_seconds() * 1000)

    planets = {p: planet_position(p, birth) for p in ALL_PLANETS}
    asc_lon = ascendant_longitude(birth, inp.latitude, inp.longitude)
    mc_lon = midheaven_longitude(birth, inp.longitude)
    asc_sd = to_sign_degree(asc_lon)
    mc_sd = to_sign_degree(mc_lon)
    ws_cusps_raw = whole_sign_houses(asc_lon)
    porphyry_cusps_raw = placidus_cusps(birth, inp.latitude, inp.longitude)
    ws_houses = [to_sign_degree(x) for x in ws_cusps_raw]
    porphyry_houses = [to_sign_degree(x) for x in porphyry_cusps_raw]
    nodes = lunar_nodes(birth)
    house_assignments = [
        {
            "planet": p,
            "pos": planets[p],
            "whole_sign": house_of(planets[p].longitude, ws_cusps_raw),
            "porphyry": house_of(planets[p].longitude, porphyry_cusps_raw),
        }
        for p in ALL_PLANETS
    ]

    aspect_rows: list[dict[str, str]] = []
    aspect_targets: list[tuple[str, float]] = [
        *[(p, planets[p].longitude) for p in ALL_PLANETS],
        ("Asc", asc_lon),
        ("MC", mc_lon),
        ("NN", nodes["north"].longitude),
    ]
    for i in range(len(aspect_targets)):
        for j in range(i + 1, len(aspect_targets)):
            a_name, a_lon = aspect_targets[i]
            b_name, b_lon = aspect_targets[j]
            r = find_aspect(a_lon, b_lon)
            if r:
                aspect_rows.append(
                    {
                        "a": a_name,
                        "b": b_name,
                        "aspect": r["name"],
                        "orb": f"{to_fixed(r['orb'], 2)}°",
                    }
                )

    return BlueprintContext(
        birth=birth,
        birth_ms=birth_ms,
        yyyy=yyyy,
        mm=mm,
        dd=dd,
        birth_hour=birth_hour,
        birth_minute=birth_minute,
        planets=planets,
        asc_lon=asc_lon,
        mc_lon=mc_lon,
        asc_sd=asc_sd,
        mc_sd=mc_sd,
        ws_cusps_raw=ws_cusps_raw,
        porphyry_cusps_raw=porphyry_cusps_raw,
        ws_houses=ws_houses,
        porphyry_houses=porphyry_houses,
        nodes=nodes,
        house_assignments=house_assignments,
        aspect_rows=aspect_rows,
        for_year=for_year,
    )


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def build_identity_section(inp: "BlueprintInput", ctx: BlueprintContext) -> str:
    lines: list[str] = []

    def push(s: str) -> None:
        lines.append(s)

    push("## 1. Identity Layer")
    push("")
    push("### Core Astrology (Tropical / Western)")
    push("")
    push(
        _table(
            ["Body", "Position", "House (Whole Sign)", "House (Porphyry)"],
            [
                *[
                    [
                        f"{PLANET_GLYPH[h['planet']]} {h['planet']}",
                        _fmt_pos(h["pos"]),
                        h["whole_sign"],
                        h["porphyry"],
                    ]
                    for h in ctx.house_assignments
                ],
                ["↑ Western/Tropical Ascendant", fmt_deg(ctx.asc_sd), 1, 1],
                ["↟ MC (Midheaven)", fmt_deg(ctx.mc_sd), 10, 10],
                [
                    "☊ North Node (Mean)",
                    fmt_deg(ctx.nodes["north"]),
                    house_of(ctx.nodes["north"].longitude, ctx.ws_cusps_raw),
                    house_of(ctx.nodes["north"].longitude, ctx.porphyry_cusps_raw),
                ],
                [
                    "☋ South Node",
                    fmt_deg(ctx.nodes["south"]),
                    house_of(ctx.nodes["south"].longitude, ctx.ws_cusps_raw),
                    house_of(ctx.nodes["south"].longitude, ctx.porphyry_cusps_raw),
                ],
            ],
        )
    )
    push("")

    # Element / modality tally
    element_tally: dict[str, int] = {"Fire": 0, "Earth": 0, "Air": 0, "Water": 0}
    modality_tally: dict[str, int] = {"Cardinal": 0, "Fixed": 0, "Mutable": 0}

    for p in ALL_PLANETS:
        _bump(element_tally, ELEMENTS[ctx.planets[p].sign])
        _bump(modality_tally, MODALITIES[ctx.planets[p].sign])
    _bump(element_tally, ELEMENTS[ctx.asc_sd.sign])
    _bump(modality_tally, MODALITIES[ctx.asc_sd.sign])
    _bump(element_tally, ELEMENTS[ctx.mc_sd.sign])
    _bump(modality_tally, MODALITIES[ctx.mc_sd.sign])

    push("### Elemental & Modality Balance")
    push("")
    push(
        _table(
            [
                "Element",
                "Planets only",
                "Including Asc + MC",
                "Modality",
                "Planets only",
                "Including Asc + MC",
            ],
            [
                [
                    "🔥 Fire",
                    len([p for p in ALL_PLANETS if ELEMENTS[ctx.planets[p].sign] == "Fire"]),
                    element_tally.get("Fire", 0),
                    "Cardinal",
                    len(
                        [
                            p
                            for p in ALL_PLANETS
                            if MODALITIES[ctx.planets[p].sign] == "Cardinal"
                        ]
                    ),
                    modality_tally.get("Cardinal", 0),
                ],
                [
                    "🌱 Earth",
                    len([p for p in ALL_PLANETS if ELEMENTS[ctx.planets[p].sign] == "Earth"]),
                    element_tally.get("Earth", 0),
                    "Fixed",
                    len(
                        [p for p in ALL_PLANETS if MODALITIES[ctx.planets[p].sign] == "Fixed"]
                    ),
                    modality_tally.get("Fixed", 0),
                ],
                [
                    "🌬 Air",
                    len([p for p in ALL_PLANETS if ELEMENTS[ctx.planets[p].sign] == "Air"]),
                    element_tally.get("Air", 0),
                    "Mutable",
                    len(
                        [
                            p
                            for p in ALL_PLANETS
                            if MODALITIES[ctx.planets[p].sign] == "Mutable"
                        ]
                    ),
                    modality_tally.get("Mutable", 0),
                ],
                [
                    "💧 Water",
                    len([p for p in ALL_PLANETS if ELEMENTS[ctx.planets[p].sign] == "Water"]),
                    element_tally.get("Water", 0),
                    "",
                    "",
                    "",
                ],
            ],
        )
    )
    push("")

    push("### House-System Clarifications")
    push("")
    push(
        _table(
            ["Body", "Whole Sign House", "Porphyry House", "Note"],
            [
                [
                    "☽ Moon",
                    house_of(ctx.planets["Moon"].longitude, ctx.ws_cusps_raw),
                    house_of(ctx.planets["Moon"].longitude, ctx.porphyry_cusps_raw),
                    "Mention the house system whenever interpreting the Moon.",
                ],
            ],
        )
    )
    push("")

    push("### House Cusps")
    push("")
    push(
        _table(
            ["House", "Whole Sign", "Porphyry"],
            [
                [i + 1, fmt_deg(ctx.ws_houses[i]), fmt_deg(ctx.porphyry_houses[i])]
                for i in range(12)
            ],
        )
    )
    push("")

    return "\n".join(lines)


def build_aspects_section(inp: "BlueprintInput", ctx: BlueprintContext) -> str:
    lines: list[str] = []

    def push(s: str) -> None:
        lines.append(s)

    push("## 2. Major Aspects")
    push("")
    push(
        _table(
            ["Body A", "Body B", "Aspect", "Orb"],
            [[r["a"], r["b"], r["aspect"], r["orb"]] for r in ctx.aspect_rows],
        )
    )
    push("")
    key_conjunction_rows = [r for r in ctx.aspect_rows if r["aspect"] == "Conjunction"]
    push("### Key Natal Conjunctions")
    push("")
    push(
        _table(
            ["Bodies", "Orb", "Usage Note"],
            [
                [
                    f"{r['a']} conjunct {r['b']}",
                    r["orb"],
                    "If interpreted in the final report, include this aspect explicitly in the overview.",
                ]
                for r in key_conjunction_rows
            ],
        )
        if len(key_conjunction_rows) > 0
        else "_No major conjunctions within the configured orb set._"
    )
    push("")

    return "\n".join(lines)


def build_vedic_section(inp: "BlueprintInput", ctx: BlueprintContext) -> str:
    lines: list[str] = []

    def push(s: str) -> None:
        lines.append(s)

    vedic_sun = to_sign_degree(sidereal_longitude(ctx.planets["Sun"].longitude, ctx.birth))
    vedic_moon = to_sign_degree(sidereal_longitude(ctx.planets["Moon"].longitude, ctx.birth))
    vedic_asc = to_sign_degree(sidereal_longitude(ctx.asc_lon, ctx.birth))
    moon_nakshatra = nakshatra(sidereal_longitude(ctx.planets["Moon"].longitude, ctx.birth))

    push("## 3. Vedic (Sidereal, Lahiri Ayanamsha)")
    push("")
    push(
        _table(
            ["Body", "Sidereal Position"],
            [
                ["☉ Sun", fmt_deg(vedic_sun)],
                ["☽ Moon", fmt_deg(vedic_moon)],
                ["↑ Vedic/Sidereal Ascendant", fmt_deg(vedic_asc)],
            ],
        )
    )
    push("")
    push(
        f"**Moon Nakshatra:** {moon_nakshatra['name']} (#{moon_nakshatra['index']}), "
        f"pada {moon_nakshatra['pada']}"
    )
    push("")

    return "\n".join(lines)


def build_numerology_section(inp: "BlueprintInput", ctx: BlueprintContext) -> str:
    lines: list[str] = []

    def push(s: str) -> None:
        lines.append(s)

    num = calculate_numerology(inp.full_name, ctx.yyyy, ctx.mm, ctx.dd, ctx.for_year)
    timing_rows = []
    for i in range(5):
        year = ctx.for_year - 1 + i
        n = calculate_numerology(inp.full_name, ctx.yyyy, ctx.mm, ctx.dd, year)
        theme = _personal_year_theme(n.personal_year)
        timing_rows.append(
            {
                "year": year,
                "age_turning": year - ctx.yyyy,
                "personal_year": n.personal_year,
                "theme": theme["theme"],
                "focus": theme["focus"],
            }
        )

    push("## 4. Numerology (Pythagorean)")
    push("")
    push(
        _table(
            ["Number", "Value", "Source"],
            [
                ["Life Path", num.life_path, "Birth date reduced"],
                ["Birth Day", num.birth_day, "Day of month reduced"],
                ["Destiny / Expression", num.destiny, "All letters of full name"],
                ["Soul Urge / Heart's Desire", num.soul_urge, "Vowels of full name"],
                ["Personality", num.personality, "Consonants of full name"],
                ["Maturity", num.maturity, "Life Path + Destiny"],
                ["Attitude", num.attitude, "Birth Month + Birth Day"],
                [
                    f"Personal Year ({num.personal_year_target})",
                    num.personal_year,
                    "Month+Day+Year",
                ],
            ],
        )
    )
    push("")
    push("### Pinnacles (life-stage themes)")
    push("")
    push(
        _table(
            ["Pinnacle", "Number"],
            [
                ["P1 (birth–~36 yr)", num.pinnacles.p1],
                ["P2 (next ~9 yr)", num.pinnacles.p2],
                ["P3 (next ~9 yr)", num.pinnacles.p3],
                ["P4 (rest of life)", num.pinnacles.p4],
            ],
        )
    )
    push("")
    push("### Challenges (life-lesson tensions)")
    push("")
    push(
        _table(
            ["Challenge", "Number"],
            [
                ["C1", num.challenges.c1],
                ["C2", num.challenges.c2],
                ["C3 (main life challenge)", num.challenges.c3],
                ["C4", num.challenges.c4],
            ],
        )
    )
    push("")

    push("### Timing Cycles")
    push("")
    push(
        _table(
            [
                "Year",
                "Age turning that birthday",
                "Personal Year",
                "Timeline Theme",
                "Timeline Focus",
            ],
            [
                [
                    r["year"],
                    r["age_turning"],
                    r["personal_year"],
                    r["theme"],
                    r["focus"],
                ]
                for r in timing_rows
            ],
        )
    )
    push("")

    return "\n".join(lines)


def build_bazi_section(inp: "BlueprintInput", ctx: BlueprintContext) -> str:
    lines: list[str] = []

    def push(s: str) -> None:
        lines.append(s)

    bazi = chinese_pillars_from_local(ctx.yyyy, ctx.mm, ctx.dd, ctx.birth_hour, ctx.birth_minute)

    push("## 5. Chinese Zodiac — Four Pillars (BaZi)")
    push("")
    push(
        f"_Calculated from local civil birth time: {inp.birth_date} "
        f"{inp.birth_time} ({inp.timezone})._"
    )
    push("")
    push(
        _table(
            ["Pillar", "Stem-Branch", "Element", "Animal", "Polarity"],
            [
                [
                    "Year",
                    f"{bazi.year.full} / {bazi.year.chinese}",
                    bazi.year.element,
                    bazi.year.animal,
                    bazi.year.polarity,
                ],
                [
                    "Month",
                    f"{bazi.month.full} / {bazi.month.chinese}",
                    bazi.month.element,
                    bazi.month.animal,
                    bazi.month.polarity,
                ],
                [
                    "Day (Self)",
                    f"{bazi.day.full} / {bazi.day.chinese}",
                    bazi.day.element,
                    bazi.day.animal,
                    bazi.day.polarity,
                ],
                [
                    "Hour",
                    f"{bazi.hour.full} / {bazi.hour.chinese}",
                    bazi.hour.element,
                    bazi.hour.animal,
                    bazi.hour.polarity,
                ],
            ],
        )
    )
    push("")
    push(f"**Year totem:** {pillar_summary(bazi.year)}")
    push(f"**Day Master (true self):** {pillar_summary(bazi.day)}")
    push("")

    return "\n".join(lines)


def build_human_design_section(inp: "BlueprintInput", ctx: BlueprintContext) -> str:
    lines: list[str] = []

    def push(s: str) -> None:
        lines.append(s)

    from quantuum.astrology.blueprint import to_iso_z

    hd = calculate_human_design(ctx.birth)

    push("## 6. Human Design")
    push("")
    push(
        "_Calculation note: Human Design gates/lines are computed with an open Rave "
        "Mandala approximation from astronomical longitudes. For professional HD use, "
        "verify Type/Profile/Authority against a dedicated Human Design source._"
    )
    push("")
    undefined_centers = (
        ", ".join(c for c in _UNDEFINED_CENTER_ORDER if c not in hd.defined_centers)
        or "(all defined)"
    )
    push(
        _table(
            ["Field", "Value"],
            [
                ["Type", hd.type],
                ["Strategy", hd.strategy],
                ["Authority", hd.authority],
                ["Profile", hd.profile],
                ["Definition", hd.definition.kind],
                ["Signature", hd.signature],
                ["Not-Self", hd.not_self],
                [
                    "Defined Centers",
                    ", ".join(hd.defined_centers) or "(none — Reflector)",
                ],
                ["Undefined Centers", undefined_centers],
                ["Active Channels", len(hd.active_channels)],
                [
                    "Active Gates",
                    ", ".join(str(g) for g in sorted(hd.active_gates)),
                ],
                ["Mind arrow (Design Sun)", f"{hd.variables.right_left_mind}-oriented"],
                [
                    "Body arrow (Personality Sun)",
                    f"{hd.variables.right_left_body}-oriented",
                ],
                ["Design moment (88° solar arc back)", to_iso_z(hd.design_ms)],
                ["Incarnation Cross", hd.incarnation_cross.name],
            ],
        )
    )
    push("")
    push("### Quantuum 35-Dimensional Matrix Mapping")
    push("")
    push(
        _table(
            ["Matrix Center", "Theme", "Human Design Center", "Status"],
            [
                [
                    m["matrix_center"],
                    m["theme"],
                    m["hd_center"],
                    "Defined" if m["hd_center"] in hd.defined_centers else "Undefined",
                ]
                for m in MATRIX_MAPPING
            ],
        )
    )
    push("")
    push("### Personality Activations (consciously held — at birth)")
    push("")
    push(
        _table(
            ["Body", "Longitude", "Gate.Line", "Color", "Tone", "Base"],
            [
                [
                    a.body,
                    to_sign_degree(a.longitude).sign
                    + " "
                    + to_fixed(a.longitude % 30, 2)
                    + "°",
                    f"{a.gate}.{a.line}",
                    a.color,
                    a.tone,
                    a.base,
                ]
                for a in hd.personality
            ],
        )
    )
    push("")
    push("### Design Activations (unconsciously held — 88° earlier)")
    push("")
    push(
        _table(
            ["Body", "Longitude", "Gate.Line", "Color", "Tone", "Base"],
            [
                [
                    a.body,
                    to_sign_degree(a.longitude).sign
                    + " "
                    + to_fixed(a.longitude % 30, 2)
                    + "°",
                    f"{a.gate}.{a.line}",
                    a.color,
                    a.tone,
                    a.base,
                ]
                for a in hd.design
            ],
        )
    )
    push("")
    push("### Active Channels")
    push("")
    if len(hd.active_channels) == 0:
        push("_(no active channels — Reflector design)_")
    else:
        push(
            _table(
                ["Channel", "Name"],
                [
                    [f"{ch.gates[0]}–{ch.gates[1]}", ch.name]
                    for ch in hd.active_channels
                ],
            )
        )
    push("")

    return "\n".join(lines)


def build_gene_keys_section(inp: "BlueprintInput", ctx: BlueprintContext) -> str:
    lines: list[str] = []

    def push(s: str) -> None:
        lines.append(s)

    hd = calculate_human_design(ctx.birth)
    gk = calculate_gene_keys(hd)

    push("## 7. Gene Keys — The Activation Sequence")
    push("")
    push(
        "_Calculation note: Gene Keys gates/lines are computed directly from the same "
        "Sun/Earth gate-line longitudes used above; verify if the Human Design "
        "gate-line source is overridden externally._"
    )
    push("")
    push(
        _table(
            ["Sphere", "Gate.Line", "Hexagram", "Shadow", "Gift", "Siddhi"],
            [
                [
                    "Life's Work",
                    f"{gk.lifes_work.gate}.{gk.lifes_work.line}",
                    gk.lifes_work.name,
                    gk.lifes_work.shadow,
                    gk.lifes_work.gift,
                    gk.lifes_work.siddhi,
                ],
                [
                    "Evolution",
                    f"{gk.evolution.gate}.{gk.evolution.line}",
                    gk.evolution.name,
                    gk.evolution.shadow,
                    gk.evolution.gift,
                    gk.evolution.siddhi,
                ],
                [
                    "Radiance",
                    f"{gk.radiance.gate}.{gk.radiance.line}",
                    gk.radiance.name,
                    gk.radiance.shadow,
                    gk.radiance.gift,
                    gk.radiance.siddhi,
                ],
                [
                    "Purpose",
                    f"{gk.purpose.gate}.{gk.purpose.line}",
                    gk.purpose.name,
                    gk.purpose.shadow,
                    gk.purpose.gift,
                    gk.purpose.siddhi,
                ],
            ],
        )
    )
    push("")

    return "\n".join(lines)


def build_mayan_section(inp: "BlueprintInput", ctx: BlueprintContext) -> str:
    lines: list[str] = []

    def push(s: str) -> None:
        lines.append(s)

    tz = tzolkin(ctx.birth)

    push("## 8. Mayan Tzolkin (Traditional GMT correlation + Dreamspell label)")
    push("")
    push(
        _table(
            ["Field", "Value"],
            [
                ["Tone (Trecena)", tz.trecena],
                ["Day Sign (Maya)", tz.sign_name],
                ["Day Sign (Dreamspell)", tz.dreamspell_name],
                ["Full Name", tz.full],
                ["Kin (1–260)", tz.kin],
            ],
        )
    )
    push("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry + standalone builder
# ---------------------------------------------------------------------------

BLUEPRINT_SECTION_ORDER: tuple[str, ...] = (
    "astrology", "aspects", "vedic", "numerology",
    "bazi", "human_design", "gene_keys", "mayan",
)

SECTION_BUILDERS: dict[str, Callable[["BlueprintInput", BlueprintContext], str]] = {
    "astrology":    build_identity_section,
    "aspects":      build_aspects_section,
    "vedic":        build_vedic_section,
    "numerology":   build_numerology_section,
    "bazi":         build_bazi_section,
    "human_design": build_human_design_section,
    "gene_keys":    build_gene_keys_section,
    "mayan":        build_mayan_section,
}


def build_reading_calc_md(kind: str, inp: "BlueprintInput") -> str:
    """Self-contained mini-doc: birth header + one section + footer."""
    from quantuum.astrology.blueprint import _render_header, _render_footer
    ctx = build_blueprint_context(inp)
    return "\n".join([
        _render_header(inp, ctx),
        SECTION_BUILDERS[kind](inp, ctx),
        _render_footer(),
    ])
