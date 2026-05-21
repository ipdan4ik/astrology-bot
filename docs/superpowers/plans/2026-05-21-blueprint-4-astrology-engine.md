# Plan 4 — Real Astrology Engine + LLM Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mock blueprint with a faithful Python port of the TypeScript astrology engine that produces **character-exact** `calc_md`, plus an `LLMClient` abstraction (Anthropic default) that polishes `calc_md → llm_md`, wired into the existing `blueprint_generate` arq task.

**Architecture:** A new `quantuum/astrology/` package mirrors the 8 TS source modules in `/home/ipu/code/work/astrology/src/`. Correctness is anchored by golden-master tests: the TS reference engine regenerates `calc_md` for all 4 example fixtures, and the Python port must reproduce each byte-for-byte. A new `quantuum/llm/` package adds an `LLMClient` Protocol with a default `AnthropicClient` and the verbatim writer prompt. `blueprint_generate` is rewired: `build_blueprint(input) → calc_md`, then `llm_client.complete(...) → llm_md`. The mock is deleted.

**Tech Stack:** Python 3.12, `astronomy-engine` (geocentric ephemeris, Don Cross — same author as the JS lib), `lunar-python` (BaZi, 6tail — same author as `lunar-typescript`), `tzdata` (IANA tz DB in containers), `anthropic` (LLM SDK), stdlib `zoneinfo`, pytest. Existing: SQLModel, arq, aiogram.

**Source of truth for the port:** `/home/ipu/code/work/astrology/src/*.ts`. Each port task translates one named TS file; the TS file IS the spec. Implementers MUST read the named TS file and reproduce its behavior exactly — not approximate it.

---

## CRITICAL: JS → Python parity hazards (read before any task)

These differences will silently break character-exact output if missed. Every implementer must internalize them.

1. **`Math.round` (JS) rounds half UP toward +∞**: `Math.round(0.5)=1`, `Math.round(2.5)=3`, `Math.round(-0.5)=0`. Python `round()` is banker's rounding. **Always use `js_round(x) = math.floor(x + 0.5)`** wherever the TS uses `Math.round`. Used in `toSignDegree` seconds. Note the TS does **not** normalize seconds==60 — keep it as `60` if it rounds there.

2. **`Number.prototype.toFixed(n)` (JS)**: operates on the IEEE-754 double and rounds half-away-from-zero in most cases, but with float artifacts. Python `f"{x:.{n}f}"` uses round-half-to-even. For the irrational astronomy values in these fixtures they nearly always agree, but **use a dedicated `to_fixed(x, n)` helper** that mirrors JS semantics so any divergence is fixed in one place. JS `toFixed` on a negative-zero or tiny value: match `f"{x:.{n}f}"` first, and only special-case if the golden test reveals a mismatch. Used for orb (`.toFixed(2)`), HD longitude (`.toFixed(2)`), lat/lon (`.toFixed(4)`).

3. **`Date.toISOString()` (JS)** always emits exactly `YYYY-MM-DDTHH:mm:ss.sssZ` (3-digit milliseconds, literal `Z`). Python `datetime.isoformat()` differs. **Use a `to_iso_z(ms: int)` helper** that formats from integer epoch-milliseconds. Used for `**UTC instant:**` and the HD `Design moment` row.

4. **`new Date(float)` truncates the float to integer ms toward zero** (ECMAScript ToInteger). The HD design-date Newton iteration does `new Date(t.getTime() + dDays * 86400000)`. **Carry instants as integer epoch-milliseconds** (mirror of `Date.getTime()`) and apply `int(...)` (Python `int()` truncates toward zero) at each step. Do NOT use float seconds round-trips.

5. **IANA timezones**: TS uses `date-fns-tz` `fromZonedTime(stamp, tz)` which uses the IANA tz database. Python `zoneinfo.ZoneInfo(tz)` uses the same database — results match including historical rules (e.g. Moscow June 1980 = UTC+3, no DST). The `tzdata` pip package guarantees the DB is present inside containers. Offset strings like `"+03:00"` are handled separately (see `parse_birth_instant`).

6. **`%` operator**: JS `%` is truncated (sign of dividend); Python `%` is floored (sign of divisor). They agree for non-negative operands. `norm360`/`normRad` already produce equivalent results in both languages because of the `if v < 0: v += 360` guard. In `mayan.py` the offsets are large positive (births after 3114 BCE), so `%` agrees — but reproduce the TS expressions verbatim and verify against the golden.

7. **Integer formatting in tables**: the TS `table()` does `r.map(String)`. Python must render ints as plain `str(int)` (no `.0`). Keep table cell values as `int` or `str`, never `float`, except where a `.toFixed`/`to_fixed` string is intended.

8. **No trailing newline**: `buildBlueprint` returns `lines.join("\n")` and the CLI writes it verbatim. Golden fixture files therefore have **no trailing newline**. Compare `build_blueprint(...) == golden_path.read_text()` exactly.

---

## File Structure

Created:
- `src/quantuum/astrology/__init__.py` — package marker
- `src/quantuum/astrology/util.py` ← `util.ts` (constants, formatters, JS-parity helpers)
- `src/quantuum/astrology/numerology.py` ← `numerology.ts`
- `src/quantuum/astrology/astro.py` ← `astro.ts`
- `src/quantuum/astrology/chinese.py` ← `chinese.ts`
- `src/quantuum/astrology/mayan.py` ← `mayan.ts`
- `src/quantuum/astrology/human_design.py` ← `humandesign.ts`
- `src/quantuum/astrology/gene_keys.py` ← `genekeys.ts`
- `src/quantuum/astrology/blueprint.py` ← `blueprint.ts` (orchestration → `calc_md`)
- `src/quantuum/llm/__init__.py`
- `src/quantuum/llm/base.py` — `LLMClient` Protocol, `LLMResult` dataclass, `LLMError`
- `src/quantuum/llm/anthropic_client.py` — `AnthropicClient`
- `src/quantuum/llm/registry.py` — provider selection
- `src/quantuum/llm/blueprint_polish.py` — `polish_blueprint(client, calc_md, ...) -> LLMResult`
- `src/quantuum/llm/prompts/blueprint_writer.txt` — verbatim copy of `astrology/prompt.txt`
- `tests/fixtures/calc/{anna,nikita,regina,victoria}.json` — copies of the 4 inputs
- `tests/fixtures/calc/{anna,nikita,regina,victoria}.calc.md` — golden `calc_md` from the TS engine
- Test files per task (see below)

