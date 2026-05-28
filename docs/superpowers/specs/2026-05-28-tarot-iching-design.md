# SP6 — Tarot / I-Ching (Таро / И-Цзин)

**Status:** Draft
**Date:** 2026-05-28
**Predecessors:** SP1–SP5 (reuses existing readings pipeline, feature-flag infra, audit, i18n seed pattern, owner console).

## 1. Goal

Add two new divinatory reading kinds — `"tarot"` (three-card past/present/future spread, with reversals) and `"iching"` (three-coin cast yielding 6 lines, changing lines, primary + transformed hexagram) — that ride the existing readings pipeline (quota → request → reading → enqueue → calc → LLM polish → deliver). The user may optionally type a question that frames the LLM interpretation; `/skip` produces a generic guidance reading.

Both kinds share the same gates as the existing 8 readings: tenant feature flag, natal-profile required, quota cost 1.

## 2. Non-goals

- No additional tarot spreads (single-card, Celtic Cross) in v1 — three-card only.
- No yarrow-stalk I-Ching method — three-coin only.
- No standalone divination history surface — both kinds appear in the existing `/history` and reading list.
- No card imagery (text-only readings; deck visuals deferred).
- No replay / re-cast button on a finished reading.
- No question-prompt input for the chart-based readings (they still fire immediately as today).
- No new audit table or owner-console submenu — the existing tenant-features submenu picks up the two new flags automatically.

## 3. Product decisions (from brainstorm)

| Decision | Choice | Notes |
| --- | --- | --- |
| Profile required? | Yes — same gate as other readings | Reuses `get_natal_profile` check; users without a profile see the existing `readings.no_profile` message. |
| Question input | Optional free-text, with `/skip` | FSM step between "Tarot/I-Ching tapped" and "draw". Stored on the reading. |
| Tarot spread | Three-card only (past/present/future) | One spread keeps surface small. |
| Reversals | 50/50 per drawn card | Standard tarot convention. |
| I-Ching method | Three-coin: 6 lines (6/7/8/9) + changing lines + transformed hexagram | Captures the distinctive dynamic-line trajectory. |
| Tarot data | Ship Python deck constant (78 cards × upright/reversed keywords) | Deterministic, no LLM hallucination on card attributes. |
| I-Ching data | Ship Wilhelm-style hexagram constant (judgment / image / six line statements, public domain) | Deterministic; LLM translates / polishes into user's language. |
| Schema | Reuse `readings` table + add `draw_jsonb` column | Reuses the entire reading pipeline. |
| `natal_profile_id` | Stays NOT NULL | Profile-required decision; no nullable migration. |

## 4. Architecture

### 4.1 Schema delta (one migration)

```python
# alembic/versions/a3b4c5d6e7f8_readings_draw_jsonb.py
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

`Reading.draw_jsonb` is `dict | None`. NULL for existing 8 chart-based kinds; populated for tarot/iching.

**Tenant feature keys** (in `src/quantuum/domain/tenant_features.py`):

```python
FEATURE_KEYS = (
    "qa", "blueprint", "transits", "daily",
    "reading.bazi", "reading.numerology", "reading.human_design",
    "reading.astrology", "reading.vedic", "reading.gene_keys",
    "reading.mayan", "reading.aspects",
    "reading.tarot", "reading.iching",   # SP6
    "referrals", "gifts",
)
```

Inventory bumps from 14 → 16 in `tests/test_tenant_features_domain.py`.

**Reading kinds menu** (in `src/quantuum/bot/ui/keyboards.py`):

```python
READING_KINDS = (
    "bazi", "numerology", "human_design", "astrology",
    "vedic", "gene_keys", "mayan", "aspects",
    "tarot", "iching",
)
```

The existing `readings_menu_kb` automatically picks them up via the `flags.get(f"reading.{k}", True)` gate.

### 4.2 Divination data modules

**`src/quantuum/divination/__init__.py`** — empty package marker.

**`src/quantuum/divination/tarot.py`**

```python
TAROT_DECK: list[Card] = [...]   # 78 entries: 22 majors + 56 minors (4 suits × 14)

