"""Chinese Zodiac (BaZi / Four Pillars).

Ported from chinese.ts — behavior must match exactly.

Uses lunar-python (6tail) for the sexagenary year/month/day/hour pillars
from the LOCAL civil birth date/time. BaZi hour branches are local-time
based, so do not derive them from the UTC instant.
"""

from __future__ import annotations

from dataclasses import dataclass

from lunar_python import Solar

# ---------------------------------------------------------------------------
# Heavenly Stems (天干)
# ---------------------------------------------------------------------------

STEMS: dict[str, dict[str, str]] = {
    "甲": {"name": "Jia",  "element": "Wood",  "polarity": "Yang"},
    "乙": {"name": "Yi",   "element": "Wood",  "polarity": "Yin"},
    "丙": {"name": "Bing", "element": "Fire",  "polarity": "Yang"},
    "丁": {"name": "Ding", "element": "Fire",  "polarity": "Yin"},
    "戊": {"name": "Wu",   "element": "Earth", "polarity": "Yang"},
    "己": {"name": "Ji",   "element": "Earth", "polarity": "Yin"},
    "庚": {"name": "Geng", "element": "Metal", "polarity": "Yang"},
    "辛": {"name": "Xin",  "element": "Metal", "polarity": "Yin"},
    "壬": {"name": "Ren",  "element": "Water", "polarity": "Yang"},
    "癸": {"name": "Gui",  "element": "Water", "polarity": "Yin"},
}

# ---------------------------------------------------------------------------
# Earthly Branches (地支)
# ---------------------------------------------------------------------------

BRANCHES: dict[str, dict[str, str]] = {
    "子": {"name": "Zi",   "animal": "Rat"},
    "丑": {"name": "Chou", "animal": "Ox"},
    "寅": {"name": "Yin",  "animal": "Tiger"},
    "卯": {"name": "Mao",  "animal": "Rabbit"},
    "辰": {"name": "Chen", "animal": "Dragon"},
    "巳": {"name": "Si",   "animal": "Snake"},
    "午": {"name": "Wu",   "animal": "Horse"},
    "未": {"name": "Wei",  "animal": "Goat"},
    "申": {"name": "Shen", "animal": "Monkey"},
    "酉": {"name": "You",  "animal": "Rooster"},
    "戌": {"name": "Xu",   "animal": "Dog"},
    "亥": {"name": "Hai",  "animal": "Pig"},
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChinesePillar:
    stem: str
    branch: str
    element: str
    polarity: str
    animal: str
    full: str
    chinese: str


@dataclass(frozen=True)
class ChinesePillars:
    year: ChinesePillar
    month: ChinesePillar
    day: ChinesePillar
    hour: ChinesePillar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def pillar_from_gan_zhi(gan_zhi: str) -> ChinesePillar:
    gan = gan_zhi[0]
    zhi = gan_zhi[1]
    stem = STEMS.get(gan)
    branch = BRANCHES.get(zhi)
    if stem is None or branch is None:
        raise ValueError(f"Unsupported BaZi pillar: {gan_zhi}")
    full = f"{stem['name']}-{branch['name']} ({stem['element']} {branch['animal']})"
    return ChinesePillar(
        stem=stem["name"],
        branch=branch["name"],
        element=stem["element"],
        polarity=stem["polarity"],
        animal=branch["animal"],
        full=full,
        chinese=gan_zhi,
    )


def chinese_pillars_from_local(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int = 0,
) -> ChinesePillars:
    """Return the Four Pillars (BaZi) for a LOCAL civil date/time."""
    solar = Solar.fromYmdHms(year, month, day, hour, minute, second)
    year_p, month_p, day_p, hour_p = solar.getLunar().getBaZi()
    return ChinesePillars(
        year=pillar_from_gan_zhi(year_p),
        month=pillar_from_gan_zhi(month_p),
        day=pillar_from_gan_zhi(day_p),
        hour=pillar_from_gan_zhi(hour_p),
    )


def pillar_summary(p: ChinesePillar) -> str:
    return f"{p.polarity} {p.element} {p.animal} ({p.full}; {p.chinese})"
