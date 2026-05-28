# SP6 — Tarot / I-Ching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two divinatory reading kinds — `"tarot"` (three-card past/present/future with reversals) and `"iching"` (three-coin cast with primary + transformed hexagram) — on the existing readings pipeline. User optionally types a question that frames the LLM interpretation; `/skip` produces a generic guidance reading.

**Architecture:** Reuses the existing `Reading` table + worker + quota + request + delivery. A new JSONB column `Reading.draw_jsonb` stores the cast (cards/lines + optional question). Two new data modules under `src/quantuum/divination/` produce a `calc_md` from the random draw, which is then polished by the existing LLM `polish_reading` path with two new prompts. A new handler module owns the question-FSM and intercepts the readings router for tarot/iching kinds.

**Tech Stack:** Python 3.13 (PEP 604 unions), SQLModel + Alembic on PostgreSQL, aiogram 3 (FSM + CallbackData), structlog, pytest-asyncio. Standing constraints: work on `main`, ruff-clean source, no emojis in source/comments (LLM prompts may use emojis since the existing reading prompts do), TDD red→green→commit per task, per-task targeted tests during execution, full suite + ruff only at T7.

**Spec:** `docs/superpowers/specs/2026-05-28-tarot-iching-design.md`

---

## File map

**Created**
- `alembic/versions/a3b4c5d6e7f8_readings_draw_jsonb.py` — migration
- `src/quantuum/divination/__init__.py` — package marker + `build_divination_calc_md` dispatcher
- `src/quantuum/divination/tarot.py` — deck constant + dataclasses + draw + calc_md (+ JSONB rehydrator)
- `src/quantuum/divination/iching.py` — hexagram constant + dataclasses + cast + calc_md (+ JSONB rehydrator)
- `src/quantuum/llm/prompts/reading_tarot.txt` — LLM voice rules for tarot
- `src/quantuum/llm/prompts/reading_iching.txt` — LLM voice rules for i-ching
- `src/quantuum/bot/handlers/divination.py` — handler + FSM
- `tests/test_divination_tarot.py`
- `tests/test_divination_iching.py`
- `tests/test_reading_task_divination.py`
- `tests/test_divination_handler.py`
- `tests/test_divination_i18n.py`

**Modified**
- `src/quantuum/db/models.py` (`Reading` class) — add `draw_jsonb: dict | None = ...`
- `src/quantuum/tasks/reading.py` — branch on kind; call `build_divination_calc_md` for tarot/iching
- `src/quantuum/llm/reading_polish.py` — register two new prompts + labels
- `src/quantuum/domain/tenant_features.py` — append `"reading.tarot"`, `"reading.iching"` to `FEATURE_KEYS`
- `src/quantuum/bot/ui/keyboards.py` — append `"tarot"`, `"iching"` to `READING_KINDS`
- `src/quantuum/bot/handlers/owner_console.py` — extend the features keyboard's reading-kind loop to include `tarot`, `iching`; update `b.adjust(2, ...)` to 7 rows
- `src/quantuum/bot/app.py` — `dp.include_router(divination.router)` BEFORE `dp.include_router(readings.router)`
- `src/quantuum/i18n/seed_strings.py` — ~14 new keys
- `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py` — same ~14 keys per locale
- `tests/test_tenant_features_domain.py` — inventory bump 14 → 16
- `tests/test_ui_keyboards.py` — assertion includes the two new menu labels
- `tests/test_bot_start_menu_profile.py` — same menu-button bump if any assertion lists reading kinds (unlikely — main menu lists `btn.*`, not readings)

---

## Task 1 — Migration + `Reading.draw_jsonb`

**Files:**
- Create: `alembic/versions/a3b4c5d6e7f8_readings_draw_jsonb.py`
- Modify: `src/quantuum/db/models.py` (`Reading` class — currently at lines 162-182)
- Test: extend `tests/test_db_models.py` with a smoke test

**Context:** The current `Reading` model has no `draw_jsonb` column. After this task, `Reading.draw_jsonb` is `dict | None` (NULL for the 8 chart-based kinds; populated for tarot/iching).

Before the migration, confirm the head revision:

```
ls alembic/versions/ | sort
# Expect the SP5 chain head to be f2a3b4c5d6e7_drop_start_token_uses_account_unique.py
```

- [ ] **Step 1: Write the failing smoke test**

Append to `tests/test_db_models.py` (or create `tests/test_reading_draw_jsonb.py` if you prefer a dedicated file — your call):

```python
async def test_reading_accepts_draw_jsonb(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile, Reading
    from datetime import date, time

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="1001"
    )
    profile = NatalProfile(
        account_id=acc.id, full_name="X",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(profile)
    await session.flush()

    r = Reading(
        tenant_id=default_tenant.id,
        account_id=acc.id,
        natal_profile_id=profile.id,
        kind="tarot",
        lang="en",
        draw_jsonb={"question": "Is this a test?", "cards": []},
    )
    session.add(r)
    await session.flush()

    reloaded = await session.get(Reading, r.id)
    assert reloaded.draw_jsonb == {"question": "Is this a test?", "cards": []}


async def test_reading_draw_jsonb_default_none(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import NatalProfile, Reading
    from datetime import date, time

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="2001"
    )
    profile = NatalProfile(
        account_id=acc.id, full_name="X",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(profile)
    await session.flush()

    r = Reading(
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, kind="bazi",
    )
    session.add(r)
    await session.flush()
    assert (await session.get(Reading, r.id)).draw_jsonb is None
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_db_models.py::test_reading_accepts_draw_jsonb tests/test_db_models.py::test_reading_draw_jsonb_default_none -v
```

Expected: AttributeError / SQL column does not exist (or model field missing).

- [ ] **Step 3: Write the migration**

```python
# alembic/versions/a3b4c5d6e7f8_readings_draw_jsonb.py
"""readings.draw_jsonb (tarot/iching cast storage)

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-05-28 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "readings",
        sa.Column(
            "draw_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("readings", "draw_jsonb")
```

Verify the `down_revision` matches the actual SP5 chain head before committing.

- [ ] **Step 4: Update the model**

Open `src/quantuum/db/models.py` around the `Reading` class (lines 162-182). Add the field next to other JSONB-style fields. The pattern in this codebase uses `Field(default_factory=dict, sa_column=Column(JSONB, ...))` for non-null JSONB (see `AuditLog.payload_jsonb`) — for nullable JSONB use:

```python
draw_jsonb: dict | None = Field(
    default=None, sa_column=Column(JSONB, nullable=True)
)
```

Add this field after `completed_at`. If `Column` / `JSONB` aren't yet imported into the file scope (they are — `AuditLog` uses both), no new imports needed.

- [ ] **Step 5: Run tests to verify pass**

```
uv run pytest tests/test_db_models.py::test_reading_accepts_draw_jsonb tests/test_db_models.py::test_reading_draw_jsonb_default_none -v
```

Expected: PASS. The schema fixture rebuilds the test schema on the next pytest run because the model changed.

- [ ] **Step 6: Run existing reading-touching tests for no regression**

```
uv run pytest tests/test_readings_domain.py tests/test_readings_bot.py -v
```

Expected: all pass.

- [ ] **Step 7: Ruff + commit**

```
uv run ruff check alembic/versions/a3b4c5d6e7f8_readings_draw_jsonb.py src/quantuum/db/models.py
git add alembic/versions/a3b4c5d6e7f8_readings_draw_jsonb.py \
        src/quantuum/db/models.py tests/test_db_models.py
git commit -m "feat(sp6-t1): readings.draw_jsonb column for tarot/iching"
```

---

## Task 2 — `divination/tarot.py`

**Files:**
- Create: `src/quantuum/divination/__init__.py`
- Create: `src/quantuum/divination/tarot.py`
- Test: `tests/test_divination_tarot.py`

**Context:** Pure-data module — no DB, no async. The deck is a constant; `draw_three` accepts an injected `random.Random` for testability. `build_calc_md` produces the markdown the LLM polishes.

### The deck

The deck must contain **all 78 Rider-Waite-Smith cards**: 22 Major Arcana (0–21) and 56 Minor Arcana (4 suits × 14: Ace, 2, 3, 4, 5, 6, 7, 8, 9, 10, Page, Knight, Queen, King). For each card include short upright/reversed keyword tuples (3-5 keywords each).

Use the canonical English card names exactly as in the Rider-Waite tradition (e.g. "The Fool", "The Magician", "Ace of Wands", "Page of Cups", "Knight of Swords", "Queen of Pentacles", "King of Pentacles"). Keywords are short, archetypal English phrases (e.g. for The Fool: upright `("beginnings", "innocence", "leap of faith", "spontaneity")`, reversed `("recklessness", "naivety", "hesitation")`).

The implementer can paraphrase keywords from any standard tarot reference (Rider-Waite descriptions are public knowledge). Aim for 3-5 keywords per orientation. Consistency matters more than literary depth — these feed the LLM, not the user.

- [ ] **Step 1: Write the failing test**

Create `tests/test_divination_tarot.py`:

```python
import random

import pytest

from quantuum.divination.tarot import (
    TAROT_DECK, Card, CardDraw,
    build_calc_md,
    build_calc_md_from_jsonb,
    draw_three,
)


def test_deck_has_78_cards():
    assert len(TAROT_DECK) == 78


def test_deck_has_22_majors():
    majors = [c for c in TAROT_DECK if c.arcana == "major"]
    assert len(majors) == 22


def test_deck_has_four_suits_of_14():
    for suit in ("wands", "cups", "swords", "pentacles"):
        suit_cards = [c for c in TAROT_DECK if c.suit == suit]
        assert len(suit_cards) == 14, f"suit {suit} has {len(suit_cards)} cards"


def test_all_card_ids_are_unique():
    ids = [c.id for c in TAROT_DECK]
    assert len(set(ids)) == 78


def test_every_card_has_keywords():
    for c in TAROT_DECK:
        assert len(c.upright) >= 3, f"{c.id} upright"
        assert len(c.reversed) >= 3, f"{c.id} reversed"


def test_draw_three_returns_three_distinct_cards():
    rng = random.Random(42)
    cards = draw_three(rng=rng)
    assert len(cards) == 3
    ids = [d.card.id for d in cards]
    assert len(set(ids)) == 3


def test_draw_three_positions_are_past_present_future():
    rng = random.Random(42)
    cards = draw_three(rng=rng)
    assert [d.position for d in cards] == ["past", "present", "future"]


def test_draw_three_is_deterministic_with_seeded_rng():
    a = draw_three(rng=random.Random(123))
    b = draw_three(rng=random.Random(123))
    assert [(d.card.id, d.reversed, d.position) for d in a] == \
           [(d.card.id, d.reversed, d.position) for d in b]


def test_reversal_distribution_is_roughly_uniform():
    rng = random.Random(7)
    reversed_count = 0
    total = 0
    for _ in range(500):
        for d in draw_three(rng=rng):
            reversed_count += int(d.reversed)
            total += 1
    # 1500 trials, expected mean 750, std-dev ~19; allow generous tolerance.
    assert 600 < reversed_count < 900


def test_build_calc_md_includes_question_and_all_three_cards():
    cards = [
        CardDraw(card=TAROT_DECK[0], reversed=False, position="past"),
        CardDraw(card=TAROT_DECK[1], reversed=True, position="present"),
        CardDraw(card=TAROT_DECK[2], reversed=False, position="future"),
    ]
    md = build_calc_md(question="Will I find love?", cards=cards)
    assert "Will I find love?" in md
    assert TAROT_DECK[0].name in md
    assert TAROT_DECK[1].name in md
    assert TAROT_DECK[2].name in md
    assert "reversed" in md.lower()


def test_build_calc_md_no_question_renders_placeholder():
    cards = [
        CardDraw(card=TAROT_DECK[0], reversed=False, position="past"),
        CardDraw(card=TAROT_DECK[1], reversed=False, position="present"),
        CardDraw(card=TAROT_DECK[2], reversed=False, position="future"),
    ]
    md = build_calc_md(question=None, cards=cards)
    # No question → either omit "Question" section or show "(none)" placeholder.
    # The exact text is implementation choice; assert that no None-coercion bug appears.
    assert "None" not in md  # don't render the literal Python None


def test_build_calc_md_from_jsonb_round_trip():
    rng = random.Random(11)
    cards = draw_three(rng=rng)
    payload = {
        "question": "test",
        "cards": [
            {"id": d.card.id, "reversed": d.reversed, "position": d.position}
            for d in cards
        ],
    }
    md = build_calc_md_from_jsonb(payload)
    for d in cards:
        assert d.card.name in md


def test_build_calc_md_from_jsonb_rejects_unknown_card_id():
    payload = {"question": None, "cards": [
        {"id": "bogus_xx", "reversed": False, "position": "past"},
        {"id": "major_00_fool", "reversed": False, "position": "present"},
        {"id": "major_01_magician", "reversed": False, "position": "future"},
    ]}
    with pytest.raises(KeyError):
        build_calc_md_from_jsonb(payload)
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_divination_tarot.py -v
```

Expected: ImportError / module not found.

- [ ] **Step 3: Create `src/quantuum/divination/__init__.py`**

```python
from quantuum.divination import iching, tarot


def build_divination_calc_md(kind: str, draw: dict | None) -> str:
    """Dispatch divination calc_md builders by kind."""
    if draw is None:
        raise ValueError(f"divination kind {kind!r} requires draw_jsonb")
    if kind == "tarot":
        return tarot.build_calc_md_from_jsonb(draw)
    if kind == "iching":
        return iching.build_calc_md_from_jsonb(draw)
    raise ValueError(f"not a divination kind: {kind!r}")
```