@dataclass(frozen=True)
class Card:
    id: str            # canonical id, e.g. "major_00_fool", "wands_05"
    name: str          # canonical English name, e.g. "The Fool"
    arcana: str        # "major" | "minor"
    suit: str | None   # "wands" | "cups" | "swords" | "pentacles" | None
    number: int | None
    upright: tuple[str, ...]   # 3-5 short keywords
    reversed: tuple[str, ...]  # 3-5 short keywords

@dataclass(frozen=True)
class CardDraw:
    card: Card
    reversed: bool
    position: str  # "past" | "present" | "future"

def draw_three(rng: random.Random | None = None) -> list[CardDraw]:
    """Three distinct cards, each independently 50/50 reversed."""

def build_calc_md(*, question: str | None, cards: list[CardDraw]) -> str:
    """Markdown summary the LLM polishes. Includes question (or 'None'),
    each position with card name, orientation, and keyword list.
    """
```

`draw_three` uses `random.SystemRandom()` by default; tests can pass a seeded `random.Random` for determinism.

**`src/quantuum/divination/iching.py`**

```python
HEXAGRAMS: dict[int, Hexagram] = {1: Hexagram(...), ..., 64: Hexagram(...)}

@dataclass(frozen=True)
class Hexagram:
    number: int          # 1..64
    name_en: str         # e.g. "The Creative"
    name_pinyin: str     # e.g. "Qian"
    trigram_above: str   # canonical name
    trigram_below: str
    judgment: str        # Wilhelm-style English text
    image: str
    lines: tuple[str, ...]  # 6 line statements, bottom→top

@dataclass(frozen=True)
class CastResult:
    lines: tuple[int, ...]            # six values in {6, 7, 8, 9}, bottom→top
    changing_indices: tuple[int, ...] # zero-based indices where line is 6 or 9
    primary_id: int                   # 1..64
    transformed_id: int | None        # None when no changing lines

def cast_three_coins(rng: random.Random | None = None) -> CastResult:
    """One coin throw per line; values: heads=3, tails=2; sum of 3 throws
    yields 6/7/8/9. Maps line-pattern → hexagram via canonical King Wen lookup.
    """

def build_calc_md(*, question: str | None, cast: CastResult) -> str:
    """Markdown summary the LLM polishes. Includes question, primary hex
    name + judgment + image, each changing line's statement, transformed
    hex name + judgment when applicable.
    """
```

**Determinism rule:** `draw_three` and `cast_three_coins` accept an injected RNG. Production calls them without an RNG (uses `SystemRandom`). Tests inject `random.Random(seed)`.

### 4.3 Reading task fork (`src/quantuum/tasks/reading.py`)

Current shape:

```python
profile = await session.get(NatalProfile, reading.natal_profile_id)
inp = from_natal_profile(profile)
calc_md = build_reading_calc_md(reading.kind, inp)
```

New:

```python
if reading.kind in ("tarot", "iching"):
    calc_md = build_divination_calc_md(reading.kind, reading.draw_jsonb)
else:
    profile = await session.get(NatalProfile, reading.natal_profile_id)
    inp = from_natal_profile(profile)
    calc_md = build_reading_calc_md(reading.kind, inp)
```

`build_divination_calc_md` lives in `src/quantuum/divination/__init__.py` (small dispatcher):

```python
def build_divination_calc_md(kind: str, draw: dict | None) -> str:
    if kind == "tarot":
        return tarot.build_calc_md_from_jsonb(draw)
    if kind == "iching":
        return iching.build_calc_md_from_jsonb(draw)
    raise ValueError(f"not a divination kind: {kind}")
```

Each module exposes a `build_calc_md_from_jsonb(draw)` that re-hydrates its dataclasses from the stored JSON and reuses the existing `build_calc_md` formatter.

### 4.4 LLM polish (`src/quantuum/llm/reading_polish.py`)

Register the two new prompts and labels:

```python
READING_PROMPTS = {
    ...existing 8...,
    "tarot":  _PROMPTS / "reading_tarot.txt",
    "iching": _PROMPTS / "reading_iching.txt",
}

