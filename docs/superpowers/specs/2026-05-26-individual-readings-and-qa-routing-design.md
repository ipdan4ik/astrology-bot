# Individual Readings + QA System-Selection — Design

**Date:** 2026-05-26
**Status:** Approved for planning

## Problem

The current Blueprint is one bundled product: a single deterministic calculator
(`build_blueprint`) emits one big Markdown, and a single LLM pass
(`polish_blueprint`) turns it into the final premium SoulMap. The user cannot
buy or generate just BaZi or just Numerology as standalone polished readings —
they must pay for and read the full blueprint.

QA already accepts free-text questions against the whole `calc_md`, so the model
technically *can* answer from BaZi, astrology, numerology, etc. We want to
verify this works and nudge the prompt to make the system-selection step
explicit, but no architectural change is needed on the QA side.

## Goals

1. Split the existing blueprint into **8 independently-generatable polished
   readings** (one per astrology system), each prog-routed through its own LLM
   prompt — so users can buy and receive just BaZi, just Numerology, etc.
2. Keep **Blueprint as a composite product** that internally runs all 8 readings
   and stitches them into a single document whose voice and structure remain
   close to the current premium SoulMap.
3. Confirm **QA already routes across systems** and add an explicit
   "system-selection" instruction to the prompt so the model is clearly told to
   pick the relevant systems for a given question.

## Non-goals

- Caching individual readings to feed back into a later Blueprint request.
- Tool-use / function-calling for QA.
- New slash commands per system (UX is a single "Разборы" menu).
- Per-system database tables (one generic `readings` table covers all 8).

## High-level architecture

```
NatalProfile ──► build_blueprint_context()
                      │
                      ▼
            ┌────────────────────────┐
            │  8 section builders    │   pure, deterministic
            │  build_<kind>_section  │
            └────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
build_reading_calc_md(kind)    build_blueprint()
        │                           │  (orchestrator)
        ▼                           ▼
  Reading.calc_md           Blueprint.calc_md  ◄── used by QA
        │                           │
        ▼                           ▼
 reading_polish (1 LLM)    blueprint_generate:
   prompts/reading_*.txt    8× reading_polish in parallel
        │                   + ceremonial wrapper
        ▼                           │
  Reading.llm_md                    ▼
                            Blueprint.llm_md
```

QA continues to read `Blueprint.calc_md` (or build it on-the-fly from the
profile via `build_blueprint`) and feed the *whole* document to a single LLM
call.

## Data model

### New: `readings` table

```python
class Reading(SQLModel, table=True):
    __tablename__ = "readings"
    __table_args__ = (Index("ix_readings_tenant_created", "tenant_id", "created_at"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    natal_profile_id: int = Field(foreign_key="natal_profiles.id")
    kind: str   # bazi|numerology|human_design|astrology|vedic|gene_keys|mayan|aspects
    status: str = "pending"  # pending|calculating|generating|done|failed
    lang: str | None = None
    calc_md: str | None = None
    llm_md: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None
```

Alembic migration adds the table + the tenant/created composite index.

### `Request.kind`

Extended enum: `blueprint | qa | transit | reading`. For readings, the specific
system is identified by `Reading.kind` via `Request.reference_id` /
`reference_type="reading"`.

### `consume_quota(session, account_id, kind, *, cost_units: int = 1) -> str`

Today it always charges one unit. Add `cost_units` so Blueprint can charge more
than one in a single atomic step.

Rules:
- **Trial** (`free_trial_used` flag) only applies when `kind == "blueprint"`.
  A trial covers the *whole* blueprint regardless of `cost_units`.
- **Subscription** is unmetered; `cost_units` is ignored once the active
  subscription branch is taken (same as today — no per-call charge).
- **Package credits**: deduct exactly `cost_units`. If
  `balance.package_credits < cost_units`, raise `InsufficientFundsError`
  *before* mutating anything; the oldest-expiring `AccountPackage` row is
  decremented in a loop (or by the full `cost_units` if it has enough headroom)
  to preserve FIFO expiry behavior.
- **Refund** (`refund_quota`) reverses by the same `cost_units` (stored on
  `Request.cost_units`, which already exists).

The blueprint `cost_units` default is **4** (≈ four sub-readings of value).
Stored on `subscription_plans` / pricing seed, not hardcoded in `consume_quota`.

## Section builders

