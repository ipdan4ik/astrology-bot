"""Quantuum Blueprint generator.

Ported from blueprint.ts — buildBlueprint must produce CHARACTER-EXACT output
matching the TypeScript implementation. Consumes the already-ported astrology
modules; reproduces the exact markdown line sequence, literals, emoji, tables,
and number formatting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

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

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


@dataclass
class BlueprintInput:
    full_name: str
    birth_date: str  # YYYY-MM-DD
    birth_time: str  # HH:MM (24h, local time)
    birth_place: str | None
    latitude: float
    longitude: float
    timezone: str  # IANA name e.g. "Europe/Moscow", or "+03:00" offset
    for_year: int | None = None


# ---------------------------------------------------------------------------
# Timezone / instant handling
# ---------------------------------------------------------------------------

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def parse_birth_instant(inp: BlueprintInput) -> datetime:
    """Mirror blueprint.ts parseBirthInstant — returns a tz-aware UTC datetime."""
    stamp = f"{inp.birth_date}T{inp.birth_time}:00"
    if re.fullmatch(r"[+-]\d{2}:\d{2}", inp.timezone):
        return datetime.fromisoformat(f"{stamp}{inp.timezone}").astimezone(timezone.utc)
    naive = datetime.fromisoformat(stamp)
    return naive.replace(tzinfo=ZoneInfo(inp.timezone)).astimezone(timezone.utc)


def to_iso_z(ms: int) -> str:
    """JS Date.toISOString() from an integer epoch-ms value."""
    dt = EPOCH + timedelta(milliseconds=ms)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------


def table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(str(v) for v in r) + " |" for r in rows)
    return "\n".join([head, sep, body])


def _fmt_pos(p) -> str:
    return f"{fmt_deg(p)}{' ℞' if p.retrograde else ''}"


# ---------------------------------------------------------------------------
# Module-level tables
# ---------------------------------------------------------------------------

PLANET_GLYPH: dict[str, str] = {
    "Sun": "☉",
    "Moon": "☽",
    "Mercury": "☿",
    "Venus": "♀",
    "Mars": "♂",
    "Jupiter": "♃",
    "Saturn": "♄",
    "Uranus": "♅",
    "Neptune": "♆",
    "Pluto": "♇",
}

ALL_PLANETS: list[str] = [
    "Sun",
    "Moon",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
]

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


def personal_year_theme(personal_year: int) -> dict[str, str]:
    return PERSONAL_YEAR_THEMES.get(
        personal_year,
        {
            "theme": f"Personal Year {personal_year}",
            "focus": "Use the calculated personal-year number as the timing anchor",
        },
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_blueprint(inp: BlueprintInput) -> str:
    birth = parse_birth_instant(inp)
    for_year = inp.for_year if inp.for_year is not None else datetime.now(timezone.utc).year
    yyyy, mm, dd = (int(x) for x in inp.birth_date.split("-"))
    birth_hour, birth_minute = (int(x) for x in inp.birth_time.split(":"))

    birth_ms = round((birth.astimezone(timezone.utc) - EPOCH).total_seconds() * 1000)

    # 1. Tropical western chart ---------------------------------------------
    planets: dict[str, Any] = {}
    for p in ALL_PLANETS:
        planets[p] = planet_position(p, birth)
    asc_lon = ascendant_longitude(birth, inp.latitude, inp.longitude)
    mc_lon = midheaven_longitude(birth, inp.longitude)
    asc_sd = to_sign_degree(asc_lon)
    mc_sd = to_sign_degree(mc_lon)
    ws_houses = [to_sign_degree(x) for x in whole_sign_houses(asc_lon)]
    porphyry_houses = [
        to_sign_degree(x) for x in placidus_cusps(birth, inp.latitude, inp.longitude)
    ]
    nodes = lunar_nodes(birth)

    ws_cusps_raw = whole_sign_houses(asc_lon)
    porphyry_cusps_raw = placidus_cusps(birth, inp.latitude, inp.longitude)
    house_assignments = [
        {
            "planet": p,
            "pos": planets[p],
            "whole_sign": house_of(planets[p].longitude, ws_cusps_raw),
            "porphyry": house_of(planets[p].longitude, porphyry_cusps_raw),
        }
        for p in ALL_PLANETS
    ]

    # 2. Aspect grid --------------------------------------------------------
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

    # 3. Vedic chart --------------------------------------------------------
    vedic_sun = to_sign_degree(sidereal_longitude(planets["Sun"].longitude, birth))
    vedic_moon = to_sign_degree(sidereal_longitude(planets["Moon"].longitude, birth))
    vedic_asc = to_sign_degree(sidereal_longitude(asc_lon, birth))
    moon_nakshatra = nakshatra(sidereal_longitude(planets["Moon"].longitude, birth))

    # 4. Numerology ---------------------------------------------------------
    num = calculate_numerology(inp.full_name, yyyy, mm, dd, for_year)
    timing_rows = []
    for i in range(5):
        year = for_year - 1 + i
        n = calculate_numerology(inp.full_name, yyyy, mm, dd, year)
        theme = personal_year_theme(n.personal_year)
        timing_rows.append(
            {
                "year": year,
                "age_turning": year - yyyy,
                "personal_year": n.personal_year,
                "theme": theme["theme"],
                "focus": theme["focus"],
            }
        )

    # 5. Chinese / BaZi -----------------------------------------------------
    bazi = chinese_pillars_from_local(yyyy, mm, dd, birth_hour, birth_minute)

    # 6. Human Design + Gene Keys ------------------------------------------
    hd = calculate_human_design(birth)
    gk = calculate_gene_keys(hd)

    # 7. Mayan Tzolkin ------------------------------------------------------
    tz = tzolkin(birth)

    # ---- Render -----------------------------------------------------------
    lines: list[str] = []

    def push(s: str) -> None:
        lines.append(s)

    push(f"# Quantuum Blueprint — {inp.full_name}")
    push("")
    push(f"**Birth date:** {inp.birth_date}  ")
    push(f"**Birth time:** {inp.birth_time} ({inp.timezone})  ")
    push(
        f"**Birth place:** {inp.birth_place if inp.birth_place is not None else '—'} "
        f"({to_fixed(inp.latitude, 4)}°, {to_fixed(inp.longitude, 4)}°)  "
    )
    push(f"**UTC instant:** {to_iso_z(birth_ms)}  ")
    push(f"**Personal-year target:** {for_year}  ")
    push("**Quantuum Matrix framework:** 35-dimensional  ")
    push("")
    push("---")
    push("")

    # ---------- 1. Identity Layer ----------
    push("## 1. Identity Layer")
    push("")
    push("### Core Astrology (Tropical / Western)")
    push("")
    push(
        table(
            ["Body", "Position", "House (Whole Sign)", "House (Porphyry)"],
            [
                *[
                    [
                        f"{PLANET_GLYPH[h['planet']]} {h['planet']}",
                        _fmt_pos(h["pos"]),
                        h["whole_sign"],
                        h["porphyry"],
                    ]
                    for h in house_assignments
                ],
                ["↑ Western/Tropical Ascendant", fmt_deg(asc_sd), 1, 1],
                ["↟ MC (Midheaven)", fmt_deg(mc_sd), 10, 10],
                [
                    "☊ North Node (Mean)",
                    fmt_deg(nodes["north"]),
                    house_of(nodes["north"].longitude, ws_cusps_raw),
                    house_of(nodes["north"].longitude, porphyry_cusps_raw),
                ],
                [
                    "☋ South Node",
                    fmt_deg(nodes["south"]),
                    house_of(nodes["south"].longitude, ws_cusps_raw),
                    house_of(nodes["south"].longitude, porphyry_cusps_raw),
                ],
            ],
        )
    )
    push("")

    # Element / modality tally
    element_tally: dict[str, int] = {"Fire": 0, "Earth": 0, "Air": 0, "Water": 0}
    modality_tally: dict[str, int] = {"Cardinal": 0, "Fixed": 0, "Mutable": 0}

    def bump(counts: dict[str, int], key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    for p in ALL_PLANETS:
        bump(element_tally, ELEMENTS[planets[p].sign])
        bump(modality_tally, MODALITIES[planets[p].sign])
    bump(element_tally, ELEMENTS[asc_sd.sign])
    bump(modality_tally, MODALITIES[asc_sd.sign])
    bump(element_tally, ELEMENTS[mc_sd.sign])
    bump(modality_tally, MODALITIES[mc_sd.sign])

    push("### Elemental & Modality Balance")
    push("")
    push(
        table(
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
                    len([p for p in ALL_PLANETS if ELEMENTS[planets[p].sign] == "Fire"]),
                    element_tally.get("Fire", 0),
                    "Cardinal",
                    len(
                        [
                            p
                            for p in ALL_PLANETS
                            if MODALITIES[planets[p].sign] == "Cardinal"
                        ]
                    ),
                    modality_tally.get("Cardinal", 0),
                ],
                [
                    "🌱 Earth",
                    len([p for p in ALL_PLANETS if ELEMENTS[planets[p].sign] == "Earth"]),
                    element_tally.get("Earth", 0),
                    "Fixed",
                    len(
                        [p for p in ALL_PLANETS if MODALITIES[planets[p].sign] == "Fixed"]
                    ),
                    modality_tally.get("Fixed", 0),
                ],
                [
                    "🌬 Air",
                    len([p for p in ALL_PLANETS if ELEMENTS[planets[p].sign] == "Air"]),
                    element_tally.get("Air", 0),
                    "Mutable",
                    len(
                        [
                            p
                            for p in ALL_PLANETS
                            if MODALITIES[planets[p].sign] == "Mutable"
                        ]
                    ),
                    modality_tally.get("Mutable", 0),
                ],
                [
                    "💧 Water",
                    len([p for p in ALL_PLANETS if ELEMENTS[planets[p].sign] == "Water"]),
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
        table(
            ["Body", "Whole Sign House", "Porphyry House", "Note"],
            [
                [
                    "☽ Moon",
                    house_of(planets["Moon"].longitude, ws_cusps_raw),
                    house_of(planets["Moon"].longitude, porphyry_cusps_raw),
                    "Mention the house system whenever interpreting the Moon.",
                ],
            ],
        )
    )
    push("")

    push("### House Cusps")
    push("")
    push(
        table(
            ["House", "Whole Sign", "Porphyry"],
            [
                [i + 1, fmt_deg(ws_houses[i]), fmt_deg(porphyry_houses[i])]
                for i in range(12)
            ],
        )
    )
    push("")

    # ---------- 2. Major Aspects ----------
    push("## 2. Major Aspects")
    push("")
    push(
        table(
            ["Body A", "Body B", "Aspect", "Orb"],
            [[r["a"], r["b"], r["aspect"], r["orb"]] for r in aspect_rows],
        )
    )
    push("")
    key_conjunction_rows = [r for r in aspect_rows if r["aspect"] == "Conjunction"]
    push("### Key Natal Conjunctions")
    push("")
    push(
        table(
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

    # ---------- 3. Vedic Layer ----------
    push("## 3. Vedic (Sidereal, Lahiri Ayanamsha)")
    push("")
    push(
        table(
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

    # ---------- 4. Numerology ----------
    push("## 4. Numerology (Pythagorean)")
    push("")
    push(
        table(
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
        table(
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
        table(
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
        table(
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

    # ---------- 5. Chinese Four Pillars ----------
    push("## 5. Chinese Zodiac — Four Pillars (BaZi)")
    push("")
    push(
        f"_Calculated from local civil birth time: {inp.birth_date} "
        f"{inp.birth_time} ({inp.timezone})._"
    )
    push("")
    push(
        table(
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

    # ---------- 6. Human Design ----------
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
        table(
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
        table(
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
        table(
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
        table(
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
            table(
                ["Channel", "Name"],
                [
                    [f"{ch.gates[0]}–{ch.gates[1]}", ch.name]
                    for ch in hd.active_channels
                ],
            )
        )
    push("")

    # ---------- 7. Gene Keys ----------
    push("## 7. Gene Keys — The Activation Sequence")
    push("")
    push(
        "_Calculation note: Gene Keys gates/lines are computed directly from the same "
        "Sun/Earth gate-line longitudes used above; verify if the Human Design "
        "gate-line source is overridden externally._"
    )
    push("")
    push(
        table(
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

    # ---------- 8. Mayan Tzolkin ----------
    push("## 8. Mayan Tzolkin (Traditional GMT correlation + Dreamspell label)")
    push("")
    push(
        table(
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

    # ---------- Footer ----------
    push("---")
    push("")
    push(
        "_Generated by quantuum-blueprint calculator — every number above is computed "
        "from the birth data above; nothing is sourced from an LLM._"
    )
    push("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# NatalProfile adapter
# ---------------------------------------------------------------------------


def from_natal_profile(profile: Any) -> BlueprintInput:
    """Build a BlueprintInput from a duck-typed NatalProfile-like object.

    Avoids a hard import of the DB layer so this module stays importable
    without it.
    """
    return BlueprintInput(
        full_name=profile.full_name,
        birth_date=profile.birth_date.isoformat(),
        birth_time=profile.birth_time.strftime("%H:%M"),
        birth_place=profile.birth_place,
        latitude=float(profile.latitude),
        longitude=float(profile.longitude),
        timezone=profile.timezone,
        for_year=profile.for_year,
    )
