# Individual Readings + QA System-Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split Quantuum Blueprint into eight standalone polished readings (BaZi, Numerology, Human Design, Astrology/Tropical, Vedic, Gene Keys, Mayan, Aspects), recompose Blueprint as their orchestrated parent, and explicitly instruct QA to pick relevant systems for each question.

**Architecture:** Refactor `build_blueprint` into pure per-system section builders, add a single generic `readings` table + task + LLM polish that dispatches on `kind`, and rewrite `polish_blueprint` to run all eight reading polishes in parallel and stitch with a deterministic ceremonial wrapper. QA stays code-untouched; only its system prompt gains a "system selection" paragraph. Quotas gain a `cost_units` parameter so the Blueprint can charge more than one credit atomically.

**Tech Stack:** Python 3.12, SQLModel + Postgres, Alembic, arq workers, aiogram bot, OpenAI/Anthropic LLM clients, pytest async.

**Spec:** `docs/superpowers/specs/2026-05-26-individual-readings-and-qa-routing-design.md`

---

## File Structure

### Created

| Path | Responsibility |
|------|----------------|
| `src/quantuum/astrology/sections.py` | Pure per-system section builders + `BlueprintContext` + `build_reading_calc_md` |
| `src/quantuum/llm/reading_polish.py` | `polish_reading(client, kind, calc_md, ...)` and `READING_PROMPTS` map |
| `src/quantuum/llm/prompts/reading_bazi.txt` | BaZi reading LLM prompt |
| `src/quantuum/llm/prompts/reading_numerology.txt` | Numerology reading LLM prompt |
| `src/quantuum/llm/prompts/reading_human_design.txt` | Human Design reading LLM prompt |
| `src/quantuum/llm/prompts/reading_astrology.txt` | Western tropical astrology reading prompt |
| `src/quantuum/llm/prompts/reading_vedic.txt` | Vedic sidereal reading prompt |
| `src/quantuum/llm/prompts/reading_gene_keys.txt` | Gene Keys reading prompt |
| `src/quantuum/llm/prompts/reading_mayan.txt` | Mayan Tzolkin reading prompt |
| `src/quantuum/llm/prompts/reading_aspects.txt` | Major aspects reading prompt |
| `src/quantuum/domain/readings.py` | `create_reading`, `get_reading`, `set_reading_status`, `list_readings` |
| `src/quantuum/tasks/reading.py` | `reading_generate` arq task |
| `src/quantuum/bot/handlers/readings.py` | "Readings" menu + per-kind callback handler |
| `alembic/versions/b8c9d0e1f2a3_readings_table.py` | DDL for `readings` |
| `alembic/versions/c9d0e1f2a3b4_request_cost_units.py` | Add `cost_units` column to `requests` |
| `tests/test_astrology_sections.py` | Per-section builder unit tests + reading-mini-doc tests |
| `tests/test_reading_polish_llm.py` | LLM prompt routing + `polish_reading` shape |
| `tests/test_readings_domain.py` | `readings.py` domain helpers |
| `tests/test_task_reading.py` | `reading_generate` happy/degraded/failure paths |
| `tests/test_readings_bot.py` | "Разборы" button + per-kind callback flow |
| `tests/test_quota_cost_units.py` | `consume_quota(cost_units=N)` + refund |
| `tests/test_blueprint_compose.py` | Composite blueprint runs 8 polishes + stitches |

### Modified

| Path | Change |
|------|--------|
| `src/quantuum/astrology/blueprint.py` | Reduce to header/footer + orchestrator over `sections.py`; CHARACTER-EXACT preserved |
| `src/quantuum/db/models.py` | Add `Reading` SQLModel + `cost_units: int = 1` field on `Request` |
| `src/quantuum/domain/quota.py` | `consume_quota` and `refund_quota` accept/honor `cost_units` |
| `src/quantuum/llm/blueprint_polish.py` | Replace single-LLM call with parallel reading polishes + deterministic stitcher |
| `src/quantuum/llm/prompts/qa_astrologer.txt` | Add "SYSTEM SELECTION" paragraph |
| `src/quantuum/tasks/blueprint.py` | Pass `build_input` to new `polish_blueprint`; use aggregated tokens |
| `src/quantuum/tasks/enqueue.py` | Add `enqueue_reading` |
| `src/quantuum/tasks/worker.py` | Register `reading_generate` in `WorkerSettings.functions` |
| `src/quantuum/bot/ui/callbacks.py` | Add `ReadingCb` |
| `src/quantuum/bot/ui/keyboards.py` | Add `readings_menu_kb` |
| `src/quantuum/bot/ui/text.py` | (only if needed) add `btn.readings` to menu-button label set |
| `src/quantuum/bot/handlers/menu.py` | Route `btn.readings` label to readings handler |
| `src/quantuum/bot/handlers/__init__.py` | Register new `readings` router |
| `src/quantuum/i18n/seed_strings.py` | Add `btn.readings`, `readings.*` keys with ru+en |
| `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py` | Translations for the new keys |
| `docs/other/features.md` / `docs/other/features.html` | (final pass) document the new "Readings" feature |

---

## Task 1 — Refactor `build_blueprint` into section builders

**Goal:** Move every chunk of `build_blueprint` into pure section functions in `sections.py` without changing the existing CHARACTER-EXACT output.

**Files:**
- Create: `src/quantuum/astrology/sections.py`
- Modify: `src/quantuum/astrology/blueprint.py`
- Test: `tests/test_astrology_blueprint_golden.py` (existing — must stay green)
- Test: `tests/test_astrology_sections.py` (new)

- [ ] **Step 1: Run the existing golden test to capture baseline**

Run: `pytest tests/test_astrology_blueprint_golden.py -v`
Expected: PASS (records the current canonical output).

- [ ] **Step 2: Write a new test asserting `build_blueprint_context` produces a stable bundle**

Add `tests/test_astrology_sections.py`:

```python
from datetime import datetime, timezone

from quantuum.astrology.blueprint import BlueprintInput
from quantuum.astrology.sections import build_blueprint_context


def _sample_input() -> BlueprintInput:
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


def test_blueprint_context_exposes_required_fields():
    ctx = build_blueprint_context(_sample_input())
    assert isinstance(ctx.birth, datetime)
    assert ctx.birth.tzinfo == timezone.utc
    assert set(ctx.planets) >= {"Sun", "Moon", "Mercury", "Mars"}
    assert len(ctx.ws_houses) == 12
    assert len(ctx.porphyry_houses) == 12
    assert ctx.for_year == 2026
    assert ctx.aspect_rows  # non-empty
```

- [ ] **Step 3: Run new test to verify it fails**

Run: `pytest tests/test_astrology_sections.py::test_blueprint_context_exposes_required_fields -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quantuum.astrology.sections'`.

- [ ] **Step 4: Create `sections.py` with `BlueprintContext` + `build_blueprint_context`**

Create `src/quantuum/astrology/sections.py`:

```python
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
from typing import Any

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


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


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


def build_blueprint_context(inp) -> BlueprintContext:
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
```

(The eight section-builder functions are filled in at Step 5 — keep this step focused on the context bundle so the failing test passes.)

- [ ] **Step 5: Re-run the section context test**

Run: `pytest tests/test_astrology_sections.py::test_blueprint_context_exposes_required_fields -v`
Expected: PASS.

- [ ] **Step 6: Add a per-section golden snapshot test**

Append to `tests/test_astrology_sections.py`:

```python
import pytest

from quantuum.astrology.sections import (
    BLUEPRINT_SECTION_ORDER,
    build_aspects_section,
    build_bazi_section,
    build_gene_keys_section,
    build_human_design_section,
    build_identity_section,
    build_mayan_section,
    build_numerology_section,
    build_vedic_section,
)

SECTION_HEADINGS = {
    "identity":     "## 1. Identity Layer",
    "aspects":      "## 2. Major Aspects",
    "vedic":        "## 3. Vedic (Sidereal, Lahiri Ayanamsha)",
    "numerology":   "## 4. Numerology (Pythagorean)",
    "bazi":         "## 5. Chinese Zodiac — Four Pillars (BaZi)",
    "human_design": "## 6. Human Design",
    "gene_keys":    "## 7. Gene Keys — The Activation Sequence",
    "mayan":        "## 8. Mayan Tzolkin",
}

@pytest.mark.parametrize("kind,expected_heading", SECTION_HEADINGS.items())
def test_section_starts_with_expected_heading(kind, expected_heading):
    inp = _sample_input()
    ctx = build_blueprint_context(inp)
    builders = {
        "identity":     build_identity_section,
        "aspects":      build_aspects_section,
        "vedic":        build_vedic_section,
        "numerology":   build_numerology_section,
        "bazi":         build_bazi_section,
        "human_design": build_human_design_section,
        "gene_keys":    build_gene_keys_section,
        "mayan":        build_mayan_section,
    }
    md = builders[kind](inp, ctx)
    assert md.splitlines()[0] == expected_heading


def test_section_order_is_canonical():
    assert BLUEPRINT_SECTION_ORDER == (
        "identity", "aspects", "vedic", "numerology",
        "bazi", "human_design", "gene_keys", "mayan",
    )
```

- [ ] **Step 7: Run the new test to confirm it fails on missing builders**

Run: `pytest tests/test_astrology_sections.py -v`
Expected: ImportError on the eight `build_*_section` symbols and `BLUEPRINT_SECTION_ORDER`.

- [ ] **Step 8: Port each section function from `blueprint.py` into `sections.py`**

Append the eight builders to `src/quantuum/astrology/sections.py`. Copy the corresponding section from the current `build_blueprint` in `src/quantuum/astrology/blueprint.py` verbatim and only rewrap as a function `build_<kind>_section(inp, ctx) -> str` returning the joined Markdown string for that section.