Refactor `src/quantuum/astrology/blueprint.py` so that `build_blueprint` becomes
a thin orchestrator over 8 pure section builders. New module:
`src/quantuum/astrology/sections.py`.

### Shared context

```python
@dataclass
class BlueprintContext:
    birth: datetime
    birth_ms: int
    yyyy: int; mm: int; dd: int
    birth_hour: int; birth_minute: int
    planets: dict[str, PlanetPosition]
    asc_lon: float; mc_lon: float
    asc_sd: SignDegree; mc_sd: SignDegree
    ws_cusps_raw: list[float]; porphyry_cusps_raw: list[float]
    ws_houses: list[SignDegree]; porphyry_houses: list[SignDegree]
    nodes: dict[str, ...]
    house_assignments: list[dict]
    aspect_rows: list[dict]
    for_year: int

def build_blueprint_context(inp: BlueprintInput) -> BlueprintContext: ...
```

Computes the astronomy once; every section builder receives `(inp, ctx)`.

### Section builders (each returns a Markdown chunk)

| Builder                          | Source section in current blueprint.py |
|----------------------------------|----------------------------------------|
| `build_identity_section`         | "## 1. Identity Layer"                 |
| `build_aspects_section`          | "## 2. Major Aspects"                  |
| `build_vedic_section`            | "## 3. Vedic (...)"                    |
| `build_numerology_section`       | "## 4. Numerology (Pythagorean)"       |
| `build_bazi_section`             | "## 5. Chinese Four Pillars"           |
| `build_human_design_section`     | "## 6. Human Design"                   |
| `build_gene_keys_section`        | "## 7. Gene Keys"                      |
| `build_mayan_section`            | "## 8. Mayan Tzolkin"                  |

### `build_blueprint` after refactor

```python
def build_blueprint(inp: BlueprintInput) -> str:
    ctx = build_blueprint_context(inp)
    return "\n".join([
        _render_header(inp, ctx),
        build_identity_section(inp, ctx),
        build_aspects_section(inp, ctx),
        build_vedic_section(inp, ctx),
        build_numerology_section(inp, ctx),
        build_bazi_section(inp, ctx),
        build_human_design_section(inp, ctx),
        build_gene_keys_section(inp, ctx),
        build_mayan_section(inp, ctx),
        _render_footer(),
    ])
```

The CHARACTER-EXACT golden-master test (the one porting parity with
blueprint.ts) must remain green.

### Per-kind reading calc_md

```python
SECTION_BUILDERS = {
    "bazi": build_bazi_section,
    "numerology": build_numerology_section,
    "human_design": build_human_design_section,
    "astrology": build_identity_section,
    "vedic": build_vedic_section,
    "gene_keys": build_gene_keys_section,
    "mayan": build_mayan_section,
    "aspects": build_aspects_section,
}

def build_reading_calc_md(kind: str, inp: BlueprintInput) -> str:
    ctx = build_blueprint_context(inp)
    return "\n".join([
        _render_header(inp, ctx),
        SECTION_BUILDERS[kind](inp, ctx),
        _render_footer(),
    ])
```

Each reading therefore feeds the LLM a self-contained mini-document (birth
header + just its system's section + footer) rather than the full blueprint.

## LLM polish

### New: `src/quantuum/llm/reading_polish.py`

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
}

async def polish_reading(client, kind, calc_md, *, lang, model, temperature, max_tokens):
    system = READING_PROMPTS[kind].read_text()
    user = "\n".join([
        f"Transform this calculated {kind} chart slice into the polished Quantuum reading.",
        f"Answer in language: {lang}.",
        "",
        "CALCULATED MARKDOWN:",
        calc_md,
    ])
    return await client.complete(system=system, user=user, model=model, temperature=temperature, max_tokens=max_tokens)
```

### Per-kind prompts

8 new files under `src/quantuum/llm/prompts/reading_*.txt`. Each mirrors the
voice and fact-discipline of `blueprint_writer.txt`:
- Same CRITICAL FACT RULES (no invented numbers, preserve house-system labels,
  no numbered lists, etc.).
- Same LANGUAGE AND VOICE rules.
- Tailored REQUIRED STRUCTURE — only the headings/blocks that belong to that
  system. For example `reading_bazi.txt` requires Year/Month/Day/Hour pillar
  blocks, Day Master section, polarity discussion, but does NOT ask for Gene
  Keys / Mayan / etc.

The prompts are drafted in the implementation phase. Style guidance: each
reading should feel like a chapter of the full SoulMap, not a different voice.

### Blueprint orchestrator (new shape of `polish_blueprint`)

`src/quantuum/llm/blueprint_polish.py` keeps its public function name but
internally:

```python
async def polish_blueprint(client, calc_md, *, lang, model, temperature, max_tokens, build_input):
    ctx = build_blueprint_context(build_input)
    sections = await asyncio.gather(*[
        polish_reading(client, kind, build_reading_calc_md(kind, build_input),
                       lang=lang, model=model, temperature=temperature, max_tokens=max_tokens)
        for kind in _BLUEPRINT_ORDER  # fixed order, see below
    ])
    return _stitch_blueprint(build_input, ctx, sections, lang=lang)