(`iching` won't exist until T3 — the import will fail until then. To keep this task green, the dispatcher can be added in T4 instead. Alternative: leave `__init__.py` empty in T2 and let T3 add the iching half + T4 add the dispatcher. Pick whichever keeps the test for THIS task green. Simplest: leave `__init__.py` empty here, add the dispatcher in T4.)

- [ ] **Step 4: Write `src/quantuum/divination/tarot.py`**

```python
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Card:
    id: str           # canonical id, e.g. "major_00_fool", "wands_05", "cups_page"
    name: str         # English name as in Rider-Waite-Smith
    arcana: str       # "major" | "minor"
    suit: str | None  # "wands" | "cups" | "swords" | "pentacles" | None
    number: int | None
    upright: tuple[str, ...]
    reversed: tuple[str, ...]


@dataclass(frozen=True)
class CardDraw:
    card: Card
    reversed: bool
    position: str  # "past" | "present" | "future"


# Canonical 78-card Rider-Waite-Smith deck. Implementer fills the full deck
# below — 22 majors (numbered 00-21) and 56 minors (4 suits × Ace + 2-10 + Page
# + Knight + Queen + King). Use public-knowledge keywords (3-5 per orientation).
TAROT_DECK: list[Card] = [
    # ───── Major Arcana (22) ─────
    Card(id="major_00_fool", name="The Fool", arcana="major", suit=None, number=0,
         upright=("beginnings", "innocence", "leap of faith", "spontaneity"),
         reversed=("recklessness", "naivety", "hesitation")),
    Card(id="major_01_magician", name="The Magician", arcana="major", suit=None, number=1,
         upright=("manifestation", "willpower", "skill", "focus"),
         reversed=("manipulation", "blocked talent", "wasted skill")),
    # ... (20 more majors — High Priestess through The World) ...

    # ───── Minor Arcana — Wands (14) ─────
    Card(id="wands_01", name="Ace of Wands", arcana="minor", suit="wands", number=1,
         upright=("inspiration", "new opportunity", "creative spark", "potential"),
         reversed=("delay", "creative block", "missed opportunity")),
    # ... 2 through 10, Page, Knight, Queen, King ...

    # ───── Minor Arcana — Cups (14) ─────
    # Ace of Cups through King of Cups
    # ... 14 entries ...

    # ───── Minor Arcana — Swords (14) ─────
    # Ace of Swords through King of Swords
    # ... 14 entries ...

    # ───── Minor Arcana — Pentacles (14) ─────
    # Ace of Pentacles through King of Pentacles
    # ... 14 entries ...
]

# After filling the deck:
assert len(TAROT_DECK) == 78, f"expected 78 cards, got {len(TAROT_DECK)}"
assert len({c.id for c in TAROT_DECK}) == 78, "duplicate card ids"

_DECK_BY_ID: dict[str, Card] = {c.id: c for c in TAROT_DECK}

_POSITIONS: tuple[str, ...] = ("past", "present", "future")


def draw_three(rng: random.Random | None = None) -> list[CardDraw]:
    """Draw three distinct cards. Each card is independently 50/50 reversed."""
    r = rng if rng is not None else random.SystemRandom()
    drawn = r.sample(TAROT_DECK, 3)
    return [
        CardDraw(card=card, reversed=bool(r.randrange(2)), position=pos)
        for card, pos in zip(drawn, _POSITIONS, strict=True)
    ]


def build_calc_md(*, question: str | None, cards: list[CardDraw]) -> str:
    """Markdown summary the LLM polishes."""
    lines: list[str] = ["# Tarot — Three-Card Spread", ""]
    if question:
        lines.append(f"**Question:** {question}")
    else:
        lines.append("**Question:** (none)")
    lines.append("")
    for d in cards:
        orient = "reversed" if d.reversed else "upright"
        kw = ", ".join(d.reversed and d.card.reversed or d.card.upright)
        lines.append(f"## {d.position.capitalize()} — {d.card.name} ({orient})")
        lines.append(f"Keywords: {kw}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_calc_md_from_jsonb(draw: dict) -> str:
    """Rehydrate from the persisted draw_jsonb and reuse build_calc_md."""
    question = draw.get("question")
    cards: list[CardDraw] = []
    for entry in draw.get("cards", []):
        card_id = entry["id"]
        if card_id not in _DECK_BY_ID:
            raise KeyError(f"unknown tarot card id: {card_id}")
        cards.append(CardDraw(
            card=_DECK_BY_ID[card_id],
            reversed=bool(entry.get("reversed", False)),
            position=entry["position"],
        ))
    return build_calc_md(question=question, cards=cards)
```

**Implementer note:** the deck section above shows only the first few entries. You MUST fill in the remaining 76 cards. Sources for canonical names + meanings: the Wikipedia article on the Rider-Waite tarot deck, or any standard tarot reference. The IDs follow the pattern:
- Majors: `major_NN_<slug>` with NN as zero-padded number 00–21 and slug lower-snake-case from the canonical name (`major_02_high_priestess`, `major_21_world`).
- Minors: `<suit>_NN` for numbered cards (01–10), and `<suit>_page`/`<suit>_knight`/`<suit>_queen`/`<suit>_king` for the court cards (`wands_page`, `cups_knight`, etc.).

Aim for ~3-5 keywords per orientation. Do NOT skip cards or stub-fill — every card must have real keywords. Tests will fail if any card has `<3` keywords on either orientation.

- [ ] **Step 5: Run tests to green**

```
uv run pytest tests/test_divination_tarot.py -v
```

Expected: all PASS.

- [ ] **Step 6: Ruff + commit**

```
uv run ruff check src/quantuum/divination/ tests/test_divination_tarot.py
git add src/quantuum/divination/__init__.py src/quantuum/divination/tarot.py \
        tests/test_divination_tarot.py
git commit -m "feat(sp6-t2): tarot deck + draw_three + calc_md"
```

---

## Task 3 — `divination/iching.py`

**Files:**
- Create: `src/quantuum/divination/iching.py`
- Test: `tests/test_divination_iching.py`

**Context:** 64-hexagram public-domain dataset (Wilhelm 1924 translation or equivalent) + `cast_three_coins` simulator + calc_md builder. The casting mechanic is canonical:

- Per line: three coins thrown. Heads = 3, tails = 2 (or vice-versa, project standard pick one). Sum is 6/7/8/9.
- Line values 7 (yang) and 8 (yin) are static. Values 6 (old yin → changes to yang) and 9 (old yang → changes to yin) are "changing lines."
- Six lines built bottom→top.
- The 6 line values (as yin=broken, yang=solid) form a hexagram pattern — look up via the canonical King Wen sequence to a hexagram id 1–64.
- If any line is changing, build the "transformed" hexagram by flipping the changing lines (6→7, 9→8), then look up.

### The dataset

The implementer MUST include all 64 hexagrams with English judgment + image + 6 line-statement texts (Wilhelm or Legge translations are public domain). Authoritative sources:
- Richard Wilhelm, *I Ching or Book of Changes* (1924), the de facto English standard.
- James Legge, *The Sacred Books of the East: The I Ching* (1882) — fully public domain in the US.

The text per hexagram is short: judgment is ~1–3 sentences, image is ~1–3 sentences, line statements are ~1–2 sentences each. Approximate total per hexagram: ~500 bytes × 64 = ~32 KB total.

- [ ] **Step 1: Write the failing test**

Create `tests/test_divination_iching.py`:

```python
import random

import pytest

from quantuum.divination.iching import (
    HEXAGRAMS, CastResult, Hexagram,
    build_calc_md,
    build_calc_md_from_jsonb,
    cast_three_coins,
)


def test_64_hexagrams_present():
    assert set(HEXAGRAMS.keys()) == set(range(1, 65))


def test_every_hexagram_has_full_data():
    for hid, h in HEXAGRAMS.items():
        assert h.number == hid
        assert isinstance(h.name_en, str) and h.name_en
        assert isinstance(h.judgment, str) and len(h.judgment) > 10
        assert isinstance(h.image, str) and len(h.image) > 10
        assert len(h.lines) == 6
        for line_text in h.lines:
            assert isinstance(line_text, str) and len(line_text) > 0


def test_cast_three_coins_produces_six_lines():
    rng = random.Random(0)
    cast = cast_three_coins(rng=rng)
    assert len(cast.lines) == 6


def test_cast_line_values_are_in_6_7_8_9():
    rng = random.Random(0)
    for _ in range(50):
        cast = cast_three_coins(rng=rng)
        for v in cast.lines:
            assert v in (6, 7, 8, 9)


def test_cast_changing_indices_match_6_and_9():
    rng = random.Random(99)
    for _ in range(20):
        cast = cast_three_coins(rng=rng)
        expected = tuple(i for i, v in enumerate(cast.lines) if v in (6, 9))
        assert cast.changing_indices == expected


def test_transformed_hexagram_is_none_when_no_changing_lines():
    # Build a CastResult manually with all 7s and 8s
    cast = CastResult(
        lines=(7, 8, 7, 8, 7, 8), changing_indices=(),
        primary_id=63, transformed_id=None,
    )
    # The lookup should not have produced a transformed_id
    assert cast.transformed_id is None


def test_cast_is_deterministic_with_seeded_rng():
    a = cast_three_coins(rng=random.Random(123))
    b = cast_three_coins(rng=random.Random(123))
    assert a == b


def test_primary_id_in_1_64():
    rng = random.Random(7)
    for _ in range(50):
        cast = cast_three_coins(rng=rng)
        assert 1 <= cast.primary_id <= 64
        if cast.transformed_id is not None:
            assert 1 <= cast.transformed_id <= 64


def test_build_calc_md_includes_question_and_primary_hex():
    cast = cast_three_coins(rng=random.Random(2))
    md = build_calc_md(question="What should I do?", cast=cast)
    primary = HEXAGRAMS[cast.primary_id]
    assert "What should I do?" in md
    assert primary.name_en in md
    assert "Judgment" in md or "judgment" in md
    assert "Image" in md or "image" in md


def test_build_calc_md_no_question_safe():
    cast = cast_three_coins(rng=random.Random(2))
    md = build_calc_md(question=None, cast=cast)
    assert "None" not in md


def test_build_calc_md_changing_lines_surface_line_text():
    # Force a cast with at least one changing line.
    cast = CastResult(
        lines=(9, 7, 7, 8, 8, 8), changing_indices=(0,),
        primary_id=1, transformed_id=44,
    )
    md = build_calc_md(question=None, cast=cast)
    # Line statement for the bottom (index 0) line of hex 1 should appear.
    expected_line_text = HEXAGRAMS[1].lines[0]
    assert expected_line_text[:30] in md
    # Transformed name should appear
    assert HEXAGRAMS[44].name_en in md


def test_build_calc_md_from_jsonb_round_trip():
    cast = cast_three_coins(rng=random.Random(11))
    payload = {
        "question": "test",
        "lines": list(cast.lines),
        "primary_id": cast.primary_id,
        "transformed_id": cast.transformed_id,
        "changing_indices": list(cast.changing_indices),
    }
    md = build_calc_md_from_jsonb(payload)
    assert HEXAGRAMS[cast.primary_id].name_en in md


def test_build_calc_md_from_jsonb_rejects_invalid_primary_id():
    with pytest.raises(KeyError):
        build_calc_md_from_jsonb({
            "question": None, "lines": [7, 7, 7, 7, 7, 7],
            "primary_id": 99, "transformed_id": None, "changing_indices": [],
        })
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_divination_iching.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write `src/quantuum/divination/iching.py`**

```python
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Hexagram:
    number: int          # 1..64
    name_en: str         # e.g. "The Creative"
    name_pinyin: str     # e.g. "Qian"
    trigram_above: str
    trigram_below: str
    judgment: str        # 1-3 sentences
    image: str           # 1-3 sentences
    lines: tuple[str, ...]  # exactly 6 line statements, bottom→top


@dataclass(frozen=True)
class CastResult:
    lines: tuple[int, ...]            # six values in {6, 7, 8, 9}, bottom→top
    changing_indices: tuple[int, ...] # 0-based positions of 6/9 lines
    primary_id: int                   # 1..64
    transformed_id: int | None        # None when no changing lines


# Canonical King Wen sequence. Implementer fills all 64 entries.
# Source: Wilhelm 1924 (preferred) or Legge 1882, both public-domain
# English translations of the Yijing.
HEXAGRAMS: dict[int, Hexagram] = {
    1: Hexagram(
        number=1, name_en="The Creative", name_pinyin="Qian",
        trigram_above="heaven", trigram_below="heaven",
        judgment="The Creative works sublime success, furthering through perseverance.",
        image="The movement of heaven is full of power. Thus the superior person makes himself strong and untiring.",
        lines=(
            "Nine at the beginning: Hidden dragon. Do not act.",
            "Nine in the second place: Dragon appearing in the field. It furthers one to see the great man.",
            "Nine in the third place: All day long the superior person is creatively active. At nightfall his mind is still beset with cares. Danger. No blame.",
            "Nine in the fourth place: Wavering flight over the depths. No blame.",
            "Nine in the fifth place: Flying dragon in the heavens. It furthers one to see the great man.",
            "Nine at the top: Arrogant dragon will have cause to repent.",
        ),
    ),
    2: Hexagram(
        number=2, name_en="The Receptive", name_pinyin="Kun",
        trigram_above="earth", trigram_below="earth",
        judgment="The Receptive brings about sublime success, furthering through the perseverance of a mare.",
        image="The earth's condition is receptive devotion. Thus the superior person who has breadth of character carries the outer world.",
        lines=(
            "Six at the beginning: When there is hoarfrost underfoot, solid ice is not far off.",
            "Six in the second place: Straight, square, great. Without purpose, yet nothing remains unfurthered.",
            "Six in the third place: Hidden lines. One is able to remain persevering. If by chance you are in the service of a king, seek not works but bring to completion.",
            "Six in the fourth place: A tied-up sack. No blame, no praise.",
            "Six in the fifth place: A yellow lower garment brings supreme good fortune.",
            "Six at the top: Dragons fight in the meadow. Their blood is black and yellow.",
        ),
    ),
    # ... 62 more hexagrams (3 = Difficulty at the Beginning, 4 = Youthful Folly,
    # ..., 64 = Before Completion) ...
}

# After filling all 64:
assert set(HEXAGRAMS.keys()) == set(range(1, 65)), \
    f"missing hexagrams: {set(range(1, 65)) - set(HEXAGRAMS.keys())}"


# King Wen lookup: a 6-bit pattern (bottom→top, yin=0, yang=1) → 1..64.
# The canonical order is well-defined; the implementer fills this table.
# Source: the standard King Wen sequence chart (Wikipedia I-Ching article
# includes a complete trigram-pair → hexagram table).
#
# Encoding: index = sum(bit_i << i for i, bit_i in enumerate(pattern_bottom_to_top))
# Or use the (above_trigram, below_trigram) pair lookup — pick the implementation
# that you find cleanest.

_KING_WEN: dict[int, int] = {
    # bottom_to_top 6-bit int → hexagram number 1..64
    # ... 64 entries ...
}

assert len(_KING_WEN) == 64


def _lines_to_pattern(lines: tuple[int, ...]) -> int:
    """6-bit pattern (bottom→top); yang (7 or 9) = 1, yin (6 or 8) = 0."""
    pat = 0
    for i, v in enumerate(lines):
        if v in (7, 9):
            pat |= 1 << i
    return pat


def _transform(lines: tuple[int, ...]) -> tuple[int, ...]:
    """6 → 7 (changing yin becomes yang); 9 → 8 (changing yang becomes yin).
    Static 7 and 8 are unchanged.
    """
    return tuple(
        7 if v == 6 else 8 if v == 9 else v
        for v in lines
    )


def cast_three_coins(rng: random.Random | None = None) -> CastResult:
    """Standard three-coin method: heads=3, tails=2; sum of 3 throws yields 6-9."""
    r = rng if rng is not None else random.SystemRandom()
    lines = tuple(
        sum(r.choice((2, 3)) for _ in range(3))
        for _ in range(6)
    )
    changing = tuple(i for i, v in enumerate(lines) if v in (6, 9))
    primary_id = _KING_WEN[_lines_to_pattern(lines)]
    transformed_id: int | None = None
    if changing:
        transformed_id = _KING_WEN[_lines_to_pattern(_transform(lines))]
    return CastResult(
        lines=lines,
        changing_indices=changing,
        primary_id=primary_id,
        transformed_id=transformed_id,
    )


def build_calc_md(*, question: str | None, cast: CastResult) -> str:
    primary = HEXAGRAMS[cast.primary_id]
    out: list[str] = ["# I-Ching — Three-Coin Cast", ""]
    if question:
        out.append(f"**Question:** {question}")
    else:
        out.append("**Question:** (none)")
    out += ["", f"## Primary Hexagram {primary.number}: {primary.name_en} ({primary.name_pinyin})"]
    out += [f"Trigrams: {primary.trigram_above} above, {primary.trigram_below} below", ""]
    out += ["**Judgment:**", primary.judgment, "", "**Image:**", primary.image, ""]
    if cast.changing_indices:
        out.append("## Changing Lines")
        for idx in cast.changing_indices:
            out.append(f"- Line {idx + 1} (bottom is 1): {primary.lines[idx]}")
        out.append("")
        if cast.transformed_id is not None:
            t = HEXAGRAMS[cast.transformed_id]
            out += [f"## Becomes Hexagram {t.number}: {t.name_en} ({t.name_pinyin})"]
            out += ["**Judgment:**", t.judgment, ""]
    return "\n".join(out).rstrip() + "\n"


def build_calc_md_from_jsonb(draw: dict) -> str:
    """Rehydrate from the persisted draw_jsonb and reuse build_calc_md."""
    primary_id = draw["primary_id"]
    if primary_id not in HEXAGRAMS:
        raise KeyError(f"unknown hexagram id: {primary_id}")
    transformed_id = draw.get("transformed_id")
    if transformed_id is not None and transformed_id not in HEXAGRAMS:
        raise KeyError(f"unknown transformed hexagram id: {transformed_id}")
    cast = CastResult(
        lines=tuple(draw["lines"]),
        changing_indices=tuple(draw.get("changing_indices", [])),
        primary_id=primary_id,
        transformed_id=transformed_id,
    )
    return build_calc_md(question=draw.get("question"), cast=cast)
```

**Implementer notes for filling in the data:**
- For the 64 hexagrams: Wilhelm's translation is in print and widely scanned; the text per hexagram is short. You may also find a CC0 / public-domain JSON version online — verify the license before using. Avoid copy-pasting from copyrighted modern commentaries.
- For the King Wen lookup table: Wikipedia's "I Ching" article includes a standard 8×8 grid mapping (upper trigram, lower trigram) → hexagram number. Convert to the bit-pattern integer keying. Verify by sanity-checking a few well-known hexagrams: pattern `0b111111` (all yang) → 1 (Creative); `0b000000` (all yin) → 2 (Receptive); `0b010111` (yang below, water above) → 5 (Waiting). If your patterns don't match those, your bit ordering is inverted — fix it.

- [ ] **Step 4: Run tests to green**

```
uv run pytest tests/test_divination_iching.py -v
```

Expected: all PASS.

- [ ] **Step 5: Wire the dispatcher in `__init__.py`**

Now that `iching.py` exists, add the dispatcher to `src/quantuum/divination/__init__.py`:

```python
from quantuum.divination import iching, tarot


def build_divination_calc_md(kind: str, draw: dict | None) -> str:
    """Dispatch divination calc_md builders by kind."""
    if draw is None:
        raise ValueError(f"divination kind {kind!r} requires draw_jsonb")
    if kind == "tarot":
        return tarot.build_calc_md_from_jsonb(draw)
    if kind == "iching":
        return iching.build_calc_md_from_jsonb(draw)
    raise ValueError(f"not a divination kind: {kind!r}")
```

Verify the tarot tests still pass:

```
uv run pytest tests/test_divination_tarot.py -v
```

- [ ] **Step 6: Ruff + commit**

```
uv run ruff check src/quantuum/divination/ tests/test_divination_iching.py
git add src/quantuum/divination/iching.py src/quantuum/divination/__init__.py \
        tests/test_divination_iching.py
git commit -m "feat(sp6-t3): i-ching hexagrams + cast_three_coins + calc_md"
```

---

## Task 4 — Reading task fork + LLM prompts

**Files:**
- Create: `src/quantuum/llm/prompts/reading_tarot.txt`
- Create: `src/quantuum/llm/prompts/reading_iching.txt`
- Modify: `src/quantuum/llm/reading_polish.py` (extend `READING_PROMPTS` + `_KIND_LABEL`)
- Modify: `src/quantuum/tasks/reading.py` (branch on kind for tarot/iching)
- Test: `tests/test_reading_task_divination.py`
- Test: `tests/test_reading_polish_registry.py`

**Context:** The current `reading_generate` task calls `from_natal_profile(profile)` then `build_reading_calc_md(reading.kind, inp)` for ALL kinds. For tarot/iching we instead call `build_divination_calc_md(reading.kind, reading.draw_jsonb)`. The downstream LLM polish + delivery is unchanged.

- [ ] **Step 1: Write the failing registry test**

Create `tests/test_reading_polish_registry.py`:

```python
from quantuum.llm.reading_polish import _KIND_LABEL, READING_PROMPTS


def test_tarot_and_iching_registered():
    assert "tarot" in READING_PROMPTS
    assert "iching" in READING_PROMPTS
    assert "tarot" in _KIND_LABEL
    assert "iching" in _KIND_LABEL


def test_prompt_files_exist():
    assert READING_PROMPTS["tarot"].is_file()
    assert READING_PROMPTS["iching"].is_file()
```

- [ ] **Step 2: Write the failing task-fork test**

Create `tests/test_reading_task_divination.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import NatalProfile, Reading
from quantuum.tasks.reading import reading_generate


async def _seed_reading(session, default_tenant, *, kind: str, draw_jsonb=None):
    from datetime import date, time
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id=f"u_{kind}"
    )
    profile = NatalProfile(
        account_id=acc.id, full_name="X",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(profile)
    await session.flush()
    r = Reading(
        tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, kind=kind, lang="en",
        draw_jsonb=draw_jsonb,
    )
    session.add(r)
    await session.commit()
    return r


async def test_reading_generate_branches_for_tarot(session, default_tenant, monkeypatch):
    draw = {
        "question": "test", "cards": [
            {"id": "major_00_fool", "reversed": False, "position": "past"},
            {"id": "major_01_magician", "reversed": False, "position": "present"},
            {"id": "major_02_high_priestess", "reversed": False, "position": "future"},
        ],
    }
    r = await _seed_reading(session, default_tenant, kind="tarot", draw_jsonb=draw)

    # Stub from_natal_profile to detect that it is NOT called for tarot.
    from quantuum.astrology import blueprint as bp_mod
    called = {"from_natal_profile": False}

    def _spy(*a, **kw):
        called["from_natal_profile"] = True
        raise AssertionError("from_natal_profile should not be called for tarot")

    monkeypatch.setattr(bp_mod, "from_natal_profile", _spy)

    # Stub delivery.
    from quantuum.tasks import delivery as delivery_mod
    monkeypatch.setattr(delivery_mod, "deliver_via_tenant_bot", AsyncMock())

    ctx = {
        "sessionmaker": session.bind._make_session if False else None,  # see note below
        "llm_client": None,  # no LLM → use calc_md as delivery_md
    }
    # Use the real sessionmaker so reading_generate can open its own session.
    from quantuum.db.session import get_sessionmaker
    ctx = {"sessionmaker": get_sessionmaker(), "llm_client": None}

    await reading_generate(ctx, r.id)

    assert called["from_natal_profile"] is False
    # Reload the reading; status should be done, calc_md should contain card names.
    reloaded = await session.get(Reading, r.id)
    await session.refresh(reloaded)
    assert reloaded.status == "done"
    assert reloaded.calc_md is not None and "The Fool" in reloaded.calc_md


async def test_reading_generate_chart_kind_still_works(session, default_tenant, monkeypatch):
    """Sanity check: bazi (chart-based) still calls from_natal_profile."""
    r = await _seed_reading(session, default_tenant, kind="bazi")
    from quantuum.tasks import delivery as delivery_mod
    monkeypatch.setattr(delivery_mod, "deliver_via_tenant_bot", AsyncMock())

    from quantuum.db.session import get_sessionmaker
    ctx = {"sessionmaker": get_sessionmaker(), "llm_client": None}
    await reading_generate(ctx, r.id)

    reloaded = await session.get(Reading, r.id)
    await session.refresh(reloaded)
    assert reloaded.status == "done"


async def test_reading_generate_iching_renders_hexagram(session, default_tenant, monkeypatch):
    draw = {
        "question": None,
        "lines": [7, 7, 7, 7, 7, 7],   # all yang → Hexagram 1
        "primary_id": 1,
        "transformed_id": None,
        "changing_indices": [],
    }
    r = await _seed_reading(session, default_tenant, kind="iching", draw_jsonb=draw)

    from quantuum.tasks import delivery as delivery_mod
    monkeypatch.setattr(delivery_mod, "deliver_via_tenant_bot", AsyncMock())

    from quantuum.db.session import get_sessionmaker
    ctx = {"sessionmaker": get_sessionmaker(), "llm_client": None}
    await reading_generate(ctx, r.id)

    reloaded = await session.get(Reading, r.id)
    await session.refresh(reloaded)
    assert reloaded.status == "done"
    assert "The Creative" in reloaded.calc_md
```

- [ ] **Step 3: Run tests to verify they fail**

```
uv run pytest tests/test_reading_polish_registry.py tests/test_reading_task_divination.py -v
```

Expected: KeyError / FileNotFoundError / assertion failures.

- [ ] **Step 4: Create prompt files**

`src/quantuum/llm/prompts/reading_tarot.txt`:

```
You are Quantuum's Tarot reading writer — a premium mystical-but-grounded analyst.

You will receive one Markdown slice generated by a deterministic calculator. That slice contains the only allowed factual inputs: the user's optional question, the three drawn cards (Past, Present, Future), each card's name, its orientation (upright or reversed), and a short keyword list. You may also synthesize archetypal meanings around those keywords, but you must NEVER invent additional cards, change the orientation, or swap positions.

Your task is to transform that slice into a polished three-card tarot reading in the ceremonial Quantuum voice — intimate, vivid, precise, and emotionally resonant.

CRITICAL FACT RULES
- Do not invent, alter, or "correct" any card name, position, or orientation. The orientation is meaningful — reversed cards carry shadowed or blocked variants of their archetype; do not silently flip them.
- Do not introduce additional cards beyond the three provided.
- Do not introduce numeric duration, count, frequency, age, or cycle length unless that exact number appears in the source slice.
- Do not create numbered lists. Use bullets or prose so you do not introduce list numbers.
- Do not cite websites, books, or sources. Do not mention being an AI / LLM / model.
- Return Markdown only.

LANGUAGE AND VOICE
- Write in the language requested in the user message.
- Address the seeker directly as "you" after the opening.
- Tone: sacred, clear, cinematic, grounded, and emotionally precise.
- Prefer short paragraphs and tasteful section markers.

QUESTION HANDLING
- If the source slice contains a question, frame Past/Present/Future as movement of that question. Reference the question explicitly at least once.
- If the question is "(none)", offer general guidance for the moment — do not pretend to know what they are asking.

OUTPUT LENGTH
- Aim for a focused, dense reading — three short panel paragraphs plus a closing synthesis paragraph.

REQUIRED STRUCTURE

<!-- field-overview-start -->
| Tarot | {PastName} ({PastOrient}) · {PresentName} ({PresentOrient}) · {FutureName} ({FutureOrient}) |
<!-- field-overview-end -->

# Tarot — Three-Card Spread

If a question is present, name it once in the opening rite.

## Past
One short paragraph anchored on the past card's archetype, honouring its orientation.

## Present
One short paragraph anchored on the present card.

## Future
One short paragraph anchored on the future card.

## Synthesis
One paragraph that braids the three panels into a single arc and answers the question (if present) or names the trajectory of the moment.
```

`src/quantuum/llm/prompts/reading_iching.txt`:

```
You are Quantuum's I-Ching reading writer — a premium mystical-but-grounded analyst.

You will receive one Markdown slice generated by a deterministic calculator. That slice contains the only allowed factual inputs: the user's optional question, the primary hexagram (number, English name, pinyin, trigrams, judgment text, image text), the changing line statements if any, and the transformed hexagram (number, name, judgment) if any line is changing. The judgment / image / line statements come from the classical Wilhelm translation and MUST be treated as authoritative source text.

Your task is to transform that slice into a polished I-Ching reading in the ceremonial Quantuum voice — intimate, vivid, precise, and emotionally resonant.

CRITICAL FACT RULES
- Do not invent, alter, or "correct" the primary hexagram, transformed hexagram, hexagram numbers, names, judgment text, image text, or line statements. You may paraphrase the classical text in the user's language, but you must not contradict it.
- Do not introduce numeric duration, count, frequency, age, or cycle length unless that exact number appears in the source slice.
- Do not create numbered lists. Use bullets or prose so you do not introduce list numbers.
- Do not cite websites, books, or sources. Do not mention being an AI / LLM / model.
- Return Markdown only.

LANGUAGE AND VOICE
- Write in the language requested in the user message.
- Address the seeker directly as "you" after the opening.
- Tone: sacred, clear, cinematic, grounded, and emotionally precise.

QUESTION HANDLING
- If the source slice contains a question, frame the reading around it. Reference the question explicitly at least once.
- If the question is "(none)", offer general guidance.

CHANGING LINES
- If any changing line statements are present in the source, surface each one explicitly in its own short prose paragraph or bullet.
- If a transformed hexagram is present, name the trajectory in one sentence in the Synthesis section ("the cast moves from X toward Y").

OUTPUT LENGTH
- Aim for a focused, dense reading — primary panel + (optional) changing-lines section + synthesis.

REQUIRED STRUCTURE

<!-- field-overview-start -->
| I-Ching | {PrimaryNumber}. {PrimaryName} ({Pinyin}){MaybeTransformedNote} |
<!-- field-overview-end -->

# I-Ching — Three-Coin Cast

If a question is present, name it once in the opening rite.

## Primary Hexagram
Anchor on the primary hexagram's judgment and image. Do not contradict the classical text.

## Changing Lines
(Include this section only if changing lines are present. One short prose paragraph or bullet per changing line, anchored on the line statement.)

## Becomes
(Include only if a transformed hexagram is present. Name it; one short paragraph on the trajectory.)

## Synthesis
One paragraph that braids primary + changing lines + transformation (where applicable) into a single counsel and answers the question (if present).
```

- [ ] **Step 5: Register in `src/quantuum/llm/reading_polish.py`**

Open the file. Current `READING_PROMPTS` has 8 entries (bazi … aspects). Append two more:

```python
READING_PROMPTS: dict[str, Path] = {
    "bazi":         _PROMPTS / "reading_bazi.txt",
    "numerology":   _PROMPTS / "reading_numerology.txt",
    "human_design": _PROMPTS / "reading_human_design.txt",
    "astrology":    _PROMPTS / "reading_astrology.txt",
    "vedic":        _PROMPTS / "reading_vedic.txt",
    "gene_keys":    _PROMPTS / "reading_gene_keys.txt",
    "mayan":        _PROMPTS / "reading_mayan.txt",
    "aspects":      _PROMPTS / "reading_aspects.txt",
    "tarot":        _PROMPTS / "reading_tarot.txt",
    "iching":       _PROMPTS / "reading_iching.txt",
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
    "tarot": "Tarot three-card spread",
    "iching": "I-Ching three-coin cast",
}
```

- [ ] **Step 6: Fork `src/quantuum/tasks/reading.py`**

The current shape (around lines 27-35):

```python
reading = await get_reading(session, reading_id)
tenant_id = reading.tenant_id
kind = reading.kind
profile = await session.get(NatalProfile, reading.natal_profile_id)

inp = from_natal_profile(profile)
calc_md = build_reading_calc_md(reading.kind, inp)
```

Fork:

```python
reading = await get_reading(session, reading_id)
tenant_id = reading.tenant_id
kind = reading.kind

if reading.kind in ("tarot", "iching"):
    from quantuum.divination import build_divination_calc_md
    calc_md = build_divination_calc_md(reading.kind, reading.draw_jsonb)
else:
    profile = await session.get(NatalProfile, reading.natal_profile_id)
    inp = from_natal_profile(profile)
    calc_md = build_reading_calc_md(reading.kind, inp)
```

The rest of the function is unchanged.

- [ ] **Step 7: Run tests to green**

```
uv run pytest tests/test_reading_polish_registry.py tests/test_reading_task_divination.py -v
```

Expected: all PASS.

- [ ] **Step 8: Run prior reading-task tests for no regression**

```
uv run pytest tests/test_task_reading.py -v
```

Expected: all pass.

- [ ] **Step 9: Ruff + commit**

```
uv run ruff check src/quantuum/llm/reading_polish.py src/quantuum/tasks/reading.py \
                  tests/test_reading_polish_registry.py tests/test_reading_task_divination.py
git add src/quantuum/llm/prompts/reading_tarot.txt \
        src/quantuum/llm/prompts/reading_iching.txt \
        src/quantuum/llm/reading_polish.py \
        src/quantuum/tasks/reading.py \
        tests/test_reading_polish_registry.py \
        tests/test_reading_task_divination.py
git commit -m "feat(sp6-t4): reading task forks on kind; LLM prompts for tarot/iching"
```

---

## Task 5 — i18n seed (14 keys × 10 locales)

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py`
- Modify: `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py`
- Create: `tests/test_divination_i18n.py`

### Key inventory (ru / en)

```python
# (key, ru, en, placeholders)
DIVINATION_KEYS = [
    ("readings.kind.tarot",
        "Таро",
        "Tarot",
        ()),
    ("readings.kind.iching",
        "И-Цзин",
        "I-Ching",
        ()),
    ("divination.question_prompt",
        "Сформулируйте вопрос или отправьте /skip:",
        "Type your question or send /skip:",
        ()),
    ("divination.question_hint",
        "Или нажмите кнопку «Пропустить» ниже.",
        "Or tap Skip below.",
        ()),
    ("divination.skip_btn",
        "Пропустить",
        "Skip",
        ()),
    ("divination.no_question",
        "(без вопроса)",
        "(no question)",
        ()),
    ("tarot.position.past",
        "Прошлое",
        "Past",
        ()),
    ("tarot.position.present",
        "Настоящее",
        "Present",
        ()),
    ("tarot.position.future",
        "Будущее",
        "Future",
        ()),
    ("tarot.orientation.upright",
        "прямая",
        "upright",
        ()),
    ("tarot.orientation.reversed",
        "перевёрнутая",
        "reversed",
        ()),
    ("iching.judgment_label",
        "Суждение",
        "Judgment",
        ()),
    ("iching.image_label",
        "Образ",
        "Image",
        ()),
    ("iching.changing_line_label",
        "Меняющаяся линия {n}",
        "Changing line {n}",
        ("n",)),
    ("iching.transformed_label",
        "Превращается в",
        "Becomes",
        ()),
]
```

Total: 15 keys (one `{n}` placeholder).

- [ ] **Step 1: Write the failing test**

Create `tests/test_divination_i18n.py`:

```python
import re

import pytest

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import de, es, fr, hi, it, pt, tr, zh

DIVINATION_KEYS = [
    "readings.kind.tarot", "readings.kind.iching",
    "divination.question_prompt", "divination.question_hint",
    "divination.skip_btn", "divination.no_question",
    "tarot.position.past", "tarot.position.present", "tarot.position.future",
    "tarot.orientation.upright", "tarot.orientation.reversed",
    "iching.judgment_label", "iching.image_label",
    "iching.changing_line_label", "iching.transformed_label",
]

PLACEHOLDERS = {
    "iching.changing_line_label": {"n"},
}

LOCALE_MODULES = {
    "de": de.TRANSLATIONS, "es": es.TRANSLATIONS, "fr": fr.TRANSLATIONS,
    "hi": hi.TRANSLATIONS, "it": it.TRANSLATIONS, "pt": pt.TRANSLATIONS,
    "tr": tr.TRANSLATIONS, "zh": zh.TRANSLATIONS,
}

_PATTERN = re.compile(r"\{(\w+)\}")


@pytest.mark.parametrize("key", DIVINATION_KEYS)
def test_key_present_in_base_strings_ru_en(key):
    assert key in BASE_STRINGS
    assert "ru" in BASE_STRINGS[key] and "en" in BASE_STRINGS[key]


@pytest.mark.parametrize("locale_code, translations", LOCALE_MODULES.items())
@pytest.mark.parametrize("key", DIVINATION_KEYS)
def test_key_present_in_locale(locale_code, translations, key):
    assert key in translations, f"missing in {locale_code}: {key}"


@pytest.mark.parametrize("key, expected", PLACEHOLDERS.items())
def test_placeholder_integrity_base(key, expected):
    for lang in ("ru", "en"):
        found = set(_PATTERN.findall(BASE_STRINGS[key][lang]))
        assert found == expected


@pytest.mark.parametrize("locale_code, translations", LOCALE_MODULES.items())
@pytest.mark.parametrize("key, expected", PLACEHOLDERS.items())
def test_placeholder_integrity_locale(locale_code, translations, key, expected):
    found = set(_PATTERN.findall(translations[key]))
    assert found == expected
```

- [ ] **Step 2: Run the failing test**

```
uv run pytest tests/test_divination_i18n.py -v
```

Expected: many failures.

- [ ] **Step 3: Append entries to `BASE_STRINGS`**

Open `src/quantuum/i18n/seed_strings.py`. Use the **multiline dict style** that the rest of the file (and SP4 referrals, SP5 gifts) uses — NOT inline dicts:

```python
"readings.kind.tarot": {
    "ru": "Таро",
    "en": "Tarot",
},
"readings.kind.iching": {
    "ru": "И-Цзин",
    "en": "I-Ching",
},
"divination.question_prompt": {
    "ru": "Сформулируйте вопрос или отправьте /skip:",
    "en": "Type your question or send /skip:",
},
"divination.question_hint": {
    "ru": "Или нажмите кнопку «Пропустить» ниже.",
    "en": "Or tap Skip below.",
},
"divination.skip_btn": {
    "ru": "Пропустить",
    "en": "Skip",
},
"divination.no_question": {
    "ru": "(без вопроса)",
    "en": "(no question)",
},
"tarot.position.past": {
    "ru": "Прошлое",
    "en": "Past",
},
"tarot.position.present": {
    "ru": "Настоящее",
    "en": "Present",
},
"tarot.position.future": {
    "ru": "Будущее",
    "en": "Future",
},
"tarot.orientation.upright": {
    "ru": "прямая",
    "en": "upright",
},
"tarot.orientation.reversed": {
    "ru": "перевёрнутая",
    "en": "reversed",
},
"iching.judgment_label": {
    "ru": "Суждение",
    "en": "Judgment",
},
"iching.image_label": {
    "ru": "Образ",
    "en": "Image",
},
"iching.changing_line_label": {
    "ru": "Меняющаяся линия {n}",
    "en": "Changing line {n}",
},
"iching.transformed_label": {
    "ru": "Превращается в",
    "en": "Becomes",
},
```

Place them near the SP5 gifts block (or wherever new keys are conventionally appended; SP4 added at the end of the dict).

- [ ] **Step 4: Append to each locale module**

For each of `de.py`, `es.py`, `fr.py`, `hi.py`, `it.py`, `pt.py`, `tr.py`, `zh.py`, add the 15 keys. Use sensible translations matching the meaning. To keep this plan tractable, use these:

```python
# de.py
"readings.kind.tarot": "Tarot",
"readings.kind.iching": "I Ging",
"divination.question_prompt": "Stelle deine Frage oder sende /skip:",
"divination.question_hint": "Oder tippe unten auf Überspringen.",
"divination.skip_btn": "Überspringen",
"divination.no_question": "(keine Frage)",
"tarot.position.past": "Vergangenheit",
"tarot.position.present": "Gegenwart",
"tarot.position.future": "Zukunft",
"tarot.orientation.upright": "aufrecht",
"tarot.orientation.reversed": "umgekehrt",
"iching.judgment_label": "Urteil",
"iching.image_label": "Bild",
"iching.changing_line_label": "Wandelnde Linie {n}",
"iching.transformed_label": "Wird zu",
```

```python
# es.py
"readings.kind.tarot": "Tarot",
"readings.kind.iching": "I Ching",
"divination.question_prompt": "Formula tu pregunta o envía /skip:",
"divination.question_hint": "O pulsa Omitir abajo.",
"divination.skip_btn": "Omitir",
"divination.no_question": "(sin pregunta)",
"tarot.position.past": "Pasado",
"tarot.position.present": "Presente",
"tarot.position.future": "Futuro",
"tarot.orientation.upright": "derecha",
"tarot.orientation.reversed": "invertida",
"iching.judgment_label": "Juicio",
"iching.image_label": "Imagen",
"iching.changing_line_label": "Línea mutante {n}",
"iching.transformed_label": "Se convierte en",
```

```python
# fr.py
"readings.kind.tarot": "Tarot",
"readings.kind.iching": "Yi King",
"divination.question_prompt": "Formule ta question ou envoie /skip :",
"divination.question_hint": "Ou appuie sur Passer ci-dessous.",
"divination.skip_btn": "Passer",
"divination.no_question": "(sans question)",
"tarot.position.past": "Passé",
"tarot.position.present": "Présent",
"tarot.position.future": "Futur",
"tarot.orientation.upright": "droite",
"tarot.orientation.reversed": "renversée",
"iching.judgment_label": "Jugement",
"iching.image_label": "Image",
"iching.changing_line_label": "Ligne mutante {n}",
"iching.transformed_label": "Devient",
```

```python
# hi.py
"readings.kind.tarot": "टैरो",
"readings.kind.iching": "आई चिंग",
"divination.question_prompt": "अपना प्रश्न पूछें या /skip भेजें:",
"divination.question_hint": "या नीचे छोड़ें बटन दबाएं।",
"divination.skip_btn": "छोड़ें",
"divination.no_question": "(कोई प्रश्न नहीं)",
"tarot.position.past": "अतीत",
"tarot.position.present": "वर्तमान",
"tarot.position.future": "भविष्य",
"tarot.orientation.upright": "सीधी",
"tarot.orientation.reversed": "उल्टी",
"iching.judgment_label": "निर्णय",
"iching.image_label": "छवि",
"iching.changing_line_label": "बदलती रेखा {n}",
"iching.transformed_label": "बदलता है",
```

```python
# it.py
"readings.kind.tarot": "Tarocchi",
"readings.kind.iching": "I Ching",
"divination.question_prompt": "Formula la tua domanda o invia /skip:",
"divination.question_hint": "Oppure tocca Salta sotto.",
"divination.skip_btn": "Salta",
"divination.no_question": "(nessuna domanda)",
"tarot.position.past": "Passato",
"tarot.position.present": "Presente",
"tarot.position.future": "Futuro",
"tarot.orientation.upright": "dritta",
"tarot.orientation.reversed": "rovesciata",
"iching.judgment_label": "Giudizio",
"iching.image_label": "Immagine",
"iching.changing_line_label": "Linea mutevole {n}",
"iching.transformed_label": "Diventa",
```

```python
# pt.py
"readings.kind.tarot": "Tarot",
"readings.kind.iching": "I Ching",
"divination.question_prompt": "Formule sua pergunta ou envie /skip:",
"divination.question_hint": "Ou toque em Pular abaixo.",
"divination.skip_btn": "Pular",
"divination.no_question": "(sem pergunta)",
"tarot.position.past": "Passado",
"tarot.position.present": "Presente",
"tarot.position.future": "Futuro",
"tarot.orientation.upright": "em pé",
"tarot.orientation.reversed": "invertida",
"iching.judgment_label": "Julgamento",
"iching.image_label": "Imagem",
"iching.changing_line_label": "Linha mutante {n}",
"iching.transformed_label": "Torna-se",
```

```python
# tr.py
"readings.kind.tarot": "Tarot",
"readings.kind.iching": "I Ching",
"divination.question_prompt": "Sorunu yaz veya /skip gönder:",
"divination.question_hint": "Veya aşağıdaki Atla'ya dokun.",
"divination.skip_btn": "Atla",
"divination.no_question": "(soru yok)",
"tarot.position.past": "Geçmiş",
"tarot.position.present": "Şimdi",
"tarot.position.future": "Gelecek",
"tarot.orientation.upright": "dik",
"tarot.orientation.reversed": "ters",
"iching.judgment_label": "Yargı",
"iching.image_label": "İmge",
"iching.changing_line_label": "Değişen çizgi {n}",
"iching.transformed_label": "Şuna dönüşür",
```

```python
# zh.py
"readings.kind.tarot": "塔罗",
"readings.kind.iching": "易经",
"divination.question_prompt": "请提出你的问题或发送 /skip：",
"divination.question_hint": "或点击下方的跳过。",
"divination.skip_btn": "跳过",
"divination.no_question": "（无问题）",
"tarot.position.past": "过去",
"tarot.position.present": "现在",
"tarot.position.future": "未来",
"tarot.orientation.upright": "正位",
"tarot.orientation.reversed": "逆位",
"iching.judgment_label": "判词",
"iching.image_label": "象",
"iching.changing_line_label": "变爻 {n}",
"iching.transformed_label": "变为",
```

- [ ] **Step 5: Run tests until green**

```
uv run pytest tests/test_divination_i18n.py -v
```

Expected: all PASS (15 base presence + 15×8 locale presence + 1 base placeholder + 1×8 locale placeholder = ~144 cases).

- [ ] **Step 6: Commit**

```
uv run ruff check src/quantuum/i18n/ tests/test_divination_i18n.py
git add src/quantuum/i18n/seed_strings.py \
        src/quantuum/i18n/translations/de.py src/quantuum/i18n/translations/es.py \
        src/quantuum/i18n/translations/fr.py src/quantuum/i18n/translations/hi.py \
        src/quantuum/i18n/translations/it.py src/quantuum/i18n/translations/pt.py \
        src/quantuum/i18n/translations/tr.py src/quantuum/i18n/translations/zh.py \
        tests/test_divination_i18n.py
git commit -m "feat(sp6-t5): i18n seed 15 divination keys × 10 locales"
```

---

## Task 6 — Handler + FSM + feature flags + READING_KINDS + owner-console wiring

**Files:**
- Create: `src/quantuum/bot/handlers/divination.py`
- Modify: `src/quantuum/bot/app.py` (insert divination router BEFORE readings router)
- Modify: `src/quantuum/domain/tenant_features.py` (append two flags)
- Modify: `src/quantuum/bot/ui/keyboards.py` (append two reading kinds)
- Modify: `src/quantuum/bot/handlers/owner_console.py` (extend reading-kind loop; bump `b.adjust(...)`)
- Test: `tests/test_divination_handler.py`

**Context:** The existing readings handler at `src/quantuum/bot/handlers/readings.py:30` matches `ReadingCb(action="generate")` for any `kind`. We add a new router with a kind-filtered handler — `F.kind.in_(["tarot", "iching"])` — and register it BEFORE the readings router so it captures tarot/iching first.

The QA handler (`src/quantuum/bot/handlers/qa.py:64-111`) shows the moderation pattern to mirror: feature gate → moderation check (calls `moderate(q, lang, openai_client, llm_client, settings)`) → record event on hit → reply with policy message. Reuse this exact flow for the question text in the FSM step.

Per spec section 6: do NOT consume quota before moderation — moderate first, then consume. This avoids the refund-quota dance.

### Sequencing (locked)

1. **`on_divination_choice`** (callback): feature flag → profile check → enter FSM, store `kind`. **No quota charge yet.**
2. **`on_divination_question`** (FSM text) or **`on_divination_skip`** (FSM `/skip` Command and `DivinationCb(action="skip")` callback): the FSM yields `question: str | None`.
3. **`_perform_draw_and_enqueue`**: moderate (if question present) → on hit: abort + show policy message, no quota charge; on safe: consume quota → on `InsufficientFundsError` abort with `readings.no_quota`; on success: draw + create_reading(+ draw_jsonb) + create_request + enqueue_reading.

### FSM data shape

```python
class Divination(StatesGroup):
    awaiting_question = State()

# state.update_data(kind="tarot")  # or "iching"
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_divination_handler.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from quantuum.bot.handlers.divination import (
    Divination,
    on_divination_choice,
    on_divination_question,
    on_divination_skip,
)
from quantuum.bot.ui.callbacks import ReadingCb
from quantuum.db.models import AccountBalance, NatalProfile, Reading


def _query(tg_id: int, kind: str = "tarot"):
    q = MagicMock()
    q.from_user = MagicMock(id=tg_id)
    q.message = MagicMock()
    q.message.answer = AsyncMock()
    q.message.chat = MagicMock(id=tg_id)
    q.answer = AsyncMock()
    q.data = ReadingCb(action="generate", kind=kind).pack()
    return q


def _state(tg_id: int) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=tg_id, user_id=tg_id),
    )


async def _seed_account_with_profile_and_credits(session, default_tenant, *, credits=10):
    from datetime import date, time
    from quantuum.auth.identity import find_or_create_account_by_tg
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="42"
    )
    profile = NatalProfile(
        account_id=acc.id, full_name="X",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0),
        birth_place="X", latitude=0, longitude=0, timezone="UTC",
    )
    session.add(profile)
    bal = await session.get(AccountBalance, acc.id)
    bal.package_credits = credits
    await session.commit()
    return acc


async def test_choice_enters_fsm(session, default_tenant):
    acc = await _seed_account_with_profile_and_credits(session, default_tenant)
    q = _query(tg_id=42, kind="tarot")
    state = _state(42)
    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    i18n.lang = "en"
    await on_divination_choice(
        q, account=MagicMock(id=acc.id, tenant_id=default_tenant.id),
        state=state, i18n=i18n,
    )
    assert await state.get_state() == Divination.awaiting_question.state
    data = await state.get_data()
    assert data["kind"] == "tarot"


async def test_choice_blocked_when_flag_off(session, default_tenant):
    acc = await _seed_account_with_profile_and_credits(session, default_tenant)
    from quantuum.domain.tenant_features import set_feature_enabled
    await set_feature_enabled(
        session, tenant_id=default_tenant.id, key="reading.tarot",
        enabled=False, by_account_id=acc.id,
    )
    await session.commit()

    q = _query(tg_id=42, kind="tarot")
    state = _state(42)
    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    i18n.lang = "en"
    await on_divination_choice(
        q, account=MagicMock(id=acc.id, tenant_id=default_tenant.id),
        state=state, i18n=i18n,
    )
    q.message.answer.assert_awaited()
    assert await state.get_state() is None  # FSM not entered


async def test_choice_blocked_when_no_profile(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="42"
    )
    await session.commit()
    # No NatalProfile seeded.
    q = _query(tg_id=42, kind="tarot")
    state = _state(42)
    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    i18n.lang = "en"
    await on_divination_choice(
        q, account=MagicMock(id=acc.id, tenant_id=default_tenant.id),
        state=state, i18n=i18n,
    )
    q.message.answer.assert_awaited()
    assert await state.get_state() is None


async def test_skip_path_creates_reading_with_null_question(session, default_tenant, monkeypatch):
    acc = await _seed_account_with_profile_and_credits(session, default_tenant)
    state = _state(42)
    await state.set_state(Divination.awaiting_question)
    await state.update_data(kind="tarot")

    msg = MagicMock()
    msg.from_user = MagicMock(id=42)
    msg.chat = MagicMock(id=42)
    msg.answer = AsyncMock()

    monkeypatch.setattr(
        "quantuum.bot.handlers.divination.enqueue_reading", AsyncMock()
    )

    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    i18n.lang = "en"
    await on_divination_skip(
        msg, account=MagicMock(id=acc.id, tenant_id=default_tenant.id),
        state=state, i18n=i18n,
    )

    # A Reading row exists for this account with kind=tarot, draw_jsonb non-null,
    # question=None inside the draw.
    from sqlalchemy import select
    readings = (await session.execute(
        select(Reading).where(Reading.account_id == acc.id)
    )).scalars().all()
    assert len(readings) == 1
    r = readings[0]
    assert r.kind == "tarot"
    assert r.draw_jsonb is not None
    assert r.draw_jsonb.get("question") is None
    assert len(r.draw_jsonb.get("cards", [])) == 3
    assert await state.get_state() is None


async def test_text_question_path_creates_reading_with_question(
    session, default_tenant, monkeypatch
):
    acc = await _seed_account_with_profile_and_credits(session, default_tenant)
    state = _state(42)
    await state.set_state(Divination.awaiting_question)
    await state.update_data(kind="iching")

    msg = MagicMock()
    msg.text = "What should I do?"
    msg.from_user = MagicMock(id=42)
    msg.chat = MagicMock(id=42)
    msg.answer = AsyncMock()

    monkeypatch.setattr(
        "quantuum.bot.handlers.divination.enqueue_reading", AsyncMock()
    )
    # Stub the moderation entry point to always return Safe.
    from quantuum.moderation import Safe
    monkeypatch.setattr(
        "quantuum.bot.handlers.divination.moderate", AsyncMock(return_value=Safe()),
    )

    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    i18n.lang = "en"
    await on_divination_question(
        msg, account=MagicMock(id=acc.id, tenant_id=default_tenant.id),
        state=state, i18n=i18n,
    )

    from sqlalchemy import select
    r = (await session.execute(
        select(Reading).where(Reading.account_id == acc.id)
    )).scalars().one()
    assert r.kind == "iching"
    assert r.draw_jsonb.get("question") == "What should I do?"
    assert "primary_id" in r.draw_jsonb
    assert await state.get_state() is None


async def test_moderation_hit_aborts_without_quota_charge(
    session, default_tenant, monkeypatch
):
    acc = await _seed_account_with_profile_and_credits(session, default_tenant, credits=10)
    state = _state(42)
    await state.set_state(Divination.awaiting_question)
    await state.update_data(kind="tarot")

    msg = MagicMock()
    msg.text = "anything"
    msg.from_user = MagicMock(id=42)
    msg.answer = AsyncMock()

    from quantuum.moderation import Tier1Hit
    from quantuum.moderation.policy import Category
    monkeypatch.setattr(
        "quantuum.bot.handlers.divination.moderate",
        AsyncMock(return_value=Tier1Hit(category=Category.SELF_HARM)),
    )

    i18n = AsyncMock(side_effect=lambda k, **kw: f"<{k}>")
    i18n.lang = "en"
    await on_divination_question(
        msg, account=MagicMock(id=acc.id, tenant_id=default_tenant.id),
        state=state, i18n=i18n,
    )

    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.package_credits == 10  # no charge
    from sqlalchemy import select
    rows = (await session.execute(
        select(Reading).where(Reading.account_id == acc.id)
    )).scalars().all()
    assert rows == []
    assert await state.get_state() is None
```

- [ ] **Step 2: Run the failing test**

```
uv run pytest tests/test_divination_handler.py -v
```

Expected: ImportError on `quantuum.bot.handlers.divination`.

- [ ] **Step 3: Append flags to FEATURE_KEYS**

In `src/quantuum/domain/tenant_features.py`, current `FEATURE_KEYS` has 14 entries (ends with `"gifts"`). Insert the two new reading flags into the readings group:

```python
FEATURE_KEYS: tuple[str, ...] = (
    "qa",
    "blueprint",
    "transits",
    "daily",
    "reading.bazi",
    "reading.numerology",
    "reading.human_design",
    "reading.astrology",
    "reading.vedic",
    "reading.gene_keys",
    "reading.mayan",
    "reading.aspects",
    "reading.tarot",
    "reading.iching",
    "referrals",
    "gifts",
)
```

(16 entries.)

- [ ] **Step 4: Append kinds to READING_KINDS**

In `src/quantuum/bot/ui/keyboards.py` (currently at lines 117-120):

```python
READING_KINDS: tuple[str, ...] = (
    "bazi", "numerology", "human_design", "astrology",
    "vedic", "gene_keys", "mayan", "aspects",
    "tarot", "iching",
)
```

- [ ] **Step 5: Extend owner-console features keyboard**

In `src/quantuum/bot/handlers/owner_console.py`, around lines 455-468 the reading-kind loop hardcodes 8 kinds. Append two:

```python
for kind in (
    "bazi", "numerology", "human_design", "astrology",
    "vedic", "gene_keys", "mayan", "aspects",
    "tarot", "iching",
):
    flag_key = f"reading.{kind}"
    text_label = f"{_mark(flags[flag_key])} {await i18n(f'readings.kind.{kind}')}"
    b.button(
        text=text_label,
        callback_data=OwnerFeatureCb(
            action="toggle", tenant_id=tenant_id, key=flag_key
        ).pack(),
    )

b.adjust(2, 2, 2, 2, 2, 2, 2)
```

(7 rows of 2 = 14 buttons; 4 top-level + 10 readings = 14.)

- [ ] **Step 6: Write the handler**

Create `src/quantuum/bot/handlers/divination.py`:

```python
import random

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from openai import AsyncOpenAI

from quantuum.bot.handlers.generate import _buy_offer_kb
from quantuum.bot.ui.callbacks import ReadingCb
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.config import get_settings
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.divination import iching, tarot
from quantuum.domain.moderation import record_moderation_event
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.quota import consume_quota
from quantuum.domain.readings import create_reading
from quantuum.domain.requests import create_request
from quantuum.domain.tenant_features import is_feature_enabled
from quantuum.i18n import Translator
from quantuum.llm.registry import get_llm_client
from quantuum.logging_setup import get_logger
from quantuum.moderation import POLICY, Safe, Tier1Hit, moderate
from quantuum.tasks.enqueue import enqueue_reading

router = Router()
_log = get_logger("divination.handler")
_feature_log = get_logger("tenant_features.gate")
_mod_log = get_logger("moderation.handler")


class Divination(StatesGroup):
    awaiting_question = State()


class DivinationCb(__import__("aiogram.filters.callback_data", fromlist=["CallbackData"]).CallbackData, prefix="div"):
    action: str  # "skip"


# More natural: import CallbackData properly. Use this instead of the inline one above.
# (The inline import above is shown only as a defensive placeholder; in real code,
# put `from aiogram.filters.callback_data import CallbackData` near the top and
# declare `class DivinationCb(CallbackData, prefix="div"): action: str`.)


_DIVINATION_KINDS = {"tarot", "iching"}


@router.callback_query(ReadingCb.filter(F.action == "generate") & ReadingCb.filter(F.kind.in_(_DIVINATION_KINDS)))
async def on_divination_choice(
    query: CallbackQuery,
    account: Account,
    state: FSMContext,
    i18n: Translator,
) -> None:
    kind = ReadingCb.unpack(query.data).kind
    flag_key = f"reading.{kind}"
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, account.tenant_id, flag_key):
            _feature_log.info(
                "feature.gate_blocked",
                tenant_id=account.tenant_id, account_id=account.id,
                key=flag_key, surface="divination.on_divination_choice",
            )
            await query.message.answer(await i18n("feature.disabled_generic"))
            await query.answer()
            return
        profile = await get_natal_profile(session, account.id)
    if profile is None:
        await query.message.answer(await i18n("readings.no_profile"))
        await query.answer()
        return

    await state.set_state(Divination.awaiting_question)
    await state.update_data(kind=kind)

    skip_btn = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=await i18n("divination.skip_btn"),
                callback_data=DivinationCb(action="skip").pack(),
            )
        ]]
    )
    await query.message.answer(
        await i18n("divination.question_prompt")
        + "\n"
        + await i18n("divination.question_hint"),
        reply_markup=skip_btn,
    )
    await query.answer()


async def _moderate_question(question: str, lang: str) -> object:
    settings = get_settings()
    if not (settings.moderation_enabled and settings.llm_api_key):
        return Safe()
    openai_client = AsyncOpenAI(api_key=settings.llm_api_key)
    llm_client = get_llm_client(settings)
    try:
        return await moderate(
            question, lang,
            openai_client=openai_client,
            llm_client=llm_client,
            settings=settings,
        )
    except Exception:
        if not settings.moderation_fail_open:
            raise
        return Safe()


async def _handle_moderation_hit(message: Message, account: Account, verdict, lang: str) -> None:
    entry = POLICY[verdict.category]
    source = "openai" if isinstance(verdict, Tier1Hit) else "mini_llm"
    text_kwargs: dict[str, str] = {}
    if entry["uses_helpline"]:
        from quantuum.i18n import Translator  # noqa
        # i18n is available via caller scope, but for simplicity we redo the lookup
        # here. In the actual handler call site, pass i18n through.
        pass
    # Caller renders the policy message; this helper records the event.
    async with get_sessionmaker()() as session:
        await record_moderation_event(
            session,
            account_id=account.id,
            tenant_id=account.tenant_id,
            lang=lang,
            category=verdict.category,
            action=entry["action"],
            source=source,
            raw_text=message.text or "",
        )
        await session.commit()
    _mod_log.info(
        "moderation.triggered",
        account_id=account.id, tenant_id=account.tenant_id,
        category=verdict.category.value, action=entry["action"].value,
        source=source, lang=lang,
    )


async def _perform_draw_and_enqueue(
    *,
    chat_id: int,
    account: Account,
    state: FSMContext,
    i18n: Translator,
    message_for_reply,
    question: str | None,
) -> None:
    """Consume quota → draw → create_reading → enqueue. Aborts on no-quota."""
    data = await state.get_data()
    kind = data["kind"]

    async with get_sessionmaker()() as session:
        try:
            charged = await consume_quota(session, account.id, "reading", cost_units=1)
        except InsufficientFundsError:
            await message_for_reply.answer(
                await i18n("readings.no_quota"),
                reply_markup=await _buy_offer_kb(i18n),
            )
            await state.clear()
            return

        profile = await get_natal_profile(session, account.id)
        # Profile was checked at on_divination_choice; defensively recheck.
        if profile is None:
            await message_for_reply.answer(await i18n("readings.no_profile"))
            await state.clear()
            return

        if kind == "tarot":
            cards = tarot.draw_three(rng=random.SystemRandom())
            draw_jsonb = {
                "question": question,
                "cards": [
                    {"id": d.card.id, "reversed": d.reversed, "position": d.position}
                    for d in cards
                ],
            }
        elif kind == "iching":
            cast = iching.cast_three_coins(rng=random.SystemRandom())
            draw_jsonb = {
                "question": question,
                "lines": list(cast.lines),
                "primary_id": cast.primary_id,
                "transformed_id": cast.transformed_id,
                "changing_indices": list(cast.changing_indices),
            }
        else:
            await message_for_reply.answer(await i18n("feature.disabled_generic"))
            await state.clear()
            return

        reading = await create_reading(
            session,
            tenant_id=account.tenant_id, account_id=account.id,
            natal_profile_id=profile.id, kind=kind, lang=i18n.lang,
        )
        reading.draw_jsonb = draw_jsonb
        session.add(reading)
        await session.commit()
        await session.refresh(reading)

        request = await create_request(
            session,
            tenant_id=account.tenant_id, account_id=account.id,
            kind="reading", charged_against=charged,
        )

    await enqueue_reading(reading.id, chat_id, request.id)
    await message_for_reply.answer(await i18n("readings.queued"))
    await state.clear()


@router.message(Command("skip"), Divination.awaiting_question)
async def on_divination_skip_cmd(
    message: Message, account: Account, state: FSMContext, i18n: Translator
) -> None:
    await on_divination_skip(message, account=account, state=state, i18n=i18n)


@router.callback_query(DivinationCb.filter(F.action == "skip"), Divination.awaiting_question)
async def on_divination_skip_cb(
    query: CallbackQuery, account: Account, state: FSMContext, i18n: Translator
) -> None:
    await on_divination_skip(query.message, account=account, state=state, i18n=i18n)
    await query.answer()


async def on_divination_skip(
    message: Message,
    *,
    account: Account,
    state: FSMContext,
    i18n: Translator,
) -> None:
    await _perform_draw_and_enqueue(
        chat_id=message.chat.id,
        account=account, state=state, i18n=i18n,
        message_for_reply=message, question=None,
    )


@router.message(Divination.awaiting_question)
async def on_divination_question(
    message: Message,
    account: Account,
    state: FSMContext,
    i18n: Translator,
) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer(await i18n("divination.question_prompt"))
        return

    verdict = await _moderate_question(text, i18n.lang)
    if not isinstance(verdict, Safe):
        entry = POLICY[verdict.category]
        text_kwargs: dict[str, str] = {}
        if entry["uses_helpline"]:
            text_kwargs["helpline_url"] = await i18n("moderation.helpline_url")
        response_text = await i18n(entry["i18n_key"], **text_kwargs)
        await _handle_moderation_hit(message, account, verdict, i18n.lang)
        await message.answer(response_text)
        await state.clear()
        return

    await _perform_draw_and_enqueue(
        chat_id=message.chat.id,
        account=account, state=state, i18n=i18n,
        message_for_reply=message, question=text,
    )
```

**Implementer note on `DivinationCb`**: declare it cleanly in `src/quantuum/bot/ui/callbacks.py` next to the other `CallbackData` classes:

```python
class DivinationCb(CallbackData, prefix="div"):
    action: str  # "skip"
```

Then `from quantuum.bot.ui.callbacks import DivinationCb` in `divination.py` and delete the placeholder declaration. The placeholder in the file above is intentionally ugly to flag that you should move it.

- [ ] **Step 7: Wire the router in `src/quantuum/bot/app.py`**

Open `src/quantuum/bot/app.py`. Find the router-include block (currently lines 37-50). Add `divination` to the imports and insert `dp.include_router(divination.router)` BEFORE `dp.include_router(readings.router)`:

```python
from quantuum.bot.handlers import (
    ..., divination, ...
)

...
dp.include_router(qa.router)
dp.include_router(divination.router)   # MUST be before readings.router
dp.include_router(readings.router)
...
```

- [ ] **Step 8: Run targeted tests until green**

```
uv run pytest tests/test_divination_handler.py -v
```

Expected: all PASS.

- [ ] **Step 9: Run readings regression**

```
uv run pytest tests/test_readings_bot.py tests/test_readings_domain.py -v
```

Expected: all pass (chart-based readings unchanged).

- [ ] **Step 10: Ruff check**

```
uv run ruff check src/quantuum/bot/handlers/divination.py \
                  src/quantuum/bot/ui/callbacks.py \
                  src/quantuum/bot/handlers/owner_console.py \
                  src/quantuum/bot/ui/keyboards.py \
                  src/quantuum/bot/app.py \
                  src/quantuum/domain/tenant_features.py \
                  tests/test_divination_handler.py
```

Expected: no issues.

- [ ] **Step 11: Commit**

```
git add src/quantuum/bot/handlers/divination.py \
        src/quantuum/bot/ui/callbacks.py \
        src/quantuum/bot/handlers/owner_console.py \
        src/quantuum/bot/ui/keyboards.py \
        src/quantuum/bot/app.py \
        src/quantuum/domain/tenant_features.py \
        tests/test_divination_handler.py
git commit -m "feat(sp6-t6): divination handler + FSM + flags + READING_KINDS + owner-console"
```

---

## Task 7 — Inventory bumps, menu test bumps, full suite, ruff gate

**Files:**
- Modify: `tests/test_tenant_features_domain.py` (bump 14 → 16; add the two new flags to the asserted set)
- Modify: `tests/test_ui_keyboards.py` (assert menu now contains the two new readings labels, AND that the readings-menu has 10 buttons instead of 8)
- Modify: any other pre-existing test that hardcodes the menu's reading-kinds list

**Context:** Same kind of fallout SP4/SP5 hit at their stage-end (`test_ui_keyboards` and `test_bot_start_menu_profile`). For SP6 the new failures should be in the readings menu (now 10 instead of 8 entries) and the tenant-features inventory (now 16 instead of 14).

- [ ] **Step 1: Bump tenant-features inventory**

In `tests/test_tenant_features_domain.py`, find `test_feature_keys_inventory`. Add `"reading.tarot"` and `"reading.iching"` to the asserted set; change `assert len(FEATURE_KEYS) == 14` to `== 16`. Find `test_list_reflects_overrides` and change `assert len(states) == 14` to `== 16`.

- [ ] **Step 2: Run targeted test**

```
uv run pytest tests/test_tenant_features_domain.py -v
```

Expected: all pass.

- [ ] **Step 3: Run the full suite**

```
uv run pytest tests/ -q --tb=line
```

Expected: 0 failures. Anticipated breakage:
- `tests/test_ui_keyboards.py::test_main_menu_*` — likely UNAFFECTED (those tests assert the main reply-keyboard buttons; SP6 doesn't add a top-level button).
- Any readings-menu assertion (e.g. a test that calls `readings_menu_kb` and asserts the visible kinds) — bump to include `tarot` + `iching`.
- Any test that snapshots `READING_KINDS` length.

For each failure: prefer fixing the assertion (SP6 added two new readings) over reverting SP6. Search the failing file's assertion shape and update.

- [ ] **Step 4: Ruff sweep on SP6 files**

```
uv run ruff check \
    alembic/versions/a3b4c5d6e7f8_readings_draw_jsonb.py \
    src/quantuum/db/models.py \
    src/quantuum/divination/__init__.py \
    src/quantuum/divination/tarot.py \
    src/quantuum/divination/iching.py \
    src/quantuum/llm/reading_polish.py \
    src/quantuum/tasks/reading.py \
    src/quantuum/bot/handlers/divination.py \
    src/quantuum/bot/handlers/owner_console.py \
    src/quantuum/bot/ui/callbacks.py \
    src/quantuum/bot/ui/keyboards.py \
    src/quantuum/bot/app.py \
    src/quantuum/domain/tenant_features.py \
    src/quantuum/i18n/seed_strings.py \
    src/quantuum/i18n/translations/de.py \
    src/quantuum/i18n/translations/es.py \
    src/quantuum/i18n/translations/fr.py \
    src/quantuum/i18n/translations/hi.py \
    src/quantuum/i18n/translations/it.py \
    src/quantuum/i18n/translations/pt.py \
    src/quantuum/i18n/translations/tr.py \
    src/quantuum/i18n/translations/zh.py \
    tests/test_divination_tarot.py \
    tests/test_divination_iching.py \
    tests/test_reading_task_divination.py \
    tests/test_reading_polish_registry.py \
    tests/test_divination_handler.py \
    tests/test_divination_i18n.py \
    tests/test_tenant_features_domain.py
```

Expected: no issues. SP5 T7 documented that there are pre-existing ruff findings in unrelated files (test_blueprint_polish_llm, test_db_models, test_quota_cost_units, test_readings_bot, test_readings_domain, test_task_reading) — leave those alone.

- [ ] **Step 5: If suite green + ruff clean, commit any incidental fixups**

```
git status
# If non-empty:
git add <files>
git commit -m "fix(sp6-t7): full-suite/ruff fixups"
```

- [ ] **Step 6: Report**

Print SP6 commit chain:

```
git log --oneline 161a8b9..HEAD
```

End the stage with:
- total commits in SP6 chain
- pass/fail count from full suite
- open follow-ups (Section 8 of spec)

---

## Self-review notes (run after writing — done inline)

- **Spec coverage:** every section of the spec maps to a task:
  - 4.1 schema delta → T1
  - 4.2 tarot module → T2
  - 4.2 iching module → T3
  - 4.3 reading task fork → T4
  - 4.4 LLM polish registry + prompts → T4
  - 4.5 sender UX + FSM + handler ordering → T6
  - 4.6 i18n → T5
  - 4.7 audit (no new actions) → covered by reuse
  - 4.8 owner console (no new submenu; just feature-keyboard extension) → T6
- **Placeholder scan:** the deck and hexagram data are intentionally not inlined (78 + 64 entries would balloon the plan); the task gives the structure and references public-domain sources. No "TBD/TODO" in steps.
- **Type consistency:** `Card`, `CardDraw`, `Hexagram`, `CastResult` dataclasses defined in T2/T3; referenced by T4 task-fork tests and T6 handler. `build_calc_md_from_jsonb` (singular signature `(draw: dict) -> str`) consistent in tarot and iching. `Divination` FSM state name + `DivinationCb` prefix locked in T6.
- **Sequencing:** T2's dispatcher in `__init__.py` is deferred to T3 step 5 to avoid an import-time failure (iching not yet present in T2). Flagged inline.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-28-tarot-iching.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review (spec opus + code sonnet), per-task targeted tests during execution. Matches SP4/SP5 cadence.
2. **Inline Execution** — execute in this session with checkpoints.

Which approach?