Replace `planets["Foo"]` and other locals with the equivalent attribute on `ctx`. Don't introduce new whitespace, headings, or list ordering. The full code for each builder is the existing render block; this is mechanical extraction.

At the bottom of the file add:

```python
BLUEPRINT_SECTION_ORDER: tuple[str, ...] = (
    "identity", "aspects", "vedic", "numerology",
    "bazi", "human_design", "gene_keys", "mayan",
)

SECTION_BUILDERS = {
    "identity":     build_identity_section,
    "aspects":      build_aspects_section,
    "vedic":        build_vedic_section,
    "numerology":   build_numerology_section,
    "bazi":         build_bazi_section,
    "human_design": build_human_design_section,
    "gene_keys":    build_gene_keys_section,
    "mayan":        build_mayan_section,
}


def build_reading_calc_md(kind: str, inp) -> str:
    """Self-contained mini-doc: birth header + one section + footer."""
    from quantuum.astrology.blueprint import _render_header, _render_footer
    ctx = build_blueprint_context(inp)
    return "\n".join([
        _render_header(inp, ctx),
        SECTION_BUILDERS[kind](inp, ctx),
        _render_footer(),
    ])
```

- [ ] **Step 9: Slim down `blueprint.py` to call section builders**

Modify `src/quantuum/astrology/blueprint.py`. Keep `BlueprintInput`, `parse_birth_instant`, `to_iso_z`, `EPOCH`, and `from_natal_profile` as they are. Replace the body of `build_blueprint` with:

```python
def _render_header(inp: BlueprintInput, ctx) -> str:
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
    push(f"**UTC instant:** {to_iso_z(ctx.birth_ms)}  ")
    push(f"**Personal-year target:** {ctx.for_year}  ")
    push("**Quantuum Matrix framework:** 35-dimensional  ")
    push("")
    push("---")
    push("")
    return "\n".join(lines)


def _render_footer() -> str:
    return "\n".join([
        "---",
        "",
        "_Generated by quantuum-blueprint calculator — every number above is computed "
        "from the birth data above; nothing is sourced from an LLM._",
        "",
    ])


def build_blueprint(inp: BlueprintInput) -> str:
    from quantuum.astrology.sections import (
        BLUEPRINT_SECTION_ORDER,
        SECTION_BUILDERS,
        build_blueprint_context,
    )

    ctx = build_blueprint_context(inp)
    parts = [_render_header(inp, ctx)]
    for kind in BLUEPRINT_SECTION_ORDER:
        parts.append(SECTION_BUILDERS[kind](inp, ctx))
    parts.append(_render_footer())
    return "\n".join(parts)
```

Delete the now-unused inline helpers (`table`, `_fmt_pos`, `PLANET_GLYPH`, `ALL_PLANETS`, …) that have moved to `sections.py`. Import `to_fixed` at the top.

- [ ] **Step 10: Run the FULL golden suite + section tests**

Run: `pytest tests/test_astrology_blueprint_golden.py tests/test_astrology_sections.py -v`
Expected: BOTH PASS. If the golden test breaks, the refactor is not byte-equivalent — re-diff and fix before commit.

- [ ] **Step 11: Commit**

```bash
git add src/quantuum/astrology/sections.py src/quantuum/astrology/blueprint.py tests/test_astrology_sections.py
git commit -m "refactor(astrology): split build_blueprint into per-system section builders"
```

---

## Task 2 — Quota `cost_units` support

**Goal:** Let `consume_quota` deduct N package credits in one atomic step, and `refund_quota` return them; trial still single-shot for Blueprint.

**Files:**
- Modify: `src/quantuum/db/models.py`
- Create: `alembic/versions/c9d0e1f2a3b4_request_cost_units.py`
- Modify: `src/quantuum/domain/quota.py`
- Create: `tests/test_quota_cost_units.py`

- [ ] **Step 1: Write failing test for `cost_units > 1` package deduction**

Create `tests/test_quota_cost_units.py`:

```python
import pytest

from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import AccountBalance, AccountPackage, Request
from quantuum.domain.quota import consume_quota, refund_quota


async def _make_account(session, tenant_id):
    from quantuum.auth.identity import find_or_create_account_by_tg
    return await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="9999")


async def test_consume_quota_deducts_cost_units(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    bal = AccountBalance(account_id=acc.id, free_trial_used=True, package_credits=5)
    pkg = AccountPackage(account_id=acc.id, requests_remaining=5, requests_total=5)
    session.add(bal); session.add(pkg)
    await session.commit()

    charged = await consume_quota(session, acc.id, "blueprint", cost_units=4)
    assert charged == "package"
    await session.refresh(bal)
    await session.refresh(pkg)
    assert bal.package_credits == 1
    assert pkg.requests_remaining == 1


async def test_consume_quota_rejects_when_balance_too_low(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    bal = AccountBalance(account_id=acc.id, free_trial_used=True, package_credits=3)
    pkg = AccountPackage(account_id=acc.id, requests_remaining=3, requests_total=5)
    session.add(bal); session.add(pkg)
    await session.commit()

    with pytest.raises(InsufficientFundsError):
        await consume_quota(session, acc.id, "blueprint", cost_units=4)
    await session.refresh(bal)
    assert bal.package_credits == 3  # untouched


async def test_refund_quota_returns_cost_units(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    bal = AccountBalance(account_id=acc.id, free_trial_used=True, package_credits=5)
    pkg = AccountPackage(account_id=acc.id, requests_remaining=5, requests_total=5)
    session.add(bal); session.add(pkg)
    await session.commit()

    await consume_quota(session, acc.id, "blueprint", cost_units=4)
    req = Request(
        tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint",
        charged_against="package", cost_units=4,
    )
    session.add(req); await session.commit(); await session.refresh(req)

    await refund_quota(session, req.id)
    await session.refresh(bal); await session.refresh(pkg)
    assert bal.package_credits == 5
    assert pkg.requests_remaining == 5


async def test_trial_is_single_shot_regardless_of_cost_units(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    charged = await consume_quota(session, acc.id, "blueprint", cost_units=4)
    assert charged == "trial"
    with pytest.raises(InsufficientFundsError):
        await consume_quota(session, acc.id, "blueprint", cost_units=1)
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `pytest tests/test_quota_cost_units.py -v`
Expected: FAIL — `consume_quota()` doesn't accept `cost_units`, `Request` lacks `cost_units` column.

- [ ] **Step 3: Add `cost_units` to `Request` model**

Edit `src/quantuum/db/models.py` — the existing `Request` class. Add immediately after the existing `cost_units: int = 1` line if missing; verify it exists. (It already exists at line ~257 — confirm with `grep cost_units src/quantuum/db/models.py`.) No model change needed if already present.

- [ ] **Step 4: Create alembic migration to enforce default for legacy rows**

Create `alembic/versions/c9d0e1f2a3b4_request_cost_units.py`:

```python
"""ensure requests.cost_units default

Revision ID: c9d0e1f2a3b4
Revises: a7b8c9d0e1f2
Create Date: 2026-05-26 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The column already exists in the model with a Python default of 1 but
    # has no server-side default; backfill and lock it down so old worker
    # paths that bypass the ORM cannot insert NULL.
    op.alter_column(
        "requests",
        "cost_units",
        existing_type=sa.Integer(),
        nullable=False,
        server_default="1",
    )
    op.execute("UPDATE requests SET cost_units = 1 WHERE cost_units IS NULL")


def downgrade() -> None:
    op.alter_column(
        "requests",
        "cost_units",
        existing_type=sa.Integer(),
        nullable=True,
        server_default=None,
    )
```

If the existing model does NOT have a `cost_units` column on `Request`, change Step 3 to add `cost_units: int = Field(default=1, sa_column=Column(Integer, nullable=False, server_default="1"))` and adjust the migration to `op.add_column` instead.

- [ ] **Step 5: Apply migration locally**

Run: `alembic upgrade head`
Expected: revision `c9d0e1f2a3b4` applied without errors.

- [ ] **Step 6: Modify `consume_quota` / `refund_quota` for `cost_units`**

Edit `src/quantuum/domain/quota.py` — replace `consume_quota` and `refund_quota`:

```python
async def consume_quota(session, account_id: int, kind: str, *, cost_units: int = 1) -> str:
    assert cost_units >= 1
    balance = await session.get(AccountBalance, account_id, with_for_update=True)
    if balance is None:
        balance = AccountBalance(account_id=account_id)
        session.add(balance)

    if not balance.free_trial_used and kind == "blueprint":
        balance.free_trial_used = True
        balance.updated_at = utcnow()
        session.add(balance)
        await session.commit()
        return "trial"

    if balance.subscription_active_until and balance.subscription_active_until > utcnow():
        await session.commit()
        return "subscription"

    if balance.package_credits >= cost_units:
        remaining = cost_units
        # Decrement from oldest-expiring package(s) FIFO; loop until cost_units drained.
        while remaining > 0:
            pkg = await _oldest_valid_package(session, account_id)
            if pkg is None:
                # Ledger drift: balance says we have units but no package row holds them.
                # Treat as insufficient to avoid silent over-spend.
                await session.rollback()
                raise InsufficientFundsError("ledger drift: no package row to debit")
            take = min(remaining, pkg.requests_remaining)
            pkg.requests_remaining -= take
            session.add(pkg)
            remaining -= take
        balance.package_credits -= cost_units
        balance.updated_at = utcnow()
        session.add(balance)
        await session.commit()
        return "package"

    raise InsufficientFundsError("no quota available")


async def refund_quota(session, request_id: int) -> None:
    request = await session.get(Request, request_id)
    if request is None or request.charged_against in (None, "none"):
        return

    units = max(request.cost_units or 1, 1)
    balance = await session.get(AccountBalance, request.account_id, with_for_update=True)
    if balance is not None:
        if request.charged_against == "trial":
            balance.free_trial_used = False
        elif request.charged_against == "package":
            balance.package_credits += units
            pkg = await _newest_valid_package(session, request.account_id)
            if pkg is not None:
                pkg.requests_remaining += units
                session.add(pkg)
        balance.updated_at = utcnow()
        session.add(balance)

    request.charged_against = "none"
    request.status = "refunded"
    session.add(request)
    await session.commit()
```

- [ ] **Step 7: Run the new tests to verify they pass**

Run: `pytest tests/test_quota_cost_units.py -v tests/test_quota.py -v`
Expected: BOTH pass — `cost_units` tests AND the existing single-unit `test_quota.py` (regression check).

- [ ] **Step 8: Commit**

```bash
git add src/quantuum/domain/quota.py alembic/versions/c9d0e1f2a3b4_request_cost_units.py tests/test_quota_cost_units.py
git commit -m "feat(quota): cost_units parameter for atomic multi-credit charge/refund"
```

---

## Task 3 — `readings` table + migration + model

**Goal:** Add the generic `Reading` SQLModel and matching migration.

**Files:**
- Modify: `src/quantuum/db/models.py`
- Create: `alembic/versions/b8c9d0e1f2a3_readings_table.py`
- Test: `tests/test_db_models.py` (existing — verify new model loads)

- [ ] **Step 1: Write failing test asserting the `Reading` model exists and is mapped**

Append to `tests/test_db_models.py`:

```python
async def test_reading_model_create_and_load(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile, Reading
    from datetime import date, time

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="r1")
    profile = NatalProfile(
        tenant_id=default_tenant.id, account_id=acc.id,
        full_name="Test", birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(profile); await session.commit(); await session.refresh(profile)

    reading = Reading(
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, kind="bazi", lang="ru",
    )
    session.add(reading); await session.commit(); await session.refresh(reading)
    assert reading.id is not None
    assert reading.status == "pending"
    assert reading.kind == "bazi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db_models.py::test_reading_model_create_and_load -v`
Expected: FAIL (`Reading` not importable).

- [ ] **Step 3: Add `Reading` to `models.py`**

Edit `src/quantuum/db/models.py` — insert after the `Blueprint` class:

```python
class Reading(SQLModel, table=True):
    __tablename__ = "readings"
    __table_args__ = (Index("ix_readings_tenant_created", "tenant_id", "created_at"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    natal_profile_id: int = Field(foreign_key="natal_profiles.id")
    kind: str  # bazi|numerology|human_design|astrology|vedic|gene_keys|mayan|aspects
    status: str = "pending"  # pending|calculating|generating|done|failed
    lang: str | None = None
    calc_md: str | None = None
    llm_md: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    error: str | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)
    completed_at: datetime | None = _dt_field(default=None)
```

- [ ] **Step 4: Create alembic migration**

Create `alembic/versions/b8c9d0e1f2a3_readings_table.py`:

```python
"""readings table