```

`_stitch_blueprint` assembles the final document:

```
# {FULL NAME} — QUANTUUM SOULMAP BLUEPRINT

<ceremonial opening — generated by a small fixed template using birth data
 from the source, NO LLM call>

## 🌌 FIELD OVERVIEW
<assembled from the eight reading_* outputs via a deterministic stitcher —
 not a separate LLM pass. Each polished reading is expected to expose a
 short FIELD OVERVIEW table fragment at the top of its output, which we
 extract and merge here.>

<section 1>
<section 2>
...
<section 8>

## 🕊 ORACLE AFFIRMATION
<deterministic template from birth data and computed numbers>

## 🧭 CLOSING TRANSMISSION
<deterministic template>
```

The eight reading prompts MUST emit, as their first content, a small
`FIELD OVERVIEW FRAGMENT` marker block (e.g. between
`<!-- field-overview-start -->` and `<!-- field-overview-end -->`) that the
stitcher harvests. This keeps style consistency without a second LLM pass.

If the stitcher cannot find the fragment for some section, it falls back to a
short auto-generated line from `calc_md` for that system so the final report
is never broken by a missing fragment.

`Blueprint.llm_md` stores the final stitched markdown.

## Domain layer

### `src/quantuum/domain/readings.py`

Mirrors `domain/blueprints.py`:

```python
async def create_reading(session, *, tenant_id, account_id, natal_profile_id, kind, lang) -> Reading
async def get_reading(session, reading_id) -> Reading
async def set_reading_status(session, reading_id, status, **fields) -> None
async def list_readings(session, *, account_id, limit=50, offset=0) -> list[Reading]
```

Status transitions: `pending → calculating → generating → done|failed`. Same
shape as blueprints.

### Task: `src/quantuum/tasks/reading.py`

```python
async def reading_generate(ctx, reading_id, chat_id=None, request_id=None):
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        try:
            reading = await get_reading(session, reading_id)
            tenant_id = reading.tenant_id
            profile = await session.get(NatalProfile, reading.natal_profile_id)
            inp = from_natal_profile(profile)
            calc_md = build_reading_calc_md(reading.kind, inp)
            await set_reading_status(session, reading_id, "calculating", calc_md=calc_md)
            await set_reading_status(session, reading_id, "generating")

            llm_client = ctx.get("llm_client")
            cfg = await get_llm_config(session)
            if llm_client is None:
                # graceful degradation, same pattern as blueprint
                await set_reading_status(session, reading_id, "done",
                                          llm_md=calc_md, llm_provider="none", llm_model="none")
                delivery_md = calc_md
            else:
                lang = reading.lang or await get_tenant_default_lang(session, tenant_id) or "ru"
                result = await polish_reading(llm_client, reading.kind, calc_md,
                                              lang=lang, model=cfg["model"],
                                              temperature=cfg["temperature"], max_tokens=cfg["max_tokens"])
                await set_reading_status(session, reading_id, "done",
                                          llm_md=result.text, llm_provider=cfg["provider"],
                                          llm_model=result.model, llm_tokens_in=result.tokens_in,
                                          llm_tokens_out=result.tokens_out)
                delivery_md = result.text
            if request_id is not None:
                try:
                    await complete_request(session, request_id, reference_id=reading_id, reference_type="reading")
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
            await deliver_via_tenant_bot(sessionmaker, tenant_id=tenant_id, chat_id=chat_id,
                                          text=delivery_md, filename=f"reading-{reading.kind}.md",
                                          preview_len=4000, always_document=False)
        except Exception:
            logger.exception("reading_delivery_failed", reading_id=reading_id, chat_id=chat_id)