Modified:
- `pyproject.toml` — add deps
- `src/quantuum/settings.py` — LLM settings
- `src/quantuum/tasks/blueprint.py` — rewire to real engine + LLM
- `src/quantuum/tasks/worker.py` — `ctx["llm_client"]`
- `.env.example`, `compose/.env.example` (if present) — LLM_* keys

Deleted:
- `src/quantuum/domain/mock_blueprint.py`
- mock-specific test assertions in `tests/test_blueprints_service.py`, `tests/test_task_blueprint.py`

---

## Phase 0 — Foundations

### Task 0: Add dependencies

**Files:**
- Modify: `pyproject.toml` (the `dependencies` array)
- Test: `tests/test_astrology_deps.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_astrology_deps.py
def test_engine_libraries_importable():
    import astronomy_engine  # noqa: F401
    import lunar_python  # noqa: F401
    import anthropic  # noqa: F401
```

Note the import names: the PyPI package `astronomy-engine` imports as `astronomy_engine`? **Verify the actual import name during Step 3** — the cosinekitty package imports as `astronomy` (module `astronomy`), not `astronomy_engine`. Adjust the test to the real import name once installed (`import astronomy`). `lunar-python` imports as `lunar_python`. `anthropic` imports as `anthropic`.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_astrology_deps.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Add dependencies and sync**

Add to `pyproject.toml` `dependencies`:
```toml
    "astronomy-engine>=2.1.19",
    "lunar-python>=1.4.4",
    "tzdata>=2024.1",
    "anthropic>=0.40",
```

Then: `uv sync`