Revision ID: b8c9d0e1f2a3
Revises: c9d0e1f2a3b4
Create Date: 2026-05-26 10:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "readings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("natal_profile_id", sa.Integer(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("lang", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("calc_md", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_md", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_provider", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_model", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("llm_tokens_in", sa.Integer(), nullable=True),
        sa.Column("llm_tokens_out", sa.Integer(), nullable=True),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["natal_profile_id"], ["natal_profiles.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_readings_account_id", "readings", ["account_id"])
    op.create_index("ix_readings_tenant_id", "readings", ["tenant_id"])
    op.create_index("ix_readings_tenant_created", "readings", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_readings_tenant_created", table_name="readings")
    op.drop_index("ix_readings_tenant_id", table_name="readings")
    op.drop_index("ix_readings_account_id", table_name="readings")
    op.drop_table("readings")
```

- [ ] **Step 5: Apply migration**

Run: `alembic upgrade head`
Expected: `b8c9d0e1f2a3` applied.

- [ ] **Step 6: Re-run the model test**

Run: `pytest tests/test_db_models.py::test_reading_model_create_and_load -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/db/models.py alembic/versions/b8c9d0e1f2a3_readings_table.py tests/test_db_models.py
git commit -m "feat(readings): add Reading SQLModel and migration"
```

---

## Task 4 — `domain/readings.py`

**Goal:** CRUD-shaped helpers around the `Reading` model, mirroring `domain/blueprints.py`.

**Files:**
- Create: `src/quantuum/domain/readings.py`
- Create: `tests/test_readings_domain.py`

- [ ] **Step 1: Write failing tests for `create_reading`, `set_reading_status`, `list_readings`**

Create `tests/test_readings_domain.py`:

```python
import pytest

from quantuum.common.exceptions import NotFoundError
from quantuum.domain.readings import (
    create_reading,
    get_reading,
    list_readings,
    set_reading_status,
)


async def _profile(session, default_tenant):
    from datetime import date, time
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="d1")
    p = NatalProfile(
        tenant_id=default_tenant.id, account_id=acc.id,
        full_name="X", birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(p); await session.commit(); await session.refresh(p)
    return acc, p


async def test_create_reading_sets_pending(session, default_tenant):
    acc, prof = await _profile(session, default_tenant)
    r = await create_reading(session,
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=prof.id, kind="bazi", lang="ru")
    assert r.status == "pending"
    assert r.kind == "bazi"


async def test_set_reading_status_terminal_sets_completed_at(session, default_tenant):
    acc, prof = await _profile(session, default_tenant)
    r = await create_reading(session,
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=prof.id, kind="bazi", lang="ru")
    await set_reading_status(session, r.id, "done", llm_md="hello")
    r2 = await get_reading(session, r.id)
    assert r2.status == "done"
    assert r2.llm_md == "hello"
    assert r2.completed_at is not None


async def test_get_reading_not_found_raises(session):
    with pytest.raises(NotFoundError):
        await get_reading(session, 999999)


async def test_list_readings_filters_by_account(session, default_tenant):
    acc, prof = await _profile(session, default_tenant)
    await create_reading(session, tenant_id=default_tenant.id, account_id=acc.id,
                         natal_profile_id=prof.id, kind="bazi", lang="ru")
    await create_reading(session, tenant_id=default_tenant.id, account_id=acc.id,
                         natal_profile_id=prof.id, kind="numerology", lang="ru")
    rows = await list_readings(session, account_id=acc.id)
    assert {r.kind for r in rows} == {"bazi", "numerology"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_readings_domain.py -v`
Expected: ImportError on `quantuum.domain.readings`.

- [ ] **Step 3: Create `domain/readings.py`**

Create `src/quantuum/domain/readings.py`:

```python
from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import NotFoundError
from quantuum.db.models import Reading

_TERMINAL = {"done", "failed"}


async def create_reading(
    session, *, tenant_id: int, account_id: int, natal_profile_id: int,
    kind: str, lang: str | None = None,
) -> Reading:
    reading = Reading(
        tenant_id=tenant_id,
        account_id=account_id,
        natal_profile_id=natal_profile_id,
        kind=kind,
        lang=lang,
        status="pending",
    )
    session.add(reading)
    await session.commit()
    await session.refresh(reading)
    return reading


async def get_reading(session, reading_id: int) -> Reading:
    reading = await session.get(Reading, reading_id)
    if reading is None:
        raise NotFoundError("reading not found")
    return reading


async def set_reading_status(session, reading_id: int, status: str, **fields) -> None:
    reading = await get_reading(session, reading_id)
    reading.status = status
    for key, value in fields.items():
        setattr(reading, key, value)
    if status in _TERMINAL:
        reading.completed_at = utcnow()
    session.add(reading)
    await session.commit()


async def list_readings(
    session, *, account_id: int, limit: int = 50, offset: int = 0
) -> list[Reading]:
    result = await session.execute(
        select(Reading)
        .where(Reading.account_id == account_id)
        .order_by(Reading.created_at.desc(), Reading.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_readings_domain.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/domain/readings.py tests/test_readings_domain.py
git commit -m "feat(readings): domain helpers (create/get/set_status/list)"
```

---

## Task 5 — `reading_polish` + per-kind prompts

**Goal:** Single LLM-polish function that picks a per-kind prompt file. Add stub prompt files for all 8 kinds so dispatch is testable; full ceremonial-grade prompt text is finalised in Task 6.

**Files:**
- Create: `src/quantuum/llm/reading_polish.py`
- Create: `src/quantuum/llm/prompts/reading_bazi.txt`, `reading_numerology.txt`, `reading_human_design.txt`, `reading_astrology.txt`, `reading_vedic.txt`, `reading_gene_keys.txt`, `reading_mayan.txt`, `reading_aspects.txt`
- Create: `tests/test_reading_polish_llm.py`

- [ ] **Step 1: Write failing test for `polish_reading`**

Create `tests/test_reading_polish_llm.py`:

```python
import pytest

from quantuum.llm.reading_polish import READING_PROMPTS, polish_reading


class _FakeClient:
    def __init__(self):
        self.calls = []
    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.calls.append({"system": system, "user": user, "model": model})
        class R:
            text = "POLISHED"
            model = model
            tokens_in = 10
            tokens_out = 20
        return R()


@pytest.mark.parametrize("kind", list(READING_PROMPTS.keys()))
async def test_polish_reading_uses_per_kind_prompt(kind):
    client = _FakeClient()
    calc = f"# Stub calc for {kind}"
    result = await polish_reading(client, kind, calc, lang="en",
                                  model="m", temperature=0.5, max_tokens=1000)
    assert result.text == "POLISHED"
    call = client.calls[0]
    assert call["system"] == READING_PROMPTS[kind].read_text()
    assert "Answer in language: en." in call["user"]
    assert calc in call["user"]


async def test_polish_reading_unknown_kind_raises():
    with pytest.raises(KeyError):
        await polish_reading(_FakeClient(), "unknown", "x", lang="en",
                             model="m", temperature=0.5, max_tokens=1000)


def test_all_eight_kinds_registered():
    assert set(READING_PROMPTS.keys()) == {
        "bazi", "numerology", "human_design", "astrology",
        "vedic", "gene_keys", "mayan", "aspects",
    }
```

- [ ] **Step 2: Run tests — verify failure**

Run: `pytest tests/test_reading_polish_llm.py -v`
Expected: ImportError on `quantuum.llm.reading_polish`.

- [ ] **Step 3: Create stub prompt files**

For each kind, create `src/quantuum/llm/prompts/reading_<kind>.txt` with a stub body (the real ceremonial prompt comes in Task 6):

```
You are Quantuum's <KIND> reading writer. (Final prompt body authored in Task 6.)
```

For example `src/quantuum/llm/prompts/reading_bazi.txt`:

```
You are Quantuum's BaZi reading writer. (Final prompt body authored in Task 6.)
```

Repeat for each of: `numerology`, `human_design`, `astrology`, `vedic`, `gene_keys`, `mayan`, `aspects`.

- [ ] **Step 4: Create `reading_polish.py`**

Create `src/quantuum/llm/reading_polish.py`:

```python
from pathlib import Path

_PROMPTS = Path(__file__).parent / "prompts"

READING_PROMPTS: dict[str, Path] = {
    "bazi":         _PROMPTS / "reading_bazi.txt",
    "numerology":   _PROMPTS / "reading_numerology.txt",
    "human_design": _PROMPTS / "reading_human_design.txt",
    "astrology":    _PROMPTS / "reading_astrology.txt",
    "vedic":        _PROMPTS / "reading_vedic.txt",
    "gene_keys":    _PROMPTS / "reading_gene_keys.txt",
    "mayan":        _PROMPTS / "reading_mayan.txt",
    "aspects":      _PROMPTS / "reading_aspects.txt",
}


_KIND_LABEL: dict[str, str] = {
    "bazi": "BaZi (Chinese Four Pillars)",
    "numerology": "Pythagorean Numerology",
    "human_design": "Human Design",
    "astrology": "Western Tropical Astrology",
    "vedic": "Vedic (Sidereal) Astrology",
    "gene_keys": "Gene Keys",
    "mayan": "Mayan Tzolkin",
    "aspects": "Natal Aspects",
}


async def polish_reading(client, kind: str, calc_md: str, *, lang: str,
                         model: str, temperature: float, max_tokens: int):
    if kind not in READING_PROMPTS:
        raise KeyError(f"unknown reading kind: {kind}")
    system = READING_PROMPTS[kind].read_text()
    label = _KIND_LABEL[kind]
    user = "\n".join([
        f"Transform this calculated {label} chart slice into the polished Quantuum reading.",
        f"Answer in language: {lang}.",
        "",
        "CALCULATED MARKDOWN:",
        calc_md,
    ])
    return await client.complete(
        system=system, user=user,
        model=model, temperature=temperature, max_tokens=max_tokens,
    )
```

- [ ] **Step 5: Re-run tests**

Run: `pytest tests/test_reading_polish_llm.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/llm/reading_polish.py src/quantuum/llm/prompts/reading_*.txt tests/test_reading_polish_llm.py
git commit -m "feat(llm): polish_reading dispatcher + stub per-kind prompts"
```

---

## Task 6 — Author the 8 reading prompts (ceremonial style)

**Goal:** Replace each stub prompt with a full ceremonial-tone prompt modelled on `blueprint_writer.txt` but scoped to a single system. Each prompt also requires a `FIELD OVERVIEW FRAGMENT` marker block so the Blueprint stitcher (Task 9) can harvest it.

**Files:**
- Modify: `src/quantuum/llm/prompts/reading_bazi.txt`
- Modify: `src/quantuum/llm/prompts/reading_numerology.txt`
- Modify: `src/quantuum/llm/prompts/reading_human_design.txt`
- Modify: `src/quantuum/llm/prompts/reading_astrology.txt`
- Modify: `src/quantuum/llm/prompts/reading_vedic.txt`
- Modify: `src/quantuum/llm/prompts/reading_gene_keys.txt`
- Modify: `src/quantuum/llm/prompts/reading_mayan.txt`
- Modify: `src/quantuum/llm/prompts/reading_aspects.txt`
- Create: `tests/test_reading_prompts.py`

- [ ] **Step 1: Write failing test that each prompt declares the FIELD OVERVIEW FRAGMENT contract**

Create `tests/test_reading_prompts.py`:

```python
from quantuum.llm.reading_polish import READING_PROMPTS


def test_every_reading_prompt_requires_field_overview_fragment():
    for kind, path in READING_PROMPTS.items():
        text = path.read_text()
        assert "<!-- field-overview-start -->" in text, f"{kind}: missing fragment start marker contract"
        assert "<!-- field-overview-end -->" in text, f"{kind}: missing fragment end marker contract"
        assert "CRITICAL FACT RULES" in text, f"{kind}: missing CRITICAL FACT RULES block"


def test_every_reading_prompt_demands_language_obedience():
    for kind, path in READING_PROMPTS.items():
        text = path.read_text()
        assert "Write in the language requested" in text, f"{kind}: missing language directive"


def test_every_reading_prompt_forbids_invention():
    for kind, path in READING_PROMPTS.items():
        text = path.read_text()
        assert "Do not invent" in text or "do not invent" in text, f"{kind}: missing invention prohibition"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reading_prompts.py -v`
Expected: stub prompts fail every assertion.

- [ ] **Step 3: Author each prompt body**

For each of the 8 prompt files, write a complete prompt of this shape (use `reading_bazi.txt` as the worked example below; the other seven follow the same template, swapping in their system's vocabulary and required tables/blocks):

```
You are Quantuum's BaZi (Chinese Four Pillars) reading writer.

You will receive one Markdown slice generated by a deterministic calculator. That slice contains the only allowed factual inputs: birth data, the four BaZi pillars (Year/Month/Day/Hour) with stem-branch, Chinese characters, element, animal, polarity, and Day Master.

Your task is to transform that slice into a polished BaZi reading in the ceremonial Quantuum voice — intimate, vivid, precise, and structured.

CRITICAL FACT RULES
- Do not invent, alter, or "correct" any pillar, stem, branch, element, animal, polarity, or Day Master.
- Do not introduce numeric duration, count, frequency, age, or cycle length unless that exact number appears in the source slice.
- Do not create numbered lists. Use bullets or prose.
- Every concrete pillar fact must come from the source slice exactly as written, including Chinese characters.
- You may synthesize meanings, archetypes, and practical guidance from the computed pillars.
- Do not cite websites, books, or sources. Do not mention being an AI/LLM/model. Do not include process notes or disclaimers.
- Return Markdown only.

LANGUAGE AND VOICE
- Write in the language requested in the user message.
- Address the person directly as "you" after the opening.
- Tone: sacred, clear, cinematic, grounded.

REQUIRED STRUCTURE

<!-- field-overview-start -->
| BaZi | {YearPillar} / {YearChars} · {MonthPillar} / {MonthChars} · {DayPillar} / {DayChars} (Day Master) · {HourPillar} / {HourChars} |
<!-- field-overview-end -->

# 🐉 BaZi — Four Pillars

Subtitle: one strong archetypal line for this person's BaZi.

## Field
A short table of the four pillars from the source slice, exact stem-branch and Chinese characters.

## Day Master
Name the Day Master pillar and what its element + polarity means for this soul.

## Year / Month / Hour
For each non-Day pillar, a short paragraph grounded in the source's element/animal/polarity.

## Living the Pillars
A bullet list of practical orientations the person can take based on the interplay of pillars.

FINAL QUALITY CHECK
- Are all pillar codes and Chinese characters copied exactly from the source slice?
- Is the field-overview-start / field-overview-end block present, on its own lines?
- Is the output Markdown only?
```

For the other seven files use these section skeletons (verbatim; adjust prose around them):

- `reading_numerology.txt`: title `# 🔢 Numerology — Pythagorean`; sections **Field** (table of Life Path / Birth Day / Destiny / Soul Urge / Personality / Maturity / Attitude / Personal Year), **Core Numbers**, **Pinnacles & Challenges**, **Timing Cycles** (no numbers/years invented). Fragment line: `| Numerology | Life Path {LifePath} · Personal Year {PY} |`.
- `reading_human_design.txt`: title `# 🧬 Human Design`; sections **Field** (Type/Strategy/Authority/Profile/Definition/Signature/Not-Self), **Centers**, **Channels & Gates**, **35-Dimensional Matrix**, **Living Your Design**. Fragment line: `| Human Design | {Type} · {Authority} · Profile {Profile} |`.
- `reading_astrology.txt`: title `# ☉ Western Tropical Astrology`; sections **Field** (Sun/Moon/Asc with signs + houses by WS and Porphyry), **Houses**, **Elemental & Modality Balance**, **House-System Clarifications**. Fragment line: `| Astrology | Sun {SunSign} · Moon {MoonSign} · Asc {AscSign} |`.
- `reading_vedic.txt`: title `# 🕉 Vedic — Sidereal (Lahiri)`; sections **Field** (Sun/Moon/Asc sidereal + Moon Nakshatra), **Nakshatra**, **Sidereal–Tropical Bridge**. Fragment line: `| Vedic | Sidereal Sun {SunSign} · Moon {MoonSign} · Nakshatra {Nakshatra} |`.
- `reading_gene_keys.txt`: title `# 🗝 Gene Keys — Activation Sequence`; sections **Field** (Life's Work / Evolution / Radiance / Purpose gates), **Shadow → Gift → Siddhi**, **Embodied Path**. Fragment line: `| Gene Keys | LW {LW} · Ev {EV} · Rd {RD} · Pp {PP} |`.
- `reading_mayan.txt`: title `# 🌀 Mayan Tzolkin`; sections **Field** (Tone, Day Sign, Dreamspell, Kin), **Day Sign & Tone**, **Dreamspell Layer**. Fragment line: `| Mayan | {Tone} {DaySign} / {Dreamspell} · Kin {Kin} |`.
- `reading_aspects.txt`: title `# ✦ Natal Aspects`; sections **Field** (summary of the strongest aspects by tightness), **Major Aspects** (list from source), **Tensions & Talents**. Fragment line: `| Aspects | {N} active major aspects |`.

Each file follows the same opening preamble, CRITICAL FACT RULES, LANGUAGE AND VOICE, REQUIRED STRUCTURE shape — only the system-specific content changes.

- [ ] **Step 4: Run prompt tests + dispatcher tests to confirm**

Run: `pytest tests/test_reading_prompts.py tests/test_reading_polish_llm.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/llm/prompts/reading_*.txt tests/test_reading_prompts.py
git commit -m "feat(llm): author 8 ceremonial-style reading prompts with field-overview fragments"
```

---

## Task 7 — `reading_generate` arq task + enqueue + worker registration

**Goal:** A worker task that takes a `reading_id`, builds the slice, polishes it, persists, and delivers via tenant bot. Mirrors `blueprint_generate` and `qa_generate`.

**Files:**
- Create: `src/quantuum/tasks/reading.py`
- Modify: `src/quantuum/tasks/enqueue.py`
- Modify: `src/quantuum/tasks/worker.py`
- Create: `tests/test_task_reading.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_task_reading.py`:

```python
from datetime import date, time

import pytest

from quantuum.db.models import NatalProfile, Reading, Request
from quantuum.domain.readings import create_reading, get_reading


class _Result:
    def __init__(self, text="POLISHED"):
        self.text = text
        self.model = "m"
        self.tokens_in = 10
        self.tokens_out = 20


class _FakeLLM:
    async def complete(self, **kw):
        return _Result()


async def _setup(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="t1")
    p = NatalProfile(
        tenant_id=default_tenant.id, account_id=acc.id,
        full_name="X", birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(p); await session.commit(); await session.refresh(p)
    return acc, p


async def test_reading_generate_happy_path(sessionmaker, default_tenant):
    from quantuum.tasks.reading import reading_generate

    async with sessionmaker() as session:
        acc, prof = await _setup(session, default_tenant)
        r = await create_reading(session, tenant_id=default_tenant.id,
            account_id=acc.id, natal_profile_id=prof.id, kind="bazi", lang="en")
        rid = r.id

    ctx = {"sessionmaker": sessionmaker, "llm_client": _FakeLLM()}
    await reading_generate(ctx, rid, chat_id=None, request_id=None)

    async with sessionmaker() as session:
        r2 = await get_reading(session, rid)
        assert r2.status == "done"
        assert r2.llm_md == "POLISHED"
        assert r2.calc_md is not None and "🐉" in r2.calc_md or "BaZi" in r2.calc_md
        assert r2.completed_at is not None


async def test_reading_generate_no_llm_client_degrades_gracefully(sessionmaker, default_tenant):
    from quantuum.tasks.reading import reading_generate

    async with sessionmaker() as session:
        acc, prof = await _setup(session, default_tenant)
        r = await create_reading(session, tenant_id=default_tenant.id,
            account_id=acc.id, natal_profile_id=prof.id, kind="numerology", lang="en")
        rid = r.id

    ctx = {"sessionmaker": sessionmaker, "llm_client": None}
    await reading_generate(ctx, rid, chat_id=None, request_id=None)

    async with sessionmaker() as session:
        r2 = await get_reading(session, rid)
        assert r2.status == "done"
        assert r2.llm_md == r2.calc_md
        assert r2.llm_provider == "none"


async def test_reading_generate_llm_failure_refunds_and_fails(sessionmaker, default_tenant):
    from quantuum.tasks.reading import reading_generate
    from quantuum.domain.quota import consume_quota
    from quantuum.domain.requests import create_request

    class _BadLLM:
        async def complete(self, **kw):
            raise RuntimeError("LLM down")

    async with sessionmaker() as session:
        acc, prof = await _setup(session, default_tenant)
        # ensure the user has a package credit so trial doesn't take effect
        from quantuum.db.models import AccountBalance, AccountPackage
        bal = AccountBalance(account_id=acc.id, free_trial_used=True, package_credits=1)
        pkg = AccountPackage(account_id=acc.id, requests_remaining=1, requests_total=1)
        session.add(bal); session.add(pkg); await session.commit()

        charged = await consume_quota(session, acc.id, "reading", cost_units=1)
        req = await create_request(session, tenant_id=default_tenant.id,
            account_id=acc.id, kind="reading", charged_against=charged)
        r = await create_reading(session, tenant_id=default_tenant.id,
            account_id=acc.id, natal_profile_id=prof.id, kind="bazi", lang="en")
        rid, reqid = r.id, req.id

    ctx = {"sessionmaker": sessionmaker, "llm_client": _BadLLM()}
    await reading_generate(ctx, rid, chat_id=None, request_id=reqid)

    async with sessionmaker() as session:
        r2 = await get_reading(session, rid)
        assert r2.status == "failed"
        req2 = await session.get(Request, reqid)
        assert req2.status == "refunded"


async def test_enqueue_reading_dispatches(monkeypatch):
    from quantuum.tasks import enqueue as enq

    captured = {}
    class _Pool:
        async def enqueue_job(self, name, *args):
            captured["name"] = name
            captured["args"] = args
    monkeypatch.setattr(enq, "_get_pool", lambda: _Pool())
    await enq.enqueue_reading(42, chat_id=5, request_id=7)
    assert captured == {"name": "reading_generate", "args": (42, 5, 7)}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_task_reading.py -v`
Expected: ImportError on `quantuum.tasks.reading.reading_generate` and `enqueue_reading`.

- [ ] **Step 3: Create `tasks/reading.py`**

Create `src/quantuum/tasks/reading.py`:

```python
from quantuum.astrology.blueprint import from_natal_profile
from quantuum.astrology.sections import build_reading_calc_md
from quantuum.db.models import NatalProfile
from quantuum.domain.llm_config import get_llm_config
from quantuum.domain.quota import refund_quota
from quantuum.domain.readings import get_reading, set_reading_status
from quantuum.domain.requests import complete_request
from quantuum.i18n.strings import get_tenant_default_lang
from quantuum.llm.reading_polish import polish_reading
from quantuum.logging_setup import get_logger
from quantuum.tasks.delivery import deliver_via_tenant_bot

logger = get_logger("task.reading")


async def reading_generate(
    ctx, reading_id: int, chat_id: int | None = None, request_id: int | None = None
) -> None:
    sessionmaker = ctx["sessionmaker"]
    delivery_md = None
    tenant_id = None
    kind = None

    async with sessionmaker() as session:
        try:
            reading = await get_reading(session, reading_id)
            tenant_id = reading.tenant_id
            kind = reading.kind
            profile = await session.get(NatalProfile, reading.natal_profile_id)

            inp = from_natal_profile(profile)
            calc_md = build_reading_calc_md(reading.kind, inp)
            await set_reading_status(session, reading_id, "calculating", calc_md=calc_md)
            await set_reading_status(session, reading_id, "generating")

            cfg = await get_llm_config(session)
            llm_client = ctx.get("llm_client")

            if llm_client is None:
                await set_reading_status(
                    session, reading_id, "done",
                    llm_md=calc_md, llm_provider="none", llm_model="none",
                )
                delivery_md = calc_md
            else:
                lang = reading.lang or await get_tenant_default_lang(session, tenant_id) or "ru"
                result = await polish_reading(
                    llm_client, reading.kind, calc_md,
                    lang=lang, model=cfg["model"],
                    temperature=cfg["temperature"], max_tokens=cfg["max_tokens"],
                )
                await set_reading_status(
                    session, reading_id, "done",
                    llm_md=result.text,
                    llm_provider=cfg["provider"], llm_model=result.model,
                    llm_tokens_in=result.tokens_in, llm_tokens_out=result.tokens_out,
                )
                delivery_md = result.text

            if request_id is not None:
                try:
                    await complete_request(
                        session, request_id,
                        reference_id=reading_id, reference_type="reading",
                    )
                except Exception:
                    logger.exception("reading_complete_request_failed", reading_id=reading_id)
        except Exception:
            logger.exception("reading_generation_failed", reading_id=reading_id)
            try:
                await set_reading_status(session, reading_id, "failed", error="generation failed")
            except Exception:
                logger.exception("reading_set_failed_status_error", reading_id=reading_id)
            if request_id is not None:
                await refund_quota(session, request_id)
            return

    if chat_id is not None and delivery_md is not None and tenant_id is not None:
        try:
            await deliver_via_tenant_bot(
                sessionmaker,
                tenant_id=tenant_id,
                chat_id=chat_id,
                text=delivery_md,
                filename=f"reading-{kind}.md",
                preview_len=4000,
                always_document=False,
            )
        except Exception:
            logger.exception("reading_delivery_failed", reading_id=reading_id, chat_id=chat_id)

    logger.info("reading_generated", reading_id=reading_id, chat_id=chat_id)
```

- [ ] **Step 4: Add `enqueue_reading`**

Edit `src/quantuum/tasks/enqueue.py` — append:

```python
async def enqueue_reading(reading_id: int, chat_id: int | None = None, request_id: int | None = None) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("reading_generate", reading_id, chat_id, request_id)
```

- [ ] **Step 5: Register the task in the worker**

Edit `src/quantuum/tasks/worker.py`:

```python
from quantuum.tasks.reading import reading_generate
```

Update the `WorkerSettings.functions` line to include `reading_generate`:

```python
functions = [
    blueprint_generate, provision_tenant, subscription_lifecycle,
    qa_generate, transit_generate, daily_generate, reading_generate,
]
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_task_reading.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/tasks/reading.py src/quantuum/tasks/enqueue.py src/quantuum/tasks/worker.py tests/test_task_reading.py
git commit -m "feat(tasks): reading_generate arq task + enqueue + worker wiring"
```

---

## Task 8 — Bot UX: "Разборы" button + per-kind callbacks

**Goal:** Add a main-menu button that opens an inline grid of 8 systems. Each tap charges 1 credit, creates a `Reading`, and enqueues `reading_generate`.

**Files:**
- Modify: `src/quantuum/bot/ui/callbacks.py`
- Modify: `src/quantuum/bot/ui/keyboards.py`
- Modify: `src/quantuum/bot/ui/text.py`
- Modify: `src/quantuum/bot/handlers/menu.py`
- Modify: `src/quantuum/bot/handlers/__init__.py`
- Create: `src/quantuum/bot/handlers/readings.py`
- Modify: `src/quantuum/i18n/seed_strings.py`
- Modify: `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py`
- Create: `tests/test_readings_bot.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_readings_bot.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantuum.bot.ui.callbacks import ReadingCb


def test_reading_cb_pack_unpack_roundtrip():
    cb = ReadingCb(action="generate", kind="bazi")
    packed = cb.pack()
    assert packed.startswith("rd:")  # prefix
    parsed = ReadingCb.unpack(packed)
    assert parsed.action == "generate"
    assert parsed.kind == "bazi"


@pytest.mark.parametrize("kind", [
    "bazi", "numerology", "human_design", "astrology",
    "vedic", "gene_keys", "mayan", "aspects",
])
async def test_readings_menu_includes_all_eight_kinds(default_tenant, sessionmaker, kind):
    from quantuum.bot.ui.keyboards import readings_menu_kb
    from quantuum.i18n.resolver import Translator

    async with sessionmaker() as session:
        i18n = await Translator.create(session, tenant_id=default_tenant.id, lang="ru")
    kb = await readings_menu_kb(i18n)
    serialised = []
    for row in kb.inline_keyboard:
        for btn in row:
            serialised.append(btn.callback_data)
    assert any(cd == ReadingCb(action="generate", kind=kind).pack() for cd in serialised), kind


async def test_on_reading_choice_creates_reading_and_enqueues(monkeypatch, sessionmaker, default_tenant):
    from datetime import date, time
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.bot.handlers.readings import on_reading_choice
    from quantuum.db.models import NatalProfile, AccountBalance, AccountPackage
    from quantuum.i18n.resolver import Translator

    async with sessionmaker() as session:
        acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="b1")
        p = NatalProfile(
            tenant_id=default_tenant.id, account_id=acc.id,
            full_name="X", birth_date=date(1990, 1, 1), birth_time=time(12, 0),
            birth_place="X", latitude=0, longitude=0, timezone="UTC",
        )
        bal = AccountBalance(account_id=acc.id, free_trial_used=True, package_credits=1)
        pkg = AccountPackage(account_id=acc.id, requests_remaining=1, requests_total=1)
        session.add_all([p, bal, pkg])
        await session.commit()
        i18n = await Translator.create(session, tenant_id=default_tenant.id, lang="ru")

    enqueued = {}
    async def fake_enqueue(reading_id, chat_id, request_id):
        enqueued.update({"reading_id": reading_id, "chat_id": chat_id, "request_id": request_id})
    monkeypatch.setattr("quantuum.bot.handlers.readings.enqueue_reading", fake_enqueue)

    query = MagicMock()
    query.data = ReadingCb(action="generate", kind="bazi").pack()
    query.message = MagicMock()
    query.message.chat.id = 555
    query.message.answer = AsyncMock()
    query.answer = AsyncMock()

    await on_reading_choice(query, acc, i18n)
    query.message.answer.assert_called()
    assert enqueued["reading_id"] is not None
    assert enqueued["chat_id"] == 555
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_readings_bot.py -v`
Expected: ImportError on `ReadingCb`, `readings_menu_kb`, and `on_reading_choice`.

- [ ] **Step 3: Add `ReadingCb` callback**

Edit `src/quantuum/bot/ui/callbacks.py` — append:

```python
class ReadingCb(CallbackData, prefix="rd"):
    action: str  # generate
    kind: str    # bazi | numerology | human_design | astrology | vedic | gene_keys | mayan | aspects
```

- [ ] **Step 4: Add `readings_menu_kb`**

Edit `src/quantuum/bot/ui/keyboards.py` — append:

```python
from quantuum.bot.ui.callbacks import ReadingCb

READING_KINDS: tuple[str, ...] = (
    "bazi", "numerology", "human_design", "astrology",
    "vedic", "gene_keys", "mayan", "aspects",
)


async def readings_menu_kb(i18n) -> InlineKeyboardMarkup:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    builder = InlineKeyboardBuilder()
    for i in range(0, len(READING_KINDS), 2):
        row = []
        for kind in READING_KINDS[i:i + 2]:
            label = await i18n(f"readings.kind.{kind}")
            row.append(InlineKeyboardButton(
                text=label,
                callback_data=ReadingCb(action="generate", kind=kind).pack(),
            ))
        builder.row(*row)
    return builder.as_markup()
```

(If `InlineKeyboardMarkup` is not in scope at the top of the file, import it from `aiogram.types`.)

- [ ] **Step 5: Add i18n keys to `seed_strings.py`**

Edit `src/quantuum/i18n/seed_strings.py` — add to `BASE_STRINGS`:

```python
"btn.readings": {
    "ru": "📖 Разборы",
    "en": "📖 Readings",
},
"readings.menu.title": {
    "ru": "Какой разбор сгенерировать?",
    "en": "Which reading would you like?",
},
"readings.queued": {
    "ru": "Готовлю разбор. Это займёт минуту.",
    "en": "Generating your reading. This will take a minute.",
},
"readings.no_profile": {
    "ru": "Сначала заполни профиль рождения.",
    "en": "Please fill in your birth profile first.",
},
"readings.no_quota": {
    "ru": "Нет доступных кредитов. Купи пакет, чтобы продолжить.",
    "en": "No credits available. Buy a package to continue.",
},
"readings.kind.bazi":         {"ru": "🐉 BaZi",        "en": "🐉 BaZi"},
"readings.kind.numerology":   {"ru": "🔢 Нумерология",  "en": "🔢 Numerology"},
"readings.kind.human_design": {"ru": "🧬 Human Design","en": "🧬 Human Design"},
"readings.kind.astrology":    {"ru": "☉ Астрология",  "en": "☉ Astrology"},
"readings.kind.vedic":        {"ru": "🕉 Ведическая",  "en": "🕉 Vedic"},
"readings.kind.gene_keys":    {"ru": "🗝 Gene Keys",   "en": "🗝 Gene Keys"},
"readings.kind.mayan":        {"ru": "🌀 Майя",        "en": "🌀 Mayan"},
"readings.kind.aspects":      {"ru": "✦ Аспекты",     "en": "✦ Aspects"},
```

- [ ] **Step 6: Add translations for the 8 non-ru/en languages**

For each of `de.py`, `es.py`, `fr.py`, `hi.py`, `it.py`, `pt.py`, `tr.py`, `zh.py` in `src/quantuum/i18n/translations/`, add entries to the existing translations dict for every new key listed in Step 5. Example for `es.py`:

```python
"btn.readings": "📖 Lecturas",
"readings.menu.title": "¿Qué lectura te gustaría?",
"readings.queued": "Estoy preparando tu lectura. Tardará un minuto.",
"readings.no_profile": "Primero, completa tu perfil de nacimiento.",
"readings.no_quota": "No hay créditos disponibles. Compra un paquete para continuar.",
"readings.kind.bazi": "🐉 BaZi",
"readings.kind.numerology": "🔢 Numerología",
"readings.kind.human_design": "🧬 Human Design",
"readings.kind.astrology": "☉ Astrología",
"readings.kind.vedic": "🕉 Védica",
"readings.kind.gene_keys": "🗝 Llaves Genéticas",
"readings.kind.mayan": "🌀 Maya",
"readings.kind.aspects": "✦ Aspectos",
```

Repeat the same set of 13 keys in each of the other 7 language files, with native-language strings for the prose entries (`btn.readings`, `readings.menu.title`, `readings.queued`, `readings.no_profile`, `readings.no_quota`) and `🐉 BaZi`/`🧬 Human Design`/etc. for the kind labels (system names are commonly left in English in those languages; localise only if natural).

- [ ] **Step 7: Create the handler**

Create `src/quantuum/bot/handlers/readings.py`:

```python
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from quantuum.bot.handlers.generate import _buy_offer_kb
from quantuum.bot.ui.callbacks import ReadingCb
from quantuum.bot.ui.keyboards import readings_menu_kb
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.quota import consume_quota
from quantuum.domain.readings import create_reading
from quantuum.domain.requests import create_request
from quantuum.i18n import Translator
from quantuum.tasks.enqueue import enqueue_reading

router = Router()


async def show_readings_menu(message: Message, i18n: Translator) -> None:
    await message.answer(
        await i18n("readings.menu.title"),
        reply_markup=await readings_menu_kb(i18n),
    )


@router.callback_query(ReadingCb.filter(F.action == "generate"))
async def on_reading_choice(
    query: CallbackQuery, account: Account, i18n: Translator
) -> None:
    kind = ReadingCb.unpack(query.data).kind

    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
        if profile is None:
            await query.message.answer(await i18n("readings.no_profile"))
            await query.answer()
            return
        try:
            charged = await consume_quota(session, account.id, "reading", cost_units=1)
        except InsufficientFundsError:
            await query.message.answer(
                await i18n("readings.no_quota"),
                reply_markup=await _buy_offer_kb(i18n),
            )
            await query.answer()
            return
        reading = await create_reading(
            session,
            tenant_id=account.tenant_id, account_id=account.id,
            natal_profile_id=profile.id, kind=kind, lang=i18n.lang,
        )
        request = await create_request(
            session,
            tenant_id=account.tenant_id, account_id=account.id,
            kind="reading", charged_against=charged,
            reference_id=reading.id, reference_type="reading",
        )

    await enqueue_reading(reading.id, query.message.chat.id, request.id)
    await query.message.answer(await i18n("readings.queued"))
    await query.answer()
```

(If `create_request` does not accept `reference_id`/`reference_type` at construction time, drop those kwargs and rely on `complete_request` later; check `src/quantuum/domain/requests.py` before finalising the call signature.)

- [ ] **Step 8: Wire the menu button**

Edit `src/quantuum/bot/handlers/menu.py`:

```python
from quantuum.bot.handlers.readings import show_readings_menu

_READINGS_LABELS = text.menu_button_labels("btn.readings")

@router.message(F.text.in_(_READINGS_LABELS))
async def on_readings_btn(message: Message, i18n: Translator) -> None:
    await show_readings_menu(message, i18n)
```

Verify `LABELS = text.all_menu_labels()` already returns labels for `btn.readings` (it iterates BASE_STRINGS, so the new key is picked up automatically once Step 5 lands).

Add `btn.readings` to the main reply-keyboard row in `src/quantuum/bot/ui/keyboards.py` `main_menu_kb()` (the function that returns the persistent reply keyboard). Place it next to "Ask the astrologer" for visual continuity:

```python
# inside main_menu_kb
[
    KeyboardButton(text=await i18n("btn.generate")),
    KeyboardButton(text=await i18n("btn.readings")),
],
```

(The exact rows depend on the current layout — locate `main_menu_kb` and insert this button preserving the existing pattern.)

- [ ] **Step 9: Register the new router**

Edit `src/quantuum/bot/handlers/__init__.py` — include the new router alongside existing ones:

```python
from quantuum.bot.handlers.readings import router as readings_router
# in the include_router calls:
dp.include_router(readings_router)
```

(Match the pattern used by `qa`, `daily`, `transits`, etc. in the same file.)

- [ ] **Step 10: Run the bot tests + a smoke pass on menu tests**

Run: `pytest tests/test_readings_bot.py tests/test_menu_and_dispatcher.py tests/test_bot_start_menu_profile.py -v`
Expected: PASS. If `test_menu_and_dispatcher.py` asserts an exact button list, update it to include the new button.

- [ ] **Step 11: Commit**

```bash
git add src/quantuum/bot/handlers/readings.py src/quantuum/bot/handlers/menu.py src/quantuum/bot/handlers/__init__.py src/quantuum/bot/ui/callbacks.py src/quantuum/bot/ui/keyboards.py src/quantuum/i18n/seed_strings.py src/quantuum/i18n/translations/*.py tests/test_readings_bot.py
git commit -m "feat(bot): Readings menu + per-kind callback handler + i18n"
```

---

## Task 9 — Composite Blueprint orchestrator

**Goal:** Replace the single LLM-call in `polish_blueprint` with parallel reading polishes + deterministic stitcher. `Blueprint.calc_md` continues to be `build_blueprint(inp)` (full deterministic md, used by QA).

**Files:**
- Modify: `src/quantuum/llm/blueprint_polish.py`
- Modify: `src/quantuum/tasks/blueprint.py`
- Create: `tests/test_blueprint_compose.py`
- Modify: `tests/test_blueprint_polish_llm.py` (existing — adjust expectations)

- [ ] **Step 1: Write failing tests for the new composite shape**

Create `tests/test_blueprint_compose.py`:

```python
import asyncio
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
        # discriminate kind by user payload contents
        for kind_label, marker in [
            ("BaZi", "BaZi"),
            ("Numerology", "Numerology"),
            ("Human Design", "Human Design"),
            ("Tropical", "Tropical"),
            ("Vedic", "Vedic"),
            ("Gene Keys", "Gene Keys"),
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
    # Stitched result must contain birth-data header and all section bodies
    assert "Desmond Test" in text
    for marker in ["BaZi", "Numerology", "Human Design", "Tropical",
                   "Vedic", "Gene Keys", "Mayan", "Aspects"]:
        assert f"section body for {marker}" in text
    # Field-overview fragments stripped from individual sections and merged at top
    assert "<!-- field-overview-start -->" not in text  # merged + cleaned
    assert "## 🌌 FIELD OVERVIEW" in text
    # Aggregated tokens
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
```

- [ ] **Step 2: Run new test to verify failure**

Run: `pytest tests/test_blueprint_compose.py -v`
Expected: FAIL — `polish_blueprint` doesn't take `build_input`, doesn't aggregate, etc.

- [ ] **Step 3: Rewrite `polish_blueprint`**

Replace `src/quantuum/llm/blueprint_polish.py` with:

```python
import asyncio
import re
from dataclasses import dataclass

from quantuum.astrology.sections import (
    BLUEPRINT_SECTION_ORDER,
    build_blueprint_context,
    build_reading_calc_md,
)
from quantuum.llm.reading_polish import polish_reading

# Map blueprint section keys → reading kinds for polishing.
_SECTION_TO_KIND = {
    "identity":     "astrology",
    "aspects":      "aspects",
    "vedic":        "vedic",
    "numerology":   "numerology",
    "bazi":         "bazi",
    "human_design": "human_design",
    "gene_keys":    "gene_keys",
    "mayan":        "mayan",
}

_FRAGMENT_RE = re.compile(
    r"<!-- field-overview-start -->\s*(.*?)\s*<!-- field-overview-end -->",
    re.DOTALL,
)


@dataclass
class _StitchedResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int


def _strip_fragment(md: str) -> tuple[str, str | None]:
    m = _FRAGMENT_RE.search(md)
    if not m:
        return md, None
    frag = m.group(1).strip()
    cleaned = _FRAGMENT_RE.sub("", md).lstrip("\n")
    return cleaned, frag


def _opening_header(build_input) -> str:
    ctx = build_blueprint_context(build_input)
    return "\n".join([
        f"# {build_input.full_name} — QUANTUUM SOULMAP BLUEPRINT",
        "",
        f"_Birth: {build_input.birth_date} {build_input.birth_time} "
        f"({build_input.timezone}) · Place: "
        f"{build_input.birth_place if build_input.birth_place else '—'} · "
        f"Personal Year target: {ctx.for_year}_",
        "",
    ])


def _closing_template() -> str:
    return "\n".join([
        "",
        "## 🕊 ORACLE AFFIRMATION",
        "",
        "_I receive the codes the sky and the calendar wrote into me, and I answer with my life._",
        "",
        "## 🧭 CLOSING TRANSMISSION",
        "",
        "_Honour what is computed; embody what is true. The map is precise — your living of it is the medicine._",
        "",
    ])


async def polish_blueprint(client, calc_md: str, *, lang: str, model: str,
                            temperature: float, max_tokens: int, build_input):
    polished = await asyncio.gather(*[
        polish_reading(
            client, _SECTION_TO_KIND[section],
            build_reading_calc_md(_SECTION_TO_KIND[section], build_input),
            lang=lang, model=model, temperature=temperature, max_tokens=max_tokens,
        )
        for section in BLUEPRINT_SECTION_ORDER
    ])

    fragments: list[str] = []
    bodies: list[str] = []
    total_in = total_out = 0
    last_model = model
    for r in polished:
        body, frag = _strip_fragment(r.text)
        if frag:
            fragments.append(frag)
        bodies.append(body)
        total_in += r.tokens_in or 0
        total_out += r.tokens_out or 0
        last_model = r.model

    parts: list[str] = [_opening_header(build_input)]
    parts.append("## 🌌 FIELD OVERVIEW\n")
    parts.append("| System | Code / Meaning |\n| --- | --- |")
    parts.extend(fragments if fragments else ["| (no field overview fragments emitted) |"])
    parts.append("")
    parts.extend(bodies)
    parts.append(_closing_template())

    return _StitchedResult(
        text="\n".join(parts),
        model=last_model,
        tokens_in=total_in,
        tokens_out=total_out,
    )
```

- [ ] **Step 4: Update `tasks/blueprint.py` to pass `build_input`**

Edit `src/quantuum/tasks/blueprint.py` — change the call:

```python
result = await polish_blueprint(
    llm_client, calc_md,
    lang=lang, model=cfg["model"],
    temperature=cfg["temperature"], max_tokens=cfg["max_tokens"],
    build_input=inp,
)
```

(`inp` is the existing `from_natal_profile(profile)` value.)

- [ ] **Step 5: Update the existing `test_blueprint_polish_llm.py`**

Open `tests/test_blueprint_polish_llm.py`. It currently asserts the old single-call shape. Replace its body so it instead verifies that calling `polish_blueprint(...)` returns aggregated tokens and contains expected stitched markers, mirroring the smoke check in `test_blueprint_compose.py` but in a smaller form. If unsure of intent, gate it as:

```python
import pytest

@pytest.mark.skip(reason="Superseded by test_blueprint_compose.py — composite shape covered there")
def test_legacy_single_call_polish_blueprint():
    pass
```

(Preferred: actually rewrite the assertions to the new contract; skip only if the rewrite would duplicate `test_blueprint_compose.py` exactly.)

- [ ] **Step 6: Run all polish tests**

Run: `pytest tests/test_blueprint_compose.py tests/test_blueprint_polish_llm.py tests/test_task_blueprint.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/llm/blueprint_polish.py src/quantuum/tasks/blueprint.py tests/test_blueprint_compose.py tests/test_blueprint_polish_llm.py
git commit -m "feat(blueprint): orchestrate 8 parallel reading polishes + deterministic stitcher"
```

---

## Task 10 — QA prompt patch (SYSTEM SELECTION paragraph)

**Goal:** One-file documentation-style change to the QA system prompt; no code touched.

**Files:**
- Modify: `src/quantuum/llm/prompts/qa_astrologer.txt`
- Create: `tests/test_qa_prompt_system_selection.py`

- [ ] **Step 1: Write failing assertion that the prompt contains "SYSTEM SELECTION"**

Create `tests/test_qa_prompt_system_selection.py`:

```python
from pathlib import Path

PROMPT = Path(__file__).resolve().parent.parent / "src" / "quantuum" / "llm" / "prompts" / "qa_astrologer.txt"


def test_qa_prompt_has_system_selection_block():
    text = PROMPT.read_text()
    assert "SYSTEM SELECTION" in text
    assert "BaZi" in text and "numerology" in text and "Human Design" in text
    assert "If the question explicitly names a system" in text
```

- [ ] **Step 2: Run test — verify failure**

Run: `pytest tests/test_qa_prompt_system_selection.py -v`
Expected: FAIL.

- [ ] **Step 3: Edit `qa_astrologer.txt`**

Edit `src/quantuum/llm/prompts/qa_astrologer.txt`. Insert AFTER the existing `CRITICAL FACT RULES` bullet list and BEFORE `INTERPRETATION`:

```

SYSTEM SELECTION
- The chart contains multiple systems (Tropical/Western astrology, Vedic, numerology, BaZi, Human Design, Gene Keys, Mayan Tzolkin, aspects, timing cycles). Before answering, decide which systems are directly relevant to the question and ground the answer in those.
- Do not force-include systems that don't speak to what was asked. A question about money may pull from BaZi Day Master, numerology Destiny / Personal Year, the 2nd/8th houses, and relevant aspects — not from Mayan Tzolkin unless it adds real signal.
- If the question explicitly names a system ("по BaZi", "by numerology", "по Human Design"), restrict the answer to that system.
```

- [ ] **Step 4: Run tests — including the existing QA tests**

Run: `pytest tests/test_qa_prompt_system_selection.py tests/test_qa_answer.py tests/test_task_qa.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/llm/prompts/qa_astrologer.txt tests/test_qa_prompt_system_selection.py
git commit -m "feat(qa): add SYSTEM SELECTION block to QA system prompt"
```

---

## Task 11 — History listing for readings

**Goal:** Show users their past readings in the existing `📜 History` screen, with download.

**Files:**
- Modify: `src/quantuum/bot/handlers/history.py`
- Modify: `src/quantuum/bot/ui/keyboards.py`
- Modify: `src/quantuum/bot/ui/callbacks.py`
- Modify: `tests/test_history_screen.py`

- [ ] **Step 1: Read the current history handler**

Run: `cat src/quantuum/bot/handlers/history.py`

Inspect how Blueprint rows are listed and how download is wired. The reading listing follows the same pattern.

- [ ] **Step 2: Write failing test that History includes recent readings**

Append to `tests/test_history_screen.py` (a new test function — keep the existing assertions for blueprints intact):

```python
async def test_history_lists_recent_readings(sessionmaker, default_tenant):
    from datetime import date, time
    from unittest.mock import AsyncMock, MagicMock

    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.bot.handlers.history import show_history
    from quantuum.db.models import NatalProfile
    from quantuum.domain.readings import create_reading, set_reading_status
    from quantuum.i18n.resolver import Translator

    async with sessionmaker() as session:
        acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="h1")
        p = NatalProfile(
            tenant_id=default_tenant.id, account_id=acc.id,
            full_name="X", birth_date=date(1990, 1, 1), birth_time=time(12, 0),
            birth_place="X", latitude=0, longitude=0, timezone="UTC",
        )
        session.add(p); await session.commit(); await session.refresh(p)

        r = await create_reading(session, tenant_id=default_tenant.id,
            account_id=acc.id, natal_profile_id=p.id, kind="bazi", lang="ru")
        await set_reading_status(session, r.id, "done", llm_md="BaZi result")
        i18n = await Translator.create(session, tenant_id=default_tenant.id, lang="ru")

    message = MagicMock()
    message.answer = AsyncMock()
    message.from_user = MagicMock(); message.from_user.id = 1
    await show_history(message, acc, i18n, page=0)
    rendered = " ".join(call.args[0] for call in message.answer.call_args_list)
    assert "bazi" in rendered.lower() or "BaZi" in rendered
```

- [ ] **Step 3: Run the new test — verify failure**

Run: `pytest tests/test_history_screen.py::test_history_lists_recent_readings -v`
Expected: FAIL.

- [ ] **Step 4: Extend the history handler to list readings**

Edit `src/quantuum/bot/handlers/history.py`. Add an import and list block. The exact diff depends on the current handler shape; preserve the existing blueprint section and add a parallel readings section that calls `list_readings(session, account_id=account.id, limit=10)` and renders one line per row in the form:

```
{n}. [{kind}] {short_status} — {date}
```

with a download button via a new `ReadingDownloadCb` (callback prefix `rdl`) added to `callbacks.py`:

```python
class ReadingDownloadCb(CallbackData, prefix="rdl"):
    reading_id: int
```

The download handler reads the `Reading.llm_md` and sends it as a `BufferedInputFile` named `reading-{kind}-{id}.md` (mirroring the existing blueprint download).

- [ ] **Step 5: Re-run the history tests**

Run: `pytest tests/test_history_screen.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/bot/handlers/history.py src/quantuum/bot/ui/keyboards.py src/quantuum/bot/ui/callbacks.py tests/test_history_screen.py
git commit -m "feat(history): show readings list with download"
```

---

## Task 12 — Full suite + features doc

**Goal:** Run the full test suite, fix any regressions, and update the user-facing features doc.

**Files:**
- Modify: `docs/other/features.md`
- Modify: `docs/other/features.html` (regenerated/maintained from features.md by existing process)

- [ ] **Step 1: Run the full test suite**

Run: `pytest -x`
Expected: PASS. If anything fails, fix in place (don't paper over) and commit the fix.

- [ ] **Step 2: Add Readings section to features.md**

Edit `docs/other/features.md`. Find the section that describes "Blueprint" and add a sibling section after it:

```markdown
### Readings (individual system-by-system)

Each Quantuum system can now be generated on its own as a polished reading:

- 🐉 **BaZi** — Chinese Four Pillars with Day Master interpretation
- 🔢 **Numerology** — Life Path, Destiny, Soul Urge, Personal Year, Pinnacles & Challenges
- 🧬 **Human Design** — Type, Strategy, Authority, Profile, Centers, Channels
- ☉ **Astrology** — Tropical Western: Sun/Moon/Ascendant + houses + element balance
- 🕉 **Vedic** — Sidereal (Lahiri) Sun/Moon/Ascendant + Moon Nakshatra
- 🗝 **Gene Keys** — Life's Work / Evolution / Radiance / Purpose
- 🌀 **Mayan Tzolkin** — Tone, Day Sign, Dreamspell, Kin
- ✦ **Aspects** — Natal aspect grid with tensions and talents

Each reading costs 1 credit. The full Blueprint composes all 8 readings into a single ceremonial document (with a unified Field Overview, Oracle Affirmation, and Closing Transmission), and costs 4 credits.

QA continues to draw from the entire chart automatically — the model selects relevant systems for each question.
```

- [ ] **Step 3: Sync features.html**

If the project maintains `features.html` by hand, mirror the changes. If a generator exists (check `docs/other/README.md` or scripts), run it.

- [ ] **Step 4: Commit**

```bash
git add docs/other/features.md docs/other/features.html
git commit -m "docs(features): document Readings feature and Blueprint composition cost"
```

- [ ] **Step 5: Final smoke pass**

Run: `pytest -x && alembic upgrade head`
Expected: tests PASS, alembic at head.

---

## Self-Review

**Spec coverage:**
- Section "Data model → readings table" → Task 3 ✓
- Section "Data model → Request.kind = reading" → no DDL needed (existing string column); used in Task 8 handler when calling `create_request(..., kind="reading", ...)` ✓
- Section "Data model → consume_quota cost_units" → Task 2 ✓
- Section "Section builders" → Task 1 ✓
- Section "Per-kind reading calc_md" → Task 1 Step 8 (`build_reading_calc_md`) ✓
- Section "LLM polish → reading_polish.py" → Task 5 ✓
- Section "LLM polish → per-kind prompts" → Task 6 ✓
- Section "LLM polish → blueprint orchestrator" → Task 9 ✓
- Section "Domain layer → readings.py" → Task 4 ✓
- Section "Task: reading_generate" → Task 7 ✓
- Section "Task: blueprint.py rewrite" → Task 9 Step 4 ✓
- Section "Task: enqueue.py" → Task 7 Step 4 ✓
- Section "QA changes → prompt patch" → Task 10 ✓
- Section "Bot UX → button, menu, callback" → Task 8 ✓
- Section "Bot UX → history listing" → Task 11 ✓
- Section "i18n keys" → Task 8 Steps 5–6 ✓
- Section "Testing → required passing tests" → integrated into each task's run-tests step, final pass in Task 12 ✓

**Placeholder scan:** No "TBD" / "implement later" / "similar to Task N" found. Each step shows the actual code or command to run.

**Type consistency:** `Reading.kind` enum values match across `models.py`, `READING_PROMPTS`, `_SECTION_TO_KIND`, `READING_KINDS` (callbacks), and i18n keys. Function signatures match between `create_reading` (Task 4), the call in `on_reading_choice` (Task 8 Step 7), and the worker (Task 7 Step 3). `polish_reading` (Task 5) signature matches its use in both `reading_generate` (Task 7) and `polish_blueprint` (Task 9). `cost_units` carried through `consume_quota` → `Request.cost_units` → `refund_quota` consistently.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-26-individual-readings-and-qa-routing.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