```

### Task: `src/quantuum/tasks/blueprint.py` (rewritten)

Instead of one LLM call, runs 8 polished readings in parallel **inline** —
without creating `Reading` rows — and stitches the result:

```python
async def blueprint_generate(ctx, blueprint_id, chat_id=None, request_id=None):
    ...
    inp = from_natal_profile(profile)
    calc_md = build_blueprint(inp)                          # full md (also used by QA)
    await set_status(session, blueprint_id, "calculating", calc_md=calc_md)
    await set_status(session, blueprint_id, "generating")

    if llm_client is None:
        await set_status(session, blueprint_id, "done", llm_md=calc_md, ...)
        delivery_md = calc_md
    else:
        polished = await polish_blueprint(llm_client, calc_md, lang=lang, ...,
                                           build_input=inp)
        # polished.text already stitched; polished.tokens_* are aggregated sums
        await set_status(session, blueprint_id, "done", llm_md=polished.text,
                          llm_provider=cfg["provider"], llm_model=polished.model,
                          llm_tokens_in=polished.tokens_in, llm_tokens_out=polished.tokens_out)
        delivery_md = polished.text
    ...
```

The 8 internal reading polishes are pure function calls; they do NOT touch the
`readings` table or the user's history (those rows are reserved for explicit
single-reading purchases).

### Task: `src/quantuum/tasks/enqueue.py`

Add `enqueue_reading(reading_id, chat_id, request_id)`.

## QA changes

**Code:** none. `qa.py`, `tasks/qa.py`, `qa_answer.py`, `domain/qa.py`,
`resolve_calc_md` all stay as they are. In particular, `resolve_calc_md`
continues to prefer the latest `done` Blueprint's `calc_md` and falls back to
`build_blueprint(from_natal_profile(profile))` when none exists — meaning QA
works for users who have only purchased individual readings (or none at all)
without forcing them to buy a Blueprint first.

**Prompt patch** in `src/quantuum/llm/prompts/qa_astrologer.txt`. Insert after
the existing CRITICAL FACT RULES block:

```
SYSTEM SELECTION
- The chart contains multiple systems (Tropical/Western astrology, Vedic,
  numerology, BaZi, Human Design, Gene Keys, Mayan Tzolkin, aspects, timing
  cycles). Before answering, decide which systems are directly relevant to the
  question and ground the answer in those.
- Do not force-include systems that don't speak to what was asked. A question
  about money may pull from BaZi Day Master, numerology Destiny / Personal
  Year, the 2nd/8th houses, and relevant aspects — not from Mayan Tzolkin
  unless it adds real signal.
- If the question explicitly names a system ("по BaZi", "by numerology",
  "по Human Design"), restrict the answer to that system.
```

This is a one-paragraph change; no code or schema impact.

## Bot UX

### Main menu

Add one new reply-keyboard button: `btn.readings` (label "📖 Разборы" /
"📖 Readings" in each language). Other main-menu buttons (Generate, Ask,
Transits, Daily, Profile, History, Help, Language) are unchanged.

Pressing "Разборы" opens an inline keyboard:

```
🐉 BaZi              🔢 Numerology
🧬 Human Design      ☉ Astrology
🕉 Vedic             🗝 Gene Keys
🌀 Mayan              ✦ Aspects
```

Callback: `ReadingCb(action="generate", kind="bazi"|...)`.

### Reading callback handler

`src/quantuum/bot/handlers/readings.py`:

```python
async def on_reading_choice(query, account, i18n):
    kind = ReadingCb.unpack(query.data).kind
    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
        if profile is None:
            await query.message.answer(await i18n("readings.no_profile"))
            return
        try:
            charged = await consume_quota(session, account.id, "reading", cost_units=1)
        except InsufficientFundsError:
            await query.message.answer(await i18n("readings.no_quota"),
                                        reply_markup=await _buy_offer_kb(i18n))
            return
        reading = await create_reading(session, tenant_id=account.tenant_id,
                                        account_id=account.id, natal_profile_id=profile.id,
                                        kind=kind, lang=i18n.lang)
        request = await create_request(session, tenant_id=account.tenant_id,
                                        account_id=account.id, kind="reading",
                                        charged_against=charged, cost_units=1,
                                        reference_id=reading.id, reference_type="reading")
    await enqueue_reading(reading.id, query.message.chat.id, request.id)
    await query.message.answer(await i18n("readings.queued"))