Discover the real import name: `uv run python -c "import astronomy; print(astronomy.__name__)"`. Update the test import accordingly (`import astronomy` rather than `import astronomy_engine`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_astrology_deps.py -v` → PASS
Then: `uv run ruff check .`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/test_astrology_deps.py
git commit -m "chore(4): add astronomy-engine, lunar-python, tzdata, anthropic deps"
```

---

### Task 1: Generate golden `calc_md` references from the TS engine

This task produces the immutable golden fixtures. No TDD — it is fixture generation. The golden MUST come from the TS reference, never from the Python port (that would be circular).

**Files:**
- Create: `tests/fixtures/calc/{anna,nikita,regina,victoria}.json`
- Create: `tests/fixtures/calc/{anna,nikita,regina,victoria}.calc.md`

- [ ] **Step 1: Install TS deps and regenerate each golden**

```bash
cd /home/ipu/code/work/astrology
bun install
for name in anna nikita regina victoria; do
  bun index.ts examples/$name.json --out /tmp/$name.calc.md
done
```

`bun index.ts` runs the CLI (`runBlueprintCli`) which writes `buildBlueprint(input)` verbatim (no trailing newline). Confirm each ran: it prints `✓ blueprint written → ... (N chars)`.

- [ ] **Step 2: Copy inputs + goldens into the test tree**

```bash
cd /home/ipu/code/work/quantuum-bot
mkdir -p tests/fixtures/calc
for name in anna nikita regina victoria; do
  cp /home/ipu/code/work/astrology/examples/$name.json tests/fixtures/calc/$name.json
  cp /tmp/$name.calc.md tests/fixtures/calc/$name.calc.md
done
```

- [ ] **Step 3: Sanity-check the goldens**

```bash
head -8 tests/fixtures/calc/anna.calc.md
wc -c tests/fixtures/calc/*.calc.md
# Confirm anna starts with "# Quantuum Blueprint — Anna Belyeva" and contains
# "**UTC instant:** 1980-06-24T07:00:00.000Z" (Europe/Moscow June 1980 = UTC+3).
# Confirm NO trailing newline:
tail -c 40 tests/fixtures/calc/anna.calc.md | xxd | tail -2
```

The last byte must NOT be `0a` (newline) — `buildBlueprint` does not emit a trailing newline.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/calc/
git commit -m "test(4): golden calc_md fixtures from TS reference engine (4 charts)"
```

---

## Phase A — Calculator port (character-exact)

### Task 2: `util.py` — constants, sign/degree, JS-parity helpers

**Files:**
- Create: `src/quantuum/astrology/__init__.py` (empty)
- Create: `src/quantuum/astrology/util.py`
- Test: `tests/test_astrology_util.py`

Port from `/home/ipu/code/work/astrology/src/util.ts`. Reproduce: `TWO_PI`, `DEG`, `RAD`, `norm360`, `norm_rad`, `SIGN_NAMES`, `SIGN_GLYPH`, `ELEMENTS`, `MODALITIES`, `SignDegree` (use a frozen dataclass with fields `longitude, sign, degree, minute, second`), `to_sign_degree`, `fmt_deg`, `reduce_numerology`. Add the JS-parity helpers: `js_round`, `to_fixed`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_astrology_util.py
import math
from quantuum.astrology.util import (
    norm360, to_sign_degree, fmt_deg, reduce_numerology, js_round, to_fixed,
    ELEMENTS, MODALITIES,
)


def test_norm360_wraps_negatives():
    assert norm360(-5) == 355
    assert norm360(365) == 5
    assert norm360(0) == 0


def test_js_round_is_half_up():
    assert js_round(0.5) == 1
    assert js_round(2.5) == 3
    assert js_round(-0.5) == 0
    assert js_round(1.4999) == 1


def test_to_fixed_matches_js():
    assert to_fixed(55.7558, 4) == "55.7558"
    assert to_fixed(2.0, 2) == "2.00"
    assert to_fixed(0.123, 2) == "0.12"


def test_to_sign_degree_anna_sun():
    # Anna's Sun longitude ≈ 92.91°  → ♋ Cancer 02°54'36"
    sd = to_sign_degree(92.91)
    assert sd.sign == "Cancer"
    assert sd.degree == 2
    # fmt_deg renders glyph + sign + DD°MM'SS"
    assert fmt_deg(to_sign_degree(92.91)).startswith("♋ Cancer 02°")


def test_reduce_numerology_keeps_master():
    assert reduce_numerology(29) == 11   # 2+9=11 kept
    assert reduce_numerology(38) == 11   # 3+8=11 kept
    assert reduce_numerology(39) == 3    # 3+9=12 → 3
    assert reduce_numerology(11, keep_master=False) == 2


def test_element_modality_tables_complete():
    assert ELEMENTS["Aries"] == "Fire"
    assert MODALITIES["Cancer"] == "Cardinal"
    assert len(ELEMENTS) == 12 and len(MODALITIES) == 12
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_astrology_util.py -v` → FAIL (module not found).

- [ ] **Step 3: Implement `util.py`**

Translate `util.ts` faithfully. Key details:
- `to_sign_degree`: `sign_index = floor(lon/30)`, `degree = floor(in_sign)`, `minute = floor(min_total)`, `second = js_round((min_total - minute) * 60)` — **use `js_round`, not `round`**. Do not normalize `second == 60`.
- `fmt_deg`: `f"{SIGN_GLYPH[sd.sign]} {sd.sign} {sd.degree:02d}°{sd.minute:02d}'{sd.second:02d}\""`.
- `js_round`: `math.floor(x + 0.5)`.
- `to_fixed(x, n)`: return `f"{x:.{n}f}"` (revisit only if a golden test later reveals a mismatch).
- `reduce_numerology(n, keep_master=True)`: exact port of the `while n > 9` loop preserving 11/22/33.
- `SignDegree`: frozen dataclass; `Position` (in astro.py) will extend it with `retrograde`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_astrology_util.py -v` → PASS. Then `uv run ruff check .`.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/astrology/__init__.py src/quantuum/astrology/util.py tests/test_astrology_util.py
git commit -m "feat(4): astrology util — sign/degree, JS-parity js_round/to_fixed"
```

---

### Task 3: `numerology.py`

**Files:**
- Create: `src/quantuum/astrology/numerology.py`
- Test: `tests/test_astrology_numerology.py`

Port from `numerology.ts`. Reproduce: `PYTHAGOREAN` map, `VOWELS`, `letters_only` (uppercase → NFD → strip combining marks → keep A–Z), `letter_value`, `is_vowel` (Y-as-vowel rule: Y is a vowel only when the previous letter exists and is a consonant), `name_sum` (modes `all|vowels|consonants` — reproduce the exact `include` boolean), `reduce_digits`, `calculate_numerology`. Return a `Numerology` dataclass with the same fields, including `challenges` and `pinnacles` (nested dataclasses or dicts with `c1..c4` / `p1..p4`).

Diacritic stripping: TS uses `.normalize("NFD").replace(/[̀-ͯ]/g, "")`. Python: `unicodedata.normalize("NFD", s)` then drop chars in U+0300–U+036F (or `unicodedata.combining(ch)`), then keep `[A-Z]` after uppercasing.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_astrology_numerology.py
from quantuum.astrology.numerology import calculate_numerology


def test_anna_numerology_matches_golden_cells():
    # Anna Belyeva, 1980-06-24, forYear 2025.
    n = calculate_numerology("Anna Belyeva", 1980, 6, 24, 2025)
    assert n.personal_year_target == 2025
    # Cross-checked against tests/fixtures/calc/anna.calc.md section 4:
    # Life Path, Birth Day, Destiny, Soul Urge, Personality, Maturity,
    # Attitude, Personal Year. Fill these in from the golden table.
    assert isinstance(n.life_path, int)
    assert isinstance(n.personal_year, int)
    # Pinnacles & challenges present
    assert set(vars(n.pinnacles)) >= {"p1", "p2", "p3", "p4"}
    assert set(vars(n.challenges)) >= {"c1", "c2", "c3", "c4"}
```

Then strengthen the test by reading the exact numerology values from `tests/fixtures/calc/anna.calc.md` (the "## 4. Numerology" table) and asserting each cell equals `calculate_numerology(...)`. Use the golden file's actual numbers.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_astrology_numerology.py -v` → FAIL.

- [ ] **Step 3: Implement `numerology.py`** — faithful port; master numbers preserved via `reduce_numerology` from `util.py`.

- [ ] **Step 4: Run test to verify it passes** → PASS. Then `uv run ruff check .`.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/astrology/numerology.py tests/test_astrology_numerology.py
git commit -m "feat(4): numerology port (Pythagorean, master numbers, pinnacles/challenges)"
```

---

### Task 4: `astro.py` — positions, houses, aspects, sidereal (HIGHEST RISK)

**Files:**
- Create: `src/quantuum/astrology/astro.py`
- Test: `tests/test_astrology_astro.py`

Port from `astro.ts`. This is the riskiest task — it depends on `astronomy-engine` producing the same longitudes as the JS lib.

**Astronomy-engine Python API mapping** (verify exact names against the installed package; the cosinekitty Python port uses these):
- Time: build from a tz-aware UTC `datetime` → `astronomy.Time(dt)`; or from epoch-ms via the `_to_astro_time(ms)` helper below.
- Sun: `astronomy.SunPosition(time)` → has ecliptic longitude of date (`.elon`). Match the JS `Astronomy.SunPosition(date).elon`.
- Moon: `astronomy.EclipticGeoMoon(time)` → `.lon`.
- Planets: `astronomy.GeoVector(body, time, aberration=True)` → `astronomy.Ecliptic(vector)` → `.elon`. `body` from `astronomy.Body.Mercury` etc.
- Sidereal time: `astronomy.SiderealTime(time)` → hours.

**Instant handling**: every astro function takes a tz-aware UTC `datetime`. Internally compute `_epoch_ms(dt) = (dt - EPOCH) // timedelta(milliseconds=1)` where `EPOCH = datetime(1970,1,1,tzinfo=timezone.utc)` (lossless integer ms). Constants `Date.UTC(2000,0,1,12,0,0)` and `Date.UTC(1900,0,0,12,0,0)` → reproduce as integer ms literals (compute once). For `Date.UTC(1900,0,0,...)` note JS month 0 = January and **day 0** = Dec 31 1899; reproduce that exact instant.

Reproduce verbatim: `ecliptic_longitude`, `planet_position` (retrograde via +6h sample), `mean_lunar_node_longitude`, `lunar_nodes`, `local_sidereal_time_deg`, `mean_obliquity_deg`, `ascendant_longitude`, `midheaven_longitude`, `whole_sign_houses`, `placidus_cusps`/`porphyry_cusps`, `house_of`, `ASPECTS`, `find_aspect`, `lahiri_ayanamsha_deg`, `sidereal_longitude`, `NAKSHATRAS`, `nakshatra`. `Position` extends `SignDegree` with `retrograde: bool`.

Iterate dict order matters for `find_aspect`: Python dicts preserve insertion order, so define `ASPECTS` in the same order as the TS object (Conjunction, Opposition, Trine, Square, Sextile, Quincunx, Semisquare, Sesquisquare). The "first wins on ties" logic (`!best || orb < best.orb`) is order-sensitive — match exactly.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_astrology_astro.py
from datetime import datetime, timezone
from quantuum.astrology.astro import planet_position, ascendant_longitude, midheaven_longitude
from quantuum.astrology.util import fmt_deg, to_sign_degree


# Anna: 1980-06-24 10:00 Europe/Moscow = 1980-06-24T07:00:00Z
ANNA = datetime(1980, 6, 24, 7, 0, 0, tzinfo=timezone.utc)
ANNA_LAT, ANNA_LON = 55.7558, 37.6173


def test_anna_sun_position():
    p = planet_position("Sun", ANNA)
    # golden: ♋ Cancer 02°54'36"
    assert fmt_deg(p) == "♋ Cancer 02°54'36\""
    assert p.retrograde is False


def test_anna_venus_retrograde():
    p = planet_position("Venus", ANNA)
    # golden: ♊ Gemini 19°10'08" ℞
    assert fmt_deg(p) == "♊ Gemini 19°10'08\""
    assert p.retrograde is True


def test_anna_ascendant_and_mc():
    asc = ascendant_longitude(ANNA, ANNA_LAT, ANNA_LON)
    mc = midheaven_longitude(ANNA, ANNA_LON)
    assert fmt_deg(to_sign_degree(asc)) == "♍ Virgo 06°53'56\""
    assert fmt_deg(to_sign_degree(mc)) == "♉ Taurus 27°28'49\""
```

Values are taken directly from `tests/fixtures/calc/anna.calc.md`. Add a couple more planets (Moon ♏ 14°27'08", Pluto ℞) for coverage.

- [ ] **Step 2: Run it to verify it fails** → FAIL.

- [ ] **Step 3: Implement `astro.py`.** Faithful port. If any assertion is off by 1 arcsecond, it is almost certainly a `js_round` vs `round` or a Time-construction issue — fix the helper, not the test. **If a value diverges by more than rounding (i.e. the underlying ephemeris longitude differs materially from JS), STOP and report it — do not weaken the assertion.**

- [ ] **Step 4: Run test to verify it passes** → PASS. Then `uv run ruff check .`.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/astrology/astro.py tests/test_astrology_astro.py
git commit -m "feat(4): astro port — positions, houses (whole sign/porphyry), aspects, sidereal"
```

---

### Task 5: `chinese.py` — BaZi Four Pillars

**Files:**
- Create: `src/quantuum/astrology/chinese.py`
- Test: `tests/test_astrology_chinese.py`

Port from `chinese.ts` using `lunar-python` (mirror of `lunar-typescript`). The JS does `Solar.fromYmdHms(y,m,d,h,mi,s).getLunar().getBaZi()` → `[year, month, day, hour]` GanZhi strings. In `lunar-python`: `from lunar_python import Solar` then `Solar.fromYmdHms(...).getLunar().getBaZi()`. Verify the method names against the installed package (lunar-python mirrors the TS API; methods are `getLunar`, `getBaZi`). Reproduce `STEMS`, `BRANCHES`, `ChinesePillar` (dataclass), `pillar_from_gan_zhi`, `chinese_pillars_from_local`, `pillar_summary`.

The pillar input is the **local civil** date/time (NOT the UTC instant): `chinese_pillars_from_local(yyyy, mm, dd, birth_hour, birth_minute)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_astrology_chinese.py
from quantuum.astrology.chinese import chinese_pillars_from_local, pillar_summary


def test_anna_four_pillars_match_golden():
    # Anna local civil: 1980-06-24 10:00
    bazi = chinese_pillars_from_local(1980, 6, 24, 10, 0)
    # Cross-check against anna.calc.md "## 5. Chinese Zodiac" table:
    # each pillar's full / chinese / element / animal / polarity.
    assert "/" in f"{bazi.year.full} / {bazi.year.chinese}"
    # Fill exact stem-branch values from the golden table, e.g.:
    # assert bazi.day.full == "..."  ; assert bazi.day.chinese == "..."
    assert pillar_summary(bazi.day).startswith(bazi.day.polarity)
```

Strengthen by reading anna's exact pillar strings from the golden and asserting each field equals the computed pillar.

- [ ] **Step 2: Run it to verify it fails** → FAIL.

- [ ] **Step 3: Implement `chinese.py`** — faithful port via lunar-python.

- [ ] **Step 4: Run test to verify it passes** → PASS. Then `uv run ruff check .`.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/astrology/chinese.py tests/test_astrology_chinese.py
git commit -m "feat(4): chinese BaZi port via lunar-python (four pillars)"
```

---

### Task 6: `mayan.py` — Tzolkin

**Files:**
- Create: `src/quantuum/astrology/mayan.py`
- Test: `tests/test_astrology_mayan.py`

Port from `mayan.ts`. Reproduce `TZOLKIN_SIGNS`, `DREAMSPELL_SIGNS`, `julian_day_number` (UTC y/m/d via Fliegel–Van Flandern), `Tzolkin` dataclass, `tzolkin(date)`. Take a tz-aware UTC `datetime`; use `dt.year/.month/.day` in UTC (the TS uses `getUTCFullYear/Month/Date`). Reproduce the modulo expressions verbatim (operands are positive for these dates, so JS/Python `%` agree).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_astrology_mayan.py
from datetime import datetime, timezone
from quantuum.astrology.mayan import tzolkin

ANNA = datetime(1980, 6, 24, 7, 0, 0, tzinfo=timezone.utc)


def test_anna_tzolkin_matches_golden():
    tz = tzolkin(ANNA)
    # Cross-check against anna.calc.md "## 8. Mayan Tzolkin":
    # Tone (Trecena), Day Sign (Maya), Dreamspell, Full Name, Kin.
    assert 1 <= tz.trecena <= 13
    assert 1 <= tz.kin <= 260
    assert tz.full == f"{tz.trecena} {tz.sign_name}"
    # Fill exact values from golden, e.g. assert tz.kin == ...
```

Strengthen with the exact golden kin/tone/sign.

- [ ] **Step 2–4:** fail → implement → pass + ruff.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/astrology/mayan.py tests/test_astrology_mayan.py
git commit -m "feat(4): mayan tzolkin port (GMT correlation + dreamspell)"
```

---

### Task 7: `human_design.py` — gates, design date, type/authority (COMPLEX)

**Files:**
- Create: `src/quantuum/astrology/human_design.py`
- Test: `tests/test_astrology_human_design.py`

Port from `humandesign.ts`. Reproduce everything: `GATE_ORDER`, gate/line/color/tone/base sizing, `GateActivation`, `longitude_to_gate`, `find_sun_longitude_time`, `HD_BODIES`, `body_longitude`, `CenterName`, `GATES_BY_CENTER`, `GATE_TO_CENTER`, `CHANNELS`, `MOTORS`, `HdType`/`HdAuthority`, `center_links`, `path_exists` (BFS), `determine_type`, `determine_authority`, `determine_strategy`, `determine_signature`, `determine_not_self`, `determine_definition` (connected components), `classify_incarnation_cross`, `HdActivation`, `HumanDesignChart`, `activations_for`, `calculate_human_design`.

**Design-date precision (critical):** `find_sun_longitude_time` does Newton iteration with `new Date(t.getTime() + dDays*86400000)`. Implement with **integer epoch-ms**:
```
t_ms = birth_ms - 89*86400000
for _ in range(30):
    lon = ecliptic_longitude("Sun", _from_ms(t_ms))
    diff = ((target - lon + 540) % 360) - 180
    if abs(diff) < 1e-7: break
    d_days = diff / 0.9856
    t_ms = int(t_ms + d_days * 86400000)   # int() truncates toward zero (JS new Date(float))
return t_ms   # keep as int ms; convert to datetime/iso only at the boundary
```
where `_from_ms(ms) = EPOCH + timedelta(milliseconds=ms)`. The chart's `design_date` should be retained as integer ms (or a datetime built from it) so `blueprint.py` can render it via `to_iso_z(ms)` exactly like JS `designDate.toISOString()`.

`calculate_human_design(birth)` takes the birth `datetime`; compute `birth_ms` once. `body_longitude` for `Earth`/`NorthNode`/`SouthNode` per the TS switch.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_astrology_human_design.py
from datetime import datetime, timezone
from quantuum.astrology.human_design import calculate_human_design

ANNA = datetime(1980, 6, 24, 7, 0, 0, tzinfo=timezone.utc)


def test_anna_hd_summary_matches_golden():
    hd = calculate_human_design(ANNA)
    # Cross-check against anna.calc.md "## 6. Human Design" table.
    assert hd.type in {
        "Manifestor", "Generator", "Manifesting Generator", "Projector", "Reflector"
    }
    assert "/" in hd.profile  # e.g. "4/6"
    # Fill exact golden values: type, strategy, authority, profile, definition.kind,
    # active gates list, incarnation cross name, and the design-date ISO string.
    # Personality[0] is the Sun, [1] is the Earth.
    assert hd.personality[0].body == "Sun"
    assert hd.personality[1].body == "Earth"


def test_anna_design_date_iso_matches_golden():
    from quantuum.astrology.blueprint import to_iso_z  # defined in Task 9
    hd = calculate_human_design(ANNA)
    # The golden "Design moment (88° solar arc back)" cell is an exact ISO-Z string.
    iso = to_iso_z(hd.design_ms)  # design_ms = integer epoch-ms of designDate
    assert iso.endswith("Z") and "T" in iso
    # assert iso == "<exact value from anna.calc.md>"
```

If `to_iso_z` does not yet exist (Task 9), inline a temporary local copy in this test, then switch to the shared helper after Task 9. Pull the exact golden ISO string and all HD fields from `anna.calc.md`.

- [ ] **Step 2: Run it to verify it fails** → FAIL.

- [ ] **Step 3: Implement `human_design.py`.** Faithful port with integer-ms iteration. If the design-date ISO is off, the culprit is float ms handling — fix the iteration to integer ms, do not weaken the test.

- [ ] **Step 4: Run test to verify it passes** → PASS. Then `uv run ruff check .`.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/astrology/human_design.py tests/test_astrology_human_design.py
git commit -m "feat(4): human design port — gates, design date (integer-ms), centers/type/authority"
```

---

### Task 8: `gene_keys.py`

**Files:**
- Create: `src/quantuum/astrology/gene_keys.py`
- Test: `tests/test_astrology_gene_keys.py`

Port from `genekeys.ts`. Reproduce the full `HEXAGRAMS` table (64 rows: gate, name, shadow, gift, siddhi), `GATE_TO_HEXAGRAM` map, `GeneKeysProfile`, `calculate_gene_keys(hd)` mapping lifesWork=Personality Sun, evolution=Personality Earth, radiance=Design Sun, purpose=Design Earth, each enriched with its `line`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_astrology_gene_keys.py
from datetime import datetime, timezone
from quantuum.astrology.human_design import calculate_human_design
from quantuum.astrology.gene_keys import calculate_gene_keys

ANNA = datetime(1980, 6, 24, 7, 0, 0, tzinfo=timezone.utc)


def test_anna_gene_keys_match_golden():
    gk = calculate_gene_keys(calculate_human_design(ANNA))
    # Cross-check against anna.calc.md "## 7. Gene Keys" table rows.
    for sphere in (gk.lifes_work, gk.evolution, gk.radiance, gk.purpose):
        assert sphere.name and sphere.shadow and sphere.gift and sphere.siddhi
        assert 1 <= sphere.line <= 6
    # Fill exact gate.line + shadow/gift/siddhi from golden for each sphere.
```

- [ ] **Step 2–4:** fail → implement → pass + ruff.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/astrology/gene_keys.py tests/test_astrology_gene_keys.py
git commit -m "feat(4): gene keys port (64 hexagrams, activation sequence)"
```

---

### Task 9: `blueprint.py` orchestration — the character-exact keystone

**Files:**
- Create: `src/quantuum/astrology/blueprint.py`
- Test: `tests/test_astrology_blueprint_golden.py`

Port from `blueprint.ts`. Reproduce: `BlueprintInput` (dataclass: `full_name, birth_date, birth_time, birth_place, latitude, longitude, timezone, for_year`), `parse_blueprint_input` (optional — validation), `parse_birth_instant`, `to_iso_z(ms)`, `table(headers, rows)`, `fmt_pos`, `fmt_sign_deg`, `PLANET_GLYPH`, `ALL_PLANETS`, `PERSONAL_YEAR_THEMES`, `MATRIX_MAPPING`, `personal_year_theme`, and the full `build_blueprint(input) -> str`. Also add `from_natal_profile(profile) -> BlueprintInput` adapter (used in Task 11).

**`parse_birth_instant`** (mirror `blueprint.ts`):
```
stamp = f"{birth_date}T{birth_time}:00"
if re.fullmatch(r"[+-]\d{2}:\d{2}", timezone):
    return datetime.fromisoformat(f"{stamp}{timezone}")   # offset-aware → has UTC offset
# IANA name:
naive = datetime.fromisoformat(stamp)
local = naive.replace(tzinfo=ZoneInfo(timezone))
return local.astimezone(UTC)
```
Then `birth_ms = (birth.astimezone(UTC) - EPOCH)//timedelta(ms=1)` for `to_iso_z`.

**`to_iso_z(ms: int) -> str`**: format integer epoch-ms as `YYYY-MM-DDTHH:mm:ss.sssZ`:
```
dt = EPOCH + timedelta(milliseconds=ms)   # tz-aware UTC
return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
```

**`forYear` default**: `input.for_year if input.for_year is not None else datetime.now(UTC).year` (matches `new Date().getUTCFullYear()`). Fixtures pin it, so golden is deterministic.

**`build_blueprint`** must reproduce the exact line sequence in `blueprint.ts` lines 222–714: header block, `## 1. Identity Layer` (core astrology table, element/modality balance, house-system clarifications, house cusps), `## 2. Major Aspects` (+ key conjunctions or the italic fallback), `## 3. Vedic`, `## 4. Numerology` (+ pinnacles, challenges, timing cycles), `## 5. Chinese Four Pillars`, `## 6. Human Design` (+ matrix mapping, personality activations, design activations, active channels or fallback), `## 7. Gene Keys`, `## 8. Mayan Tzolkin`, footer. Reproduce every literal string, emoji, two-trailing-space line breaks (`  ` after birth-data lines), and `table()` formatting exactly.

The HD activation longitude cells use `to_sign_degree(lon).sign + " " + to_fixed(lon % 30, 2) + "°"`. The `Design moment` row uses `to_iso_z(hd.design_ms)`.

- [ ] **Step 1: Write the failing golden test**

```python
# tests/test_astrology_blueprint_golden.py
import json
from pathlib import Path
import pytest
from quantuum.astrology.blueprint import build_blueprint, BlueprintInput

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
```

- [ ] **Step 2: Run it to verify it fails** → FAIL (initially module-not-found, then diffs).

- [ ] **Step 3: Implement `blueprint.py`.** Iterate against the diff for each fixture until all 4 are byte-exact. When a diff appears, classify it: rounding (`js_round`/`to_fixed`), ISO formatting (`to_iso_z`), table spacing, or a literal-string typo — fix the cause. **If a diff is caused by a genuine ephemeris value difference (not formatting), STOP and surface it to the controller; do not regenerate the golden from Python.**

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_astrology_blueprint_golden.py -v` → 4 PASS. Then `uv run ruff check .`.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/astrology/blueprint.py tests/test_astrology_blueprint_golden.py
git commit -m "feat(4): blueprint orchestration — character-exact calc_md for 4 golden charts"
```

---

## Phase B — LLM polish + wiring

### Task 10: `LLMClient` abstraction + `AnthropicClient` + prompt + settings

**Files:**
- Create: `src/quantuum/llm/__init__.py`, `base.py`, `anthropic_client.py`, `registry.py`, `blueprint_polish.py`
- Create: `src/quantuum/llm/prompts/blueprint_writer.txt` (copy of `astrology/prompt.txt`)
- Modify: `src/quantuum/settings.py`
- Test: `tests/test_llm_client.py`

**`base.py`:**
```python
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int


class LLMError(RuntimeError):
    pass


@runtime_checkable
class LLMClient(Protocol):
    async def complete(
        self, *, system: str, user: str, model: str, temperature: float, max_tokens: int
    ) -> LLMResult: ...
```

**`anthropic_client.py`:** wrap `anthropic.AsyncAnthropic`. `complete()` calls `messages.create(model=model, system=system, max_tokens=max_tokens, temperature=temperature, messages=[{"role":"user","content":user}])`; extract text from `resp.content[0].text` (concatenate any text blocks), tokens from `resp.usage.input_tokens/output_tokens`. Strip a leading/trailing ```` ```markdown ```` fence (mirror `strip_markdown_fence` from `llm-blueprint.ts`). Wrap SDK errors in `LLMError`.

**`registry.py`:** `def get_llm_client(settings) -> LLMClient | None` — returns `AnthropicClient(api_key=...)` when `settings.llm_provider == "anthropic"` and `settings.llm_api_key` is set, else `None`. Leave a seam for `openai` later (not implemented now — YAGNI).

**`blueprint_polish.py`:**
```python
PROMPT_PATH = Path(__file__).parent / "prompts" / "blueprint_writer.txt"

async def polish_blueprint(client, calc_md, *, model, temperature, max_tokens) -> LLMResult:
    system = PROMPT_PATH.read_text()
    user = "\n".join([
        "Transform this calculated Markdown into the final premium Quantuum SoulMap Blueprint.",
        "",
        "CALCULATED MARKDOWN:",
        calc_md,
    ])
    return await client.complete(system=system, user=user, model=model,
                                 temperature=temperature, max_tokens=max_tokens)
```
(The user-message wrapper mirrors `llm-blueprint.ts` lines 138–145.)

**`settings.py`** — add:
```python
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = 0.85
    llm_max_tokens: int = 9000
```

**Copy the prompt:** `cp /home/ipu/code/work/astrology/prompt.txt src/quantuum/llm/prompts/blueprint_writer.txt`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_client.py
import pytest
from quantuum.llm.base import LLMClient, LLMResult
from quantuum.llm.anthropic_client import AnthropicClient
from quantuum.llm.blueprint_polish import polish_blueprint


class FakeLLM:
    def __init__(self):
        self.calls = []
    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.calls.append({"system": system, "user": user, "model": model})
        return LLMResult(text="POLISHED", model=model, tokens_in=11, tokens_out=22)


def test_fake_satisfies_protocol():
    assert isinstance(FakeLLM(), LLMClient)


async def test_polish_blueprint_wraps_calc_md():
    fake = FakeLLM()
    res = await polish_blueprint(fake, "# calc", model="m", temperature=0.1, max_tokens=1000)
    assert res.text == "POLISHED" and res.tokens_in == 11
    call = fake.calls[0]
    assert "CALCULATED MARKDOWN:" in call["user"] and "# calc" in call["user"]
    assert "Quantuum Blueprint Writer" in call["system"]  # prompt file loaded


async def test_anthropic_client_parses_response(monkeypatch):
    # Build AnthropicClient with a fake AsyncAnthropic whose messages.create
    # returns an object with .content[0].text and .usage.input_tokens/output_tokens.
    client = AnthropicClient(api_key="x")
    class _Resp:
        content = [type("B", (), {"type": "text", "text": "```markdown\nHELLO\n```"})()]
        usage = type("U", (), {"input_tokens": 5, "output_tokens": 7})()
        model = "claude-x"
    class _Msgs:
        async def create(self, **kw):
            return _Resp()
    monkeypatch.setattr(client, "_client", type("C", (), {"messages": _Msgs()})())
    res = await client.complete(system="s", user="u", model="claude-x", temperature=0.5, max_tokens=100)
    assert res.text == "HELLO"  # fence stripped
    assert res.tokens_in == 5 and res.tokens_out == 7
```

Design `AnthropicClient` so the underlying SDK object is an overridable attribute (e.g. `self._client`) to make it testable without network.

- [ ] **Step 2: Run it to verify it fails** → FAIL.

- [ ] **Step 3: Implement the `llm/` package + settings + copy prompt.**

- [ ] **Step 4: Run test to verify it passes** → PASS. Then `uv run ruff check .`.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/llm/ src/quantuum/settings.py tests/test_llm_client.py
git commit -m "feat(4): LLMClient protocol + AnthropicClient + blueprint writer prompt"
```

---

### Task 11: Rewire `blueprint_generate` to real engine + LLM; remove mock

**Files:**
- Modify: `src/quantuum/tasks/blueprint.py`
- Modify: `src/quantuum/tasks/worker.py` (add `ctx["llm_client"]`)
- Delete: `src/quantuum/domain/mock_blueprint.py`
- Modify/replace: `tests/test_task_blueprint.py`, `tests/test_blueprints_service.py`
- Test: `tests/test_task_blueprint.py` (rewritten)

New `blueprint_generate` flow (mirror spec §6 generation pipeline):
1. Load `Blueprint` + its `NatalProfile` (via `natal_profile_id`).
2. `inp = from_natal_profile(profile)`; `calc_md = build_blueprint(inp)`. Set status `calculating` with `calc_md`, then `generating`.
3. `llm_client = ctx.get("llm_client")`. If present: `result = await polish_blueprint(client, calc_md, model=settings.llm_model, temperature=settings.llm_temperature, max_tokens=settings.llm_max_tokens)`; set status `done` with `llm_md=result.text, llm_provider=settings.llm_provider, llm_model=result.model, llm_tokens_in=result.tokens_in, llm_tokens_out=result.tokens_out`. If `llm_client is None` (no API key configured): set `done` with `llm_md=calc_md, llm_provider="none", llm_model="none"` (graceful degradation — deliver the calc_md so the bot still works without an LLM key). Document this fallback.
4. Complete the request on success.
5. On exception: status `failed`, refund quota (unchanged behavior).
6. Delivery (best-effort, no refund on delivery failure): `bot.send_message(chat_id, llm_md[:500])` + `bot.send_document(BufferedInputFile(llm_md.encode(), filename="blueprint.md"))`.

`worker.py` `startup`: `ctx["llm_client"] = get_llm_client(settings)`.

Get the natal profile loader: use `session.get(NatalProfile, blueprint.natal_profile_id)`.

- [ ] **Step 1: Rewrite the failing test**

```python
# tests/test_task_blueprint.py  (replace mock-based assertions)
# Build a tenant + account + natal profile (use anna's data) + blueprint row,
# then run blueprint_generate with a fake ctx (sessionmaker, bot, llm_client=FakeLLM).
async def test_blueprint_generate_uses_real_engine_and_llm(session_factory, ...):
    # ... arrange natal profile from anna fixture ...
    fake_bot = ...  # records send_message / send_document
    fake_llm = FakeLLM()  # returns LLMResult(text="POLISHED", tokens_in=11, tokens_out=22)
    ctx = {"sessionmaker": session_factory, "bot": fake_bot, "llm_client": fake_llm}
    await blueprint_generate(ctx, blueprint_id, chat_id=123, request_id=req_id)

    bp = await reload(blueprint_id)
    assert bp.status == "done"
    assert bp.calc_md.startswith("# Quantuum Blueprint —")
    assert bp.llm_md == "POLISHED"
    assert bp.llm_tokens_in == 11 and bp.llm_tokens_out == 22
    assert bp.llm_provider == "anthropic" or bp.llm_provider  # provider recorded
    # delivery used llm_md
    assert fake_bot.documents  # a document was sent


async def test_blueprint_generate_without_llm_falls_back_to_calc_md(...):
    ctx = {"sessionmaker": session_factory, "bot": fake_bot, "llm_client": None}
    await blueprint_generate(ctx, blueprint_id, chat_id=123, request_id=req_id)
    bp = await reload(blueprint_id)
    assert bp.status == "done"
    assert bp.llm_md == bp.calc_md and bp.llm_provider == "none"


async def test_blueprint_generate_failure_refunds(...):
    # Make build_blueprint raise (e.g. monkeypatch) → status failed + quota refunded.
```

Reuse existing test scaffolding/fixtures in `tests/test_task_blueprint.py` for tenant/account/profile creation. Keep the existing delivery/refund test intent; only swap mock expectations for real-engine + llm expectations. Update `tests/test_blueprints_service.py` to drop `MOCK_BLUEPRINT_MD` import/asserts (test `set_status`/`create_blueprint` with a literal `calc_md` string instead).

- [ ] **Step 2: Run it to verify it fails** → FAIL (still imports mock / old behavior).

- [ ] **Step 3: Implement the rewire + delete mock.**

```bash
git rm src/quantuum/domain/mock_blueprint.py
```
Edit `tasks/blueprint.py` and `tasks/worker.py`. Remove all `mock_blueprint` imports across the repo (`grep -rn mock_blueprint src tests`).

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run: `uv run pytest tests/test_task_blueprint.py tests/test_blueprints_service.py -v` → PASS. Then `uv run ruff check .`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(4): wire blueprint_generate to real engine + LLM polish; remove mock"
```

---

### Task 12: Worker/env wiring + docs

**Files:**
- Modify: `.env.example` (and `compose/.env.example` / compose env if LLM vars belong there)
- Modify: `docs/superpowers/specs/...` is NOT edited; instead add a short note in the plan's deploy section (below)
- Test: full suite

- [ ] **Step 1: Add LLM_* to `.env.example`**

```
LLM_PROVIDER=anthropic
LLM_API_KEY=
LLM_MODEL=claude-sonnet-4-6
LLM_TEMPERATURE=0.85
LLM_MAX_TOKENS=9000
```
Pydantic settings read these as `llm_provider`, `llm_api_key`, etc. (case-insensitive env mapping). If the task-worker service in `compose/docker-compose*.yml` needs the LLM key, add `LLM_API_KEY`/`LLM_MODEL` to its environment (pull from host env `${LLM_API_KEY:-}` — do NOT hardcode secrets).

- [ ] **Step 2: Confirm worker startup builds the client**

Verify `worker.py` `startup` sets `ctx["llm_client"] = get_llm_client(settings)` and `shutdown` closes nothing extra (the Anthropic async client doesn't require explicit close, but if it exposes `.aclose()`, call it in shutdown).

- [ ] **Step 3: Run the full suite (stage completion)**

Run: `uv run pytest -q` → all green. Then `uv run ruff check .`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(4): LLM env wiring (.env.example, compose) for blueprint polish"
```

---

## Self-Review (run after writing, before execution)

- **Spec coverage (§6):** module-by-module port table → Tasks 2–9; character-exact calc_md anchor → Task 9 golden test; `LLMClient` Protocol + Anthropic default + prompt file → Task 10; generation flow (calc → llm → deliver, status transitions, refund) → Task 11; env/provider selection → Tasks 10/12. ✓
- **Determinism:** all 4 fixtures pin `forYear`, so golden has no wall-clock dependency. ✓
- **Parity hazards** each have a dedicated helper and are called out at task level (`js_round`, `to_fixed`, `to_iso_z`, integer-ms iteration, `zoneinfo`+`tzdata`). ✓
- **No circular golden:** golden generated from the TS engine (Task 1), never from Python; divergence escalates rather than silently regenerating. ✓
- **Type consistency:** `SignDegree`/`Position`, `HumanDesignChart.design_ms`, `LLMResult` field names used consistently across Tasks 4/7/9/10/11. ✓

## Deploy notes (after merge)

- No DB migration in this plan (no schema change — `blueprints.calc_md/llm_md/llm_*` already exist from earlier stages).
- Set `LLM_API_KEY` (+ optionally `LLM_MODEL`) in the task-worker environment. Without it, generation gracefully falls back to delivering `calc_md` (`llm_provider="none"`).
- Rebuild the task-worker image so the new deps (`astronomy-engine`, `lunar-python`, `tzdata`, `anthropic`) are installed. `tzdata` is required for IANA timezones inside the container.