_KIND_LABEL = {
    ...existing 8...,
    "tarot":  "Tarot three-card spread",
    "iching": "I-Ching three-coin cast",
}
```

**`src/quantuum/llm/prompts/reading_tarot.txt`** (new) voice rules:
- Anchor on the supplied keyword list for each card; do not invent card attributes.
- Acknowledge orientation (upright vs reversed) — never silently flip a card.
- If a question is present, frame past/present/future around it.
- One short synthesis paragraph at the close.

**`src/quantuum/llm/prompts/reading_iching.txt`** (new) voice rules:
- Lead with primary hexagram name + judgment.
- Use image as supporting metaphor, not literal.
- For each changing line index, surface the line statement explicitly.
- If transformed hexagram exists, name the trajectory (from → to).
- If a question is present, frame guidance around it.

### 4.5 Sender UX (`src/quantuum/bot/handlers/divination.py` — new module)

The existing handler at `src/quantuum/bot/handlers/readings.py:30` matches every `ReadingCb(action="generate")` regardless of `kind`. We register a new router with a kind-filtered handler **before** the readings router so it captures tarot/iching first.

Order matters: `app.py` must include `divination.router` ahead of `readings.router`.

#### Flow

```
ReadingCb(action="generate", kind in {tarot,iching})
  │
  ▼
on_divination_choice():
  │ feature flag check (reading.tarot or reading.iching) → feature.disabled_generic
  │ profile check → readings.no_profile
  │ quota check (cost_units=1) → readings.no_quota
  │ enter Divination.awaiting_question FSM
  │ state.update_data(kind=kind)
  │ prompt: divination.question_prompt + divination.question_hint
  │ inline skip button → DivinationCb(action="skip")
  ▼
either: text message → on_divination_question(text):  set question=text
or:     /skip command OR DivinationCb(action="skip"): set question=None
  │
  ▼
_perform_draw_and_enqueue(question, kind):
  │ if kind == "tarot":  draw = draw_three(); draw_jsonb = {"question": q, "cards": [...]}
  │ if kind == "iching": cast = cast_three_coins(); draw_jsonb = {"question": q, "lines": [...], "primary_id": ..., "transformed_id": ..., "changing_indices": [...]}
  │ create_reading(..., kind=kind, draw_jsonb=draw_jsonb)
  │ create_request(...)
  │ enqueue_reading(reading_id, chat_id, request_id)
  │ state.clear()
  ▼
Reply: readings.queued
```

The FSM uses aiogram `StatesGroup`:

```python
class Divination(StatesGroup):
    awaiting_question = State()
```

Quota is consumed in `on_divination_choice` (before the FSM), matching the existing readings handler's debit-on-tap semantics. If the user never finishes the FSM (e.g., closes the chat), the quota is gone — same UX gap the chart readings have today.

### 4.6 i18n keys (~14 unique × 10 locales)

| Key | Placeholders | Surface |
| --- | --- | --- |
| `readings.kind.tarot` | — | Menu button label |
| `readings.kind.iching` | — | Menu button label |
| `divination.question_prompt` | — | "Type your question or send /skip" |
| `divination.question_hint` | — | "Or tap Skip below" |
| `divination.skip_btn` | — | Inline button label |
| `divination.no_question` | — | Used in calc_md when question is None ("(no question)") |
| `tarot.position.past` | — | "Past" |
| `tarot.position.present` | — | "Present" |
| `tarot.position.future` | — | "Future" |
| `tarot.orientation.upright` | — | "upright" |
| `tarot.orientation.reversed` | — | "reversed" |
| `iching.judgment_label` | — | "Judgment" |
| `iching.image_label` | — | "Image" |
| `iching.changing_line_label` | `{n}` | "Changing line {n}" |
| `iching.transformed_label` | — | "Becomes" |

The two `readings.kind.*` labels feed the existing menu builder. The `tarot.*` / `iching.*` strings are used inside `build_calc_md` so the LLM sees position/orientation labels in the user's language (helpful for non-English readings).

**Reuse from existing seed:** `readings.queued`, `readings.no_profile`, `readings.no_quota`, `feature.disabled_generic`. No new "unknown" / "error" keys.

### 4.7 Audit

No new audit actions. Existing `Reading` row creation + `Request` row creation already establish a per-reading record. Reuse.

### 4.8 Owner console

No change. The existing `/owner_console` features submenu lists every `FEATURE_KEYS` entry; the two new ones appear automatically. The labels come from i18n (see `owner.features.label.<key>` pattern if it exists; otherwise the SP2 owner-features handler uses the raw flag key).

If the SP2 features submenu uses explicit per-flag i18n labels, add `owner.features.label.reading.tarot` and `owner.features.label.reading.iching` to the seed. **Implementation MUST verify SP2's per-flag label convention before assuming it auto-formats raw keys.** If labels are required, append them to the 30-key seed list above for a total of 16 new keys × 10 locales.

## 5. Data-flow diagrams

### 5.1 Tarot draw

```
User taps "Tarot"  →  on_divination_choice()
  │  flag + profile + quota checks
  ▼