```

### History

`history.py` already lists blueprints. Add a parallel "Readings" subsection
showing the most recent readings (kind + status + download). Reuse the existing
download flow.

### Profile / no-profile flow

Identical to blueprint — if no `NatalProfile`, prompt the user to set one up
first.

## i18n

Add to `BASE_STRINGS`:

```
btn.readings = "📖 Разборы" (/etc.)
readings.menu.title = "Какой разбор сгенерировать?"
readings.kind.bazi = "🐉 BaZi"
readings.kind.numerology = "🔢 Numerology"
readings.kind.human_design = "🧬 Human Design"
readings.kind.astrology = "☉ Astrology"
readings.kind.vedic = "🕉 Vedic"
readings.kind.gene_keys = "🗝 Gene Keys"
readings.kind.mayan = "🌀 Mayan"
readings.kind.aspects = "✦ Aspects"
readings.queued = "Готовлю разбор. Это займёт минуту."
readings.no_profile = "Сначала заполни профиль рождения."
readings.no_quota = "Нет доступных кредитов. Купи пакет, чтобы продолжить."
```

Translations in all 10 supported languages — added to per-lang translation
files (auto-merged into BASE_STRINGS per existing i18n pipeline). The seed is
insert-only, so the keys land via normal startup.

## Testing

### New tests

- `tests/astrology/test_sections.py`:
  - Each `build_*_section` is a pure function — golden snapshot per section.
  - `build_reading_calc_md(kind, inp)` produces a self-contained mini-doc with
    header + that section + footer.
- `tests/llm/test_reading_polish.py`:
  - Fake LLM client; assert system prompt is the per-kind file, assert user
    message contains the kind label and the calc_md.
- `tests/domain/test_readings.py`:
  - create / get / status transitions / list.
- `tests/tasks/test_reading_task.py`:
  - Happy path: calc_md is set, status transitions, request completes.
  - LLM unavailable: graceful degradation (status=done with calc_md fallback).
  - Failure: status=failed, refund_quota called.
- `tests/tasks/test_blueprint_compose.py`:
  - polish_blueprint runs 8 polish_reading calls in parallel, stitched output
    contains all 8 sections + header/footer.
  - One section failure → which behaviour? **Decision:** if ANY polished
    reading raises, the whole blueprint generation fails and refunds. (We
    can't deliver a half-blueprint without surprising the user.) Tested.
- `tests/bot/test_readings_handler.py`:
  - Callback for each kind enqueues a Reading + Request + charges 1 unit.
  - No profile → prompt.
  - No quota → buy offer.
- `tests/domain/test_quota_cost_units.py`:
  - `consume_quota(..., cost_units=4)` deducts 4 package credits atomically;
    if balance is 3, raises and mutates nothing.
  - `refund_quota` returns the same `cost_units` to the user.
  - Trial: still single-shot for blueprint regardless of cost_units.

### Tests that MUST stay green

- `tests/astrology/test_blueprint.py` — CHARACTER-EXACT golden master for
  `build_blueprint`. The refactor MUST NOT change a byte of its output.
- All existing QA, transit, billing, history tests.

## Migration plan (per-PR order)

1. **PR1 — section builders refactor.** Pure mechanical refactor; tests pass.
2. **PR2 — `readings` table + domain + cost_units.** No bot UX yet.
3. **PR3 — `reading_generate` task + 8 prompts + `polish_reading`.** Internal,
   no UI exposure; backfilled with unit tests.
4. **PR4 — bot UX: button, callback, handler, i18n strings.** First version
   visible to users (each system as a 1-credit reading).
5. **PR5 — blueprint orchestrator rewrite + stitcher.** Replaces single-LLM
   `polish_blueprint` with the 8-in-parallel composer. CHARACTER-EXACT
   `build_blueprint` golden test stays green; new `polish_blueprint`
   integration test covers stitched output.
6. **PR6 — QA prompt patch.** One-file change; QA tests stay green.
7. **PR7 — history listing for readings + cleanup.**

Each PR ships independently; readings become user-facing at PR4 even before
the blueprint composition is in place.

## Open questions deferred to implementation

- Exact value of blueprint `cost_units` (4 is the default proposal, but it
  should be configurable per pricing seed).
- Field-overview fragment format: chosen between an HTML-comment marker block
  vs. a leading fenced section the stitcher parses. Decision made during PR5.
- Whether to expose the `Blueprint.calc_md` to the user as a downloadable
  "raw chart" — currently no, kept as an internal source for QA.
