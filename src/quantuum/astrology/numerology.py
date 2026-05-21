"""Pythagorean numerology calculator.

Ported from numerology.ts — behavior must match exactly, including master-number
preservation (11/22/33) and the Y-as-vowel adjacency rule.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from quantuum.astrology.util import reduce_numerology

# ---------------------------------------------------------------------------
# Pythagorean letter→value map
# ---------------------------------------------------------------------------

PYTHAGOREAN: dict[str, int] = {
    "A": 1, "J": 1, "S": 1,
    "B": 2, "K": 2, "T": 2,
    "C": 3, "L": 3, "U": 3,
    "D": 4, "M": 4, "V": 4,
    "E": 5, "N": 5, "W": 5,
    "F": 6, "O": 6, "X": 6,
    "G": 7, "P": 7, "Y": 7,
    "H": 8, "Q": 8, "Z": 8,
    "I": 9, "R": 9,
}

VOWELS: frozenset[str] = frozenset({"A", "E", "I", "O", "U"})

# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------


def letters_only(name: str) -> str:
    """Uppercase → NFD normalize → strip combining marks → keep [A-Z] only."""
    upper = name.upper()
    nfd = unicodedata.normalize("NFD", upper)
    # Drop combining characters (unicodedata.combining returns non-zero for them)
    stripped = "".join(ch for ch in nfd if not unicodedata.combining(ch))
    return "".join(ch for ch in stripped if "A" <= ch <= "Z")


def letter_value(letter: str) -> int:
    """Return the Pythagorean value of a letter (0 if not in map)."""
    return PYTHAGOREAN.get(letter, 0)


def is_vowel(letter: str, prev: str) -> bool:
    """Return True if letter is a vowel or is Y adjacent to a consonant."""
    if letter in VOWELS:
        return True
    # Treat Y as vowel only when preceded by a consonant (not a vowel, not empty).
    if letter == "Y" and prev and prev not in VOWELS:
        return True
    return False


# ---------------------------------------------------------------------------
# name_sum
# ---------------------------------------------------------------------------


def name_sum(name: str, mode: str) -> int:
    """Sum letter values in *name* filtered by *mode* ('all'/'vowels'/'consonants').

    Returns reduce_numerology(sum).
    """
    upper = letters_only(name)
    total = 0
    prev = ""
    for ch in upper:
        vowel = is_vowel(ch, prev)
        include = (
            mode == "all"
            or (mode == "vowels" and vowel)
            or (mode == "consonants" and not vowel and ch != "Y")
            or (mode == "consonants" and ch == "Y" and not vowel)
        )
        if include:
            total += letter_value(ch)
        prev = ch
    return reduce_numerology(total)


# ---------------------------------------------------------------------------
# reduce_digits
# ---------------------------------------------------------------------------


def reduce_digits(s: int | str, keep_master: bool = True) -> int:
    """Sum the decimal digits of str(s), then reduce_numerology the result."""
    total = sum(int(ch) for ch in str(s) if ch.isdigit())
    return reduce_numerology(total, keep_master)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Challenges:
    c1: int
    c2: int
    c3: int
    c4: int


@dataclass(frozen=True)
class Pinnacles:
    p1: int
    p2: int
    p3: int
    p4: int


@dataclass(frozen=True)
class Numerology:
    life_path: int
    birth_day: int
    destiny: int
    soul_urge: int
    personality: int
    maturity: int
    attitude: int
    personal_year: int
    personal_year_target: int
    challenges: Challenges
    pinnacles: Pinnacles


# ---------------------------------------------------------------------------
# Main calculator
# ---------------------------------------------------------------------------


def calculate_numerology(
    full_name: str,
    birth_year: int,
    birth_month: int,
    birth_day: int,
    for_year: int,
) -> Numerology:
    """Compute Pythagorean numerology from birth data and a target year."""
    m = reduce_numerology(birth_month)
    d = reduce_numerology(birth_day)
    y = reduce_numerology(birth_year)
    life_path = reduce_numerology(m + d + y)

    destiny = name_sum(full_name, "all")
    soul_urge = name_sum(full_name, "vowels")
    personality = name_sum(full_name, "consonants")
    maturity = reduce_numerology(life_path + destiny)
    attitude = reduce_numerology(reduce_numerology(birth_month) + reduce_numerology(birth_day))

    personal_year = reduce_numerology(
        reduce_numerology(birth_month)
        + reduce_numerology(birth_day)
        + reduce_numerology(for_year)
    )

    # Pinnacles: P1=month+day; P2=day+year; P3=P1+P2; P4=month+year
    p1 = reduce_numerology(reduce_numerology(birth_month) + reduce_numerology(birth_day))
    p2 = reduce_numerology(reduce_numerology(birth_day) + reduce_numerology(birth_year))
    p3 = reduce_numerology(p1 + p2)
    p4 = reduce_numerology(reduce_numerology(birth_month) + reduce_numerology(birth_year))

    # Challenges: |month-day|, |day-year|, |C1-C2|, |month-year|
    # keep_master=False throughout — matches TS `false` argument
    c1 = reduce_numerology(
        abs(reduce_numerology(birth_month, False) - reduce_numerology(birth_day, False)),
        False,
    )
    c2 = reduce_numerology(
        abs(reduce_numerology(birth_day, False) - reduce_numerology(birth_year, False)),
        False,
    )
    c3 = reduce_numerology(abs(c1 - c2), False)
    c4 = reduce_numerology(
        abs(reduce_numerology(birth_month, False) - reduce_numerology(birth_year, False)),
        False,
    )

    return Numerology(
        life_path=life_path,
        birth_day=reduce_numerology(birth_day),
        destiny=destiny,
        soul_urge=soul_urge,
        personality=personality,
        maturity=maturity,
        attitude=attitude,
        personal_year=personal_year,
        personal_year_target=for_year,
        challenges=Challenges(c1=c1, c2=c2, c3=c3, c4=c4),
        pinnacles=Pinnacles(p1=p1, p2=p2, p3=p3, p4=p4),
    )