Prompt + inline Skip button
  │
  ▼  (user types question OR /skip OR tap Skip)
on_divination_question() / on_divination_skip()
  │  draw_three() → 3 distinct cards, 50/50 reversed each
  │  draw_jsonb = {"question": q, "cards": [{"id","name","reversed","position"} × 3]}
  │  create_reading(kind="tarot", draw_jsonb=draw_jsonb)
  │  create_request(); enqueue_reading()
  ▼
Worker: reading_generate()
  │  build_divination_calc_md("tarot", draw_jsonb) → calc_md
  │  polish_reading("tarot", calc_md, lang=...)
  ▼
Delivery (existing pipeline)
```

### 5.2 I-Ching cast

```
User taps "I-Ching"  →  on_divination_choice()
  │  flag + profile + quota checks
  ▼
Prompt + inline Skip button
  │
  ▼  (user types question OR /skip OR tap Skip)
on_divination_question() / on_divination_skip()
  │  cast_three_coins() → six lines (6/7/8/9), primary_id, changing_indices, transformed_id
  │  draw_jsonb = {"question": q, "lines": [...], "primary_id": ..., "transformed_id": ..., "changing_indices": [...]}
  │  create_reading(kind="iching", draw_jsonb=draw_jsonb)
  │  create_request(); enqueue_reading()
  ▼
Worker: reading_generate()
  │  build_divination_calc_md("iching", draw_jsonb) → calc_md
  │  polish_reading("iching", calc_md, lang=...)
  ▼
Delivery
```

## 6. Concurrency & abuse considerations

- **Random source:** `random.SystemRandom()` is cryptographically suitable and matches existing usage (`secrets` module in SP4/SP5 code generation). Tests inject `random.Random(seed)`.
- **Reading-task replay safety:** `draw_jsonb` is captured at handler time and persisted. If the worker retries `reading_generate`, the same draw is used — no fresh randomness per attempt. Critical for reproducibility.
- **Question content:** The question is free-text user input destined for an LLM. **The existing content-moderation tier 1+2 pre-LLM filter (SP1 in `quantuum/bot/handlers/qa.py`) is currently invoked only for the QA handler.** SP6 reuses the QA moderation entry point on the question text BEFORE the draw is performed. If a moderation hit occurs, abort the FSM, refund the quota via the existing `refund_quota` helper, and show the moderation message. **Implementation MUST locate and reuse the SP1 moderation helper rather than rolling its own.** If the question is empty (skip path), moderation is bypassed.
- **Quota-debit before FSM completion:** The handler debits the quota at `on_divination_choice`. If the user abandons the FSM without finishing (closes chat, times out), the quota is consumed. This matches the existing readings UX (and is a known limitation; out of scope to fix here).
- **Refund path on FSM error:** Three explicit refund triggers: (a) moderation hit on the question, (b) `/skip` followed by draw RNG failure (shouldn't happen, but defensive), (c) any exception during `_perform_draw_and_enqueue` before `create_reading` succeeds. After `create_reading` succeeds, the reading row is the source of truth and refunds (if needed) go through the existing reading-failure path.
- **`draw_jsonb` schema drift:** The structure is fixed in this spec. If a future change adds fields, the `build_calc_md_from_jsonb` rehydrators must tolerate missing keys with sensible defaults.
- **i18n fallback in calc_md:** `build_calc_md` produces text that includes localized position/orientation labels. The Translator's existing 6-step fallback chain handles missing translations — no extra guard needed.

## 7. Testing strategy

Per-task targeted tests during execution; full suite at stage end.

| Task | Test target |
| --- | --- |
| Migration + model | Smoke test: `Reading.draw_jsonb` accepts dict, NULL is fine. |
| Tarot module | `tests/test_divination_tarot.py`: deck integrity (78 cards, 22 majors, 4 suits × 14), `draw_three` returns 3 distinct cards, seeded RNG is deterministic, reversal distribution sanity (large-N), `build_calc_md` golden snippet. |
| I-Ching module | `tests/test_divination_iching.py`: hexagram integrity (64 entries with all line statements), `cast_three_coins` line values ∈ {6,7,8,9}, changing-line indices correct, transformed hexagram lookup matches the King Wen sequence for sample line patterns, `build_calc_md` golden snippet. |
| Task fork | `tests/test_reading_task_divination.py`: branches on kind; uses `draw_jsonb`; does NOT call `from_natal_profile` for tarot/iching; LLM polish path still hit; status transitions OK. |
| LLM polish registry | `tests/test_reading_polish_registry.py` (or extension): asserts `"tarot"` and `"iching"` are in `READING_PROMPTS` and `_KIND_LABEL`. |
| Handler + FSM | `tests/test_divination_handler.py`: FSM happy path (text question → draw → enqueue → quota debited, request + reading rows created, `draw_jsonb` non-null); `/skip` path (question=None); profile-missing → `readings.no_profile`, no quota debit, no reading row; no-quota → `readings.no_quota`, no reading row; feature-flag-off → `feature.disabled_generic`; moderation hit on question → abort + refund. |
| i18n | `tests/test_divination_i18n.py`: presence + placeholder integrity for the new keys across all 10 locales (one placeholder: `{n}` in `iching.changing_line_label`). |
| Inventory + menu | Update `tests/test_tenant_features_domain.py` (14→16) and `tests/test_ui_keyboards.py` (menu now contains the two new labels). |
| Full suite + ruff | Final gate; expect 1785 + new ≈ 60 new tests pass, ruff clean on SP6 files. |

## 8. Out-of-scope follow-ups

- **Additional spreads** (single-card draw, Celtic Cross). Schema already supports — add new `tarot.spread` key in `draw_jsonb` later.
- **Yarrow-stalk I-Ching method** (different probability distribution over 6/7/8/9). Same shape, just a new caster.
- **Recast / replay** button on a delivered reading.
- **Card / hexagram artwork** (image attachments).
- **Per-tenant deck customisation** or alternate translations (e.g., Thoth tarot, Wilhelm vs Legge I-Ching).
- **Question-prompt for chart-based readings** — would unify UX but is a separate decision.

## 9. Plan handoff

The implementation plan (`docs/superpowers/plans/2026-05-28-tarot-iching.md`) breaks SP6 into 7 tasks following SP5 cadence:

1. **Migration + model**: add `Reading.draw_jsonb` (JSONB NULL).
2. **Divination Tarot module**: deck constant + `draw_three` + `build_calc_md` (+ JSONB rehydrator) + tests.
3. **Divination I-Ching module**: hexagram constant + `cast_three_coins` + `build_calc_md` (+ JSONB rehydrator) + tests.
4. **Reading task fork + LLM prompts**: branch in `reading_generate`; register prompts + labels in `reading_polish.py`; add `reading_tarot.txt` and `reading_iching.txt`.
5. **i18n seed**: ~14 keys × 10 locales + placeholder integrity tests (plus owner.features labels if SP2 requires them).
6. **Handler + FSM**: `bot/handlers/divination.py`, register router before readings router, append `READING_KINDS`, append `FEATURE_KEYS`, reuse SP1 moderation on the question.
7. **Inventory + menu test bumps + full suite + ruff**: 14→16 inventory, menu keyboard test bumps, ruff sweep.

Standing constraints carry over: work on `main`, Python 3.13 / PEP 604, ruff-clean, no emojis, full TDD red-green-commit per task, two-stage subagent review (spec opus + code sonnet), per-task targeted tests during execution, full suite only at stage end.
