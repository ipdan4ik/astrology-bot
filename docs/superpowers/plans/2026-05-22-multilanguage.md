# Multi-language Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the bot from 2 languages (ru/en) to 10 and make every LLM-generated reading honor the user's chosen language.

**Architecture:** A single source-of-truth tuple of platform languages drives enablement, the picker, and tests. The 8 new languages' UI strings live in one file per language under `src/quantuum/i18n/translations/`, auto-discovered and merged into `BASE_STRINGS` (so existing seed/cache machinery is unchanged). Readings reuse the existing transit/daily pattern: a `lang` is captured at request time and passed to the generator, which instructs the model to answer in it. Blueprint gains a `lang` column to match `TransitReport`/`QaAnswer`; Q&A already stores `lang` and just needs threading.

**Tech Stack:** Python 3.12, aiogram 3, SQLModel/asyncpg/PostgreSQL, alembic, Redis, arq, OpenAI LLM, pytest + pytest-asyncio.

**Languages:** `ru, en` (existing) + `es, fr, pt, it, de, tr, zh, hi` (new). Default stays `ru`.

**Test stack:** PG `172.30.0.2`, Redis `172.30.0.3` (already up). Tests build schema from `SQLModel.metadata.create_all` — migrations are for prod parity and are not exercised by the suite. Per-task, run only that task's targeted tests; run the full suite at stage end.

---

### Task 1: Language single-source-of-truth + picker labels & layout

**Files:**
- Create: `src/quantuum/i18n/langs.py`
- Modify: `src/quantuum/bot/ui/keyboards.py` (`LANG_LABELS` ~line 20; `language_picker_kb` `.adjust(1)` ~line 70)
- Test: `tests/test_language_picker.py`

- [ ] **Step 1: Create the language constants module**

Create `src/quantuum/i18n/langs.py`:

```python
"""Single source of truth for the platform's supported languages."""

DEFAULT_LANG = "ru"

# Display/seed order. ru first (default), en second, then the rest.
PLATFORM_LANGS: tuple[str, ...] = (
    "ru", "en", "es", "fr", "pt", "it", "de", "tr", "zh", "hi",
)

# Non-default languages, used as the default extra_langs for tenant seeding.
EXTRA_LANGS: tuple[str, ...] = tuple(c for c in PLATFORM_LANGS if c != DEFAULT_LANG)
```

- [ ] **Step 2: Add native labels and widen the picker**

In `src/quantuum/bot/ui/keyboards.py`, replace the `LANG_LABELS` dict (currently ru/en only):

```python
LANG_LABELS = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
    "es": "🇪🇸 Español",
    "fr": "🇫🇷 Français",
    "pt": "🇵🇹 Português",
    "it": "🇮🇹 Italiano",
    "de": "🇩🇪 Deutsch",
    "tr": "🇹🇷 Türkçe",
    "zh": "🇨🇳 中文",
    "hi": "🇮🇳 हिन्दी",
}
```

In `language_picker_kb`, change `b.adjust(1)` to `b.adjust(2)` (two columns for 10 languages).

- [ ] **Step 3: Write the failing test (label coverage)**

Append to `tests/test_language_picker.py`:

```python
def test_lang_labels_cover_all_platform_langs():
    from quantuum.bot.ui.keyboards import LANG_LABELS
    from quantuum.i18n.langs import PLATFORM_LANGS

    for code in PLATFORM_LANGS:
        assert code in LANG_LABELS, f"LANG_LABELS missing native name for {code!r}"
        assert LANG_LABELS[code].strip(), f"LANG_LABELS[{code!r}] is empty"
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_language_picker.py::test_lang_labels_cover_all_platform_langs -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/i18n/langs.py src/quantuum/bot/ui/keyboards.py tests/test_language_picker.py
git commit -m "feat(i18n): platform language constants + native picker labels (10 langs)"
```

---

### Task 2: Enablement default + double-default guard + all-tenant backfill

**Files:**
- Modify: `src/quantuum/db/bootstrap.py` (`ensure_tenant_default_language`, lines 209-241)
- Modify: `src/quantuum/api/app.py` (lifespan, lines 22-37)
- Test: `tests/test_i18n_seed.py`, `tests/test_language_picker.py`

- [ ] **Step 1: Harden `ensure_tenant_default_language` (default to all langs + no second default)**

In `src/quantuum/db/bootstrap.py`, add the import near the top (with the other imports):

```python
from quantuum.i18n.langs import EXTRA_LANGS
```

Replace the whole `ensure_tenant_default_language` function body with:

```python
async def ensure_tenant_default_language(
    session,
    tenant_id: int,
    default_lang: str = "ru",
    extra_langs: tuple[str, ...] = EXTRA_LANGS,
) -> None:
    """Idempotently ensure TenantLanguage rows for *tenant_id*.

    * default_lang gets is_default=True, enabled=True — BUT only if the tenant
      does not already have a default language (never creates a second default,
      never flips an existing one).
    * each lang in extra_langs gets is_default=False, enabled=True.
    * Never creates duplicate rows.
    """
    result = await session.execute(
        select(TenantLanguage).where(TenantLanguage.tenant_id == tenant_id)
    )
    existing: dict[str, TenantLanguage] = {row.lang: row for row in result.scalars()}
    has_default = any(row.is_default for row in existing.values())

    # The configured default is only marked default when no default exists yet.
    all_langs = [(default_lang, not has_default)] + [(lang, False) for lang in extra_langs]
    added = False
    for lang, is_default in all_langs:
        if lang not in existing:
            session.add(
                TenantLanguage(
                    tenant_id=tenant_id,
                    lang=lang,
                    enabled=True,
                    is_default=is_default,
                )
            )
            added = True

    if added:
        await session.commit()
```

- [ ] **Step 2: Backfill every tenant in the API bootstrap**

In `src/quantuum/api/app.py`, add imports at the top of the file (with the other imports):

```python
from sqlmodel import select
from quantuum.db.models import Tenant
```

In `_lifespan`, replace these two lines:

```python
        default_tenant_id = await get_default_tenant_id(session)
        await ensure_tenant_default_language(session, default_tenant_id)
        await ensure_tenant_default_language(session, platform.id, default_lang="ru")
```

with:

```python
        # Enable all platform languages for every tenant (idempotent backfill of
        # existing tenants; new tenants inherit the new default via provisioning).
        tenant_ids = (await session.execute(select(Tenant.id))).scalars().all()
        for tid in tenant_ids:
            await ensure_tenant_default_language(session, tid)
```

(The unused `get_default_tenant_id` import may remain; it is still used elsewhere in the file at `default_tenant_id = await get_default_tenant_id(session)` further down — verify before removing. If now unused, remove it from the import and the line above `yield`.)

- [ ] **Step 3: Update the seed test to expect all 10 languages**

In `tests/test_i18n_seed.py`, replace `test_ensure_tenant_default_language` with:

```python
async def test_ensure_tenant_default_language(session, default_tenant):
    """Seeds ru (default) + all extra langs idempotently, with exactly one default."""
    from quantuum.db.bootstrap import ensure_tenant_default_language
    from quantuum.i18n.langs import PLATFORM_LANGS

    tenant_id = default_tenant.id

    await ensure_tenant_default_language(session, tenant_id)

    result = await session.execute(
        select(TenantLanguage).where(TenantLanguage.tenant_id == tenant_id)
    )
    rows = {row.lang: row for row in result.scalars()}

    assert set(rows) == set(PLATFORM_LANGS), "all platform languages must be seeded"
    assert rows["ru"].is_default is True and rows["ru"].enabled is True
    assert rows["en"].is_default is False and rows["en"].enabled is True
    defaults = [r for r in rows.values() if r.is_default]
    assert len(defaults) == 1, f"Expected exactly 1 default, got {len(defaults)}"

    # Idempotency: run again; no duplicates, no default flip.
    await ensure_tenant_default_language(session, tenant_id)
    result2 = await session.execute(
        select(TenantLanguage).where(TenantLanguage.tenant_id == tenant_id)
    )
    rows2 = list(result2.scalars())
    assert len(rows2) == len(PLATFORM_LANGS)
    defaults2 = [r for r in rows2 if r.is_default]
    assert len(defaults2) == 1 and defaults2[0].lang == "ru"


async def test_ensure_tenant_default_language_no_second_default(session, default_tenant):
    """A tenant whose default is already 'en' must not gain a second default when
    backfilled with default_lang='ru'."""
    from quantuum.db.bootstrap import ensure_tenant_default_language

    tenant_id = default_tenant.id
    # Pre-existing 'en' default (mimics an onboarded tenant with a non-ru default).
    session.add(TenantLanguage(tenant_id=tenant_id, lang="en", enabled=True, is_default=True))
    await session.commit()

    await ensure_tenant_default_language(session, tenant_id)  # default_lang='ru'

    result = await session.execute(
        select(TenantLanguage).where(TenantLanguage.tenant_id == tenant_id)
    )
    rows = list(result.scalars())
    defaults = [r for r in rows if r.is_default]
    assert len(defaults) == 1 and defaults[0].lang == "en", "must keep the original default"
    assert any(r.lang == "ru" and not r.is_default for r in rows), "ru added as non-default"
```

- [ ] **Step 4: Update the picker tests (now seed 10 languages)**

In `tests/test_language_picker.py`, replace `test_picker_lists_enabled_langs_default_first` with:

```python
async def test_picker_lists_enabled_langs_default_first(session, default_tenant):
    from quantuum.db.bootstrap import ensure_tenant_default_language
    from quantuum.bot.ui.keyboards import language_picker_kb
    from quantuum.i18n.langs import PLATFORM_LANGS

    await ensure_tenant_default_language(session, default_tenant.id)
    await session.commit()

    markup = await language_picker_kb(default_tenant.id, action="setup")
    buttons = _inline(markup)

    codes = [LangCb.unpack(b.callback_data).lang for b in buttons]
    assert codes[0] == "ru", "default language must be first"
    assert set(codes) == set(PLATFORM_LANGS), "picker lists all enabled languages"
    assert codes[1:] == sorted(codes[1:]), "non-default languages are sorted"
    actions = {LangCb.unpack(b.callback_data).action for b in buttons}
    assert actions == {"setup"}
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_i18n_seed.py::test_ensure_tenant_default_language tests/test_i18n_seed.py::test_ensure_tenant_default_language_no_second_default tests/test_language_picker.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/db/bootstrap.py src/quantuum/api/app.py tests/test_i18n_seed.py tests/test_language_picker.py
git commit -m "feat(i18n): enable all platform languages for every tenant (guarded backfill)"
```

---

### Task 3: Translation package + merge into BASE_STRINGS + validation tests

**Files:**
- Create: `src/quantuum/i18n/translations/__init__.py`
- Modify: `src/quantuum/i18n/seed_strings.py` (append merge at end of file)
- Test: `tests/test_i18n_translations.py` (new)

- [ ] **Step 1: Create the auto-discovering translations package**

Create `src/quantuum/i18n/translations/__init__.py`:

```python
"""Per-language UI string translations for the non-base languages.

Each sibling module (e.g. ``es.py``) defines ``TRANSLATIONS: dict[str, str]``
mapping every BASE_STRINGS key to its translation. Modules are auto-discovered,
so adding a new ``<lang>.py`` registers it with no edits here.
"""

import importlib
import pkgutil

LANGUAGES: dict[str, dict[str, str]] = {}

for _info in pkgutil.iter_modules(__path__):
    _mod = importlib.import_module(f"{__name__}.{_info.name}")
    LANGUAGES[_info.name] = _mod.TRANSLATIONS
```

- [ ] **Step 2: Merge translations into BASE_STRINGS**

At the **end** of `src/quantuum/i18n/seed_strings.py` (after `BASE_STRINGS` is fully defined), append:

```python
# Merge the per-language translation files into BASE_STRINGS. Only keys that
# already exist in the ru/en base are populated; coverage is enforced by tests.
from quantuum.i18n.translations import LANGUAGES as _EXTRA_LANGUAGES  # noqa: E402

for _lang, _mapping in _EXTRA_LANGUAGES.items():
    for _key, _text in _mapping.items():
        if _key in BASE_STRINGS:
            BASE_STRINGS[_key][_lang] = _text
```

- [ ] **Step 3: Write the validation tests (pass vacuously now, gate each language later)**

Create `tests/test_i18n_translations.py`:

```python
"""Validation for per-language UI translations. These iterate over whatever
languages are currently present, so they pass before any translation exists and
must stay green as each language file is added."""

import re

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import LANGUAGES


def _tokens(s: str) -> set[str]:
    """The set of ``{placeholder}`` names in a string."""
    return set(re.findall(r"{(\w+)}", s))


def test_translation_files_cover_all_keys():
    base_keys = set(BASE_STRINGS)
    for lang, mapping in LANGUAGES.items():
        assert set(mapping) == base_keys, (
            f"{lang}: translation keys differ from BASE_STRINGS "
            f"(missing={base_keys - set(mapping)}, extra={set(mapping) - base_keys})"
        )


def test_translation_placeholder_parity():
    for lang, mapping in LANGUAGES.items():
        for key, text in mapping.items():
            assert _tokens(text) == _tokens(BASE_STRINGS[key]["en"]), (
                f"{lang}/{key}: placeholder tokens differ from English source"
            )
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_i18n_translations.py -v`
Expected: PASS (no language files yet → vacuous).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/i18n/translations/__init__.py src/quantuum/i18n/seed_strings.py tests/test_i18n_translations.py
git commit -m "feat(i18n): translation package with auto-discovery + BASE_STRINGS merge"
```

---

### Tasks 4–11: Translate UI strings — one task PER LANGUAGE

> **Controller note:** Dispatch these EIGHT tasks one at a time, each to a fresh **Sonnet** subagent (`model: sonnet`). They are identical except for the target language. Languages, in order: **es, fr, pt, it, de, tr, zh, hi**. Each task creates exactly one file and must keep `tests/test_i18n_translations.py` green.

**Files (per language `<lang>`):**
- Create: `src/quantuum/i18n/translations/<lang>.py`
- Validates against: `tests/test_i18n_translations.py` (from Task 3)

- [ ] **Step 1: Read the source strings**

Read `src/quantuum/i18n/seed_strings.py`. `BASE_STRINGS` maps each dotted key to `{"ru": ..., "en": ...}`. The English value is the translation source; the file header documents which keys contain `{placeholder}` variables.

- [ ] **Step 2: Write the translation file**

Create `src/quantuum/i18n/translations/<lang>.py` with this exact shape:

```python
"""<Language name> UI translations. Generated; keys mirror BASE_STRINGS."""

TRANSLATIONS = {
    "btn.generate": "<translation>",
    # ... one entry for EVERY key in BASE_STRINGS ...
}
```

**Hard rules (a reviewer and an automated test enforce these):**
1. Include **every** key present in `BASE_STRINGS` — no more, no fewer.
2. Copy every `{placeholder}` token **verbatim** — never translate or rename `{name}`, `{count}`, `{slug}`, etc. The set of `{...}` tokens in each value MUST equal the set in the English source.
3. Preserve any leading emoji, markdown (`*`, `_`, backticks), and newlines exactly as in the source.
4. Translate naturally and idiomatically into `<lang>`; keep astrology/esoteric terms accurate. Keep button labels short.
5. Do not add comments between entries, imports, or any code beyond the `TRANSLATIONS` dict.

- [ ] **Step 3: Run the validation tests**

Run: `uv run pytest tests/test_i18n_translations.py -v`
Expected: PASS (the new language is now covered by both checks).

- [ ] **Step 4: Commit**

```bash
git add src/quantuum/i18n/translations/<lang>.py
git commit -m "feat(i18n): <lang> UI translations"
```

---

### Task 12: Full-completeness test (every key has all 10 languages)

**Files:**
- Test: `tests/test_i18n_translations.py` (append)

- [ ] **Step 1: Write the completeness test**

Append to `tests/test_i18n_translations.py`:

```python
def test_every_key_has_all_platform_langs():
    from quantuum.i18n.langs import PLATFORM_LANGS

    expected = set(PLATFORM_LANGS)
    for key, langs in BASE_STRINGS.items():
        assert set(langs) == expected, (
            f"{key}: languages {set(langs)} != platform set {expected}"
        )
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_i18n_translations.py::test_every_key_has_all_platform_langs -v`
Expected: PASS (all 8 language files present after Tasks 4–11).

- [ ] **Step 3: Run the existing seed idempotency test (row-count sanity)**

Run: `uv run pytest tests/test_i18n_seed.py -v`
Expected: PASS — `test_ensure_base_strings_idempotent` computes its expected count from `BASE_STRINGS`, so the larger seed is handled automatically.

- [ ] **Step 4: Commit**

```bash
git add tests/test_i18n_translations.py
git commit -m "test(i18n): assert every UI key defines all 10 platform languages"
```

---

### Task 13: Blueprint `lang` column + migration + `create_blueprint(lang=...)`

**Files:**
- Modify: `src/quantuum/db/models.py` (`Blueprint`, after the `status` field ~line 147)
- Create: `alembic/versions/f6a7b8c9d0e1_blueprint_lang.py`
- Modify: `src/quantuum/domain/blueprints.py` (`create_blueprint`, lines 8-20)
- Test: `tests/test_blueprints_service.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_blueprints_service.py` (import helpers it already uses; if it lacks a setup, use the inline form below):

```python
async def test_create_blueprint_stores_lang(session, default_tenant):
    from datetime import date, time
    from decimal import Decimal
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.domain.blueprints import create_blueprint, get_blueprint
    from quantuum.domain.natal_profiles import upsert_natal_profile

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="42")
    profile = await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    bp = await create_blueprint(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, lang="es",
    )
    reloaded = await get_blueprint(session, bp.id)
    assert reloaded.lang == "es"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_blueprints_service.py::test_create_blueprint_stores_lang -v`
Expected: FAIL (`create_blueprint() got an unexpected keyword argument 'lang'` / no `lang` attribute).

- [ ] **Step 3: Add the model column**

In `src/quantuum/db/models.py`, in `class Blueprint`, add after `status: str = "pending" ...`:

```python
    lang: str | None = None
```

- [ ] **Step 4: Add the `lang` parameter to `create_blueprint`**

In `src/quantuum/domain/blueprints.py`, replace `create_blueprint`:

```python
async def create_blueprint(
    session, *, tenant_id: int, account_id: int, natal_profile_id: int, lang: str | None = None
) -> Blueprint:
    blueprint = Blueprint(
        tenant_id=tenant_id,
        account_id=account_id,
        natal_profile_id=natal_profile_id,
        lang=lang,
        status="pending",
    )
    session.add(blueprint)
    await session.commit()
    await session.refresh(blueprint)
    return blueprint
```

- [ ] **Step 5: Create the alembic migration**

Create `alembic/versions/f6a7b8c9d0e1_blueprint_lang.py`:

```python
"""blueprint lang column

Revision ID: f6a7b8c9d0e1
Revises: d9e0f1a2b3c4
Create Date: 2026-05-22 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "blueprints",
        sa.Column("lang", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("blueprints", "lang")
```

- [ ] **Step 6: Run the test**

Run: `uv run pytest tests/test_blueprints_service.py::test_create_blueprint_stores_lang -v`
Expected: PASS.

- [ ] **Step 7: Verify the migration chain is linear**

Run: `uv run alembic heads`
Expected: a single head `f6a7b8c9d0e1 (head)`.

- [ ] **Step 8: Commit**

```bash
git add src/quantuum/db/models.py src/quantuum/domain/blueprints.py alembic/versions/f6a7b8c9d0e1_blueprint_lang.py tests/test_blueprints_service.py
git commit -m "feat(blueprint): add lang column + create_blueprint(lang)"
```

---

### Task 14: Capture blueprint language at request time (bot + API)

**Files:**
- Modify: `src/quantuum/bot/handlers/generate.py` (`request_blueprint_for_account` lines ~33-58; `run_generate` ~62-70)
- Modify: `src/quantuum/api/routes/me.py` (`create_blueprint_route` lines 112-124)
- Test: `tests/test_api_blueprints.py`

- [ ] **Step 1: Write the failing API test**

Append to `tests/test_api_blueprints.py` (follow the file's existing client/auth fixtures; the assertion is the key part):

```python
async def test_create_blueprint_route_stores_resolved_lang(session, default_tenant, monkeypatch):
    """The blueprint row stores the account's resolved language."""
    from datetime import date, time
    from decimal import Decimal
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.domain.natal_profiles import upsert_natal_profile
    from quantuum.db.bootstrap import ensure_tenant_default_language
    from quantuum.domain.blueprints import get_blueprint
    from quantuum.api.routes import me as me_routes

    await ensure_tenant_default_language(session, default_tenant.id)
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="99")
    acc.preferred_lang = "fr"
    session.add(acc)
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    await session.commit()

    # Avoid real enqueue.
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(me_routes.enqueue, "enqueue_blueprint", _noop)

    bp = await me_routes.create_blueprint_route(account=acc, session=session)
    reloaded = await get_blueprint(session, bp.id)
    assert reloaded.lang == "fr"
```

> If `create_blueprint_route`'s signature/returns differ from a direct call (e.g. it returns a Pydantic model), assert on the persisted row via `get_blueprint` using the id from the response. Keep the `preferred_lang == "fr"` → stored `lang == "fr"` assertion.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_api_blueprints.py::test_create_blueprint_route_stores_resolved_lang -v`
Expected: FAIL (stored `lang` is `None`).

- [ ] **Step 3: Resolve + store lang in the API route**

In `src/quantuum/api/routes/me.py`, `create_blueprint_route` already has `account` and `session`. `resolve_lang` is already imported. Replace the `create_blueprint(...)` call:

```python
    lang = await resolve_lang(
        session,
        tenant_id=account.tenant_id,
        preferred_lang=account.preferred_lang,
        tg_language_code=None,
    )
    blueprint = await create_blueprint(
        session, tenant_id=account.tenant_id, account_id=account.id,
        natal_profile_id=profile.id, lang=lang,
    )
```

- [ ] **Step 4: Thread lang through the bot handler**

In `src/quantuum/bot/handlers/generate.py`, change `request_blueprint_for_account` to accept and pass `lang`:

```python
async def request_blueprint_for_account(
    session,
    *,
    account: Account,
    chat_id: int,
    enqueue: Callable[[int, int | None, int | None], Awaitable[None]],
    lang: str | None = None,
) -> tuple[str, int | None]:
```

and within it, in the `create_blueprint(...)` call, add `lang=lang`:

```python
    blueprint = await create_blueprint(
        session, tenant_id=account.tenant_id, account_id=account.id,
        natal_profile_id=profile.id, lang=lang,
    )
```

In `run_generate`, pass the current UI language:

```python
        status, _ = await request_blueprint_for_account(
            session, account=account, chat_id=chat_id, enqueue=enqueue_blueprint,
            lang=i18n.lang,
        )
```

- [ ] **Step 5: Run the test**

Run: `uv run pytest tests/test_api_blueprints.py::test_create_blueprint_route_stores_resolved_lang -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/bot/handlers/generate.py src/quantuum/api/routes/me.py tests/test_api_blueprints.py
git commit -m "feat(blueprint): capture user language at request time (bot + API)"
```

---

### Task 15: Generate the Blueprint in the chosen language

**Files:**
- Modify: `src/quantuum/llm/blueprint_polish.py`
- Modify: `src/quantuum/llm/prompts/blueprint_writer.txt` (line 26)
- Modify: `src/quantuum/tasks/blueprint.py` (the `polish_blueprint(...)` call ~lines 37-42)
- Test: `tests/test_task_blueprint.py` (and a small llm test)

- [ ] **Step 1: Write the failing generator test**

Create `tests/test_blueprint_polish_llm.py`:

```python
from quantuum.llm.base import LLMResult
from quantuum.llm.blueprint_polish import polish_blueprint


class CaptureLLM:
    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.system = system
        self.user = user
        return LLMResult(text="BP", tokens_in=1, tokens_out=2, model=model)


async def test_polish_blueprint_passes_language():
    client = CaptureLLM()
    result = await polish_blueprint(
        client, "CALC_MD", lang="es", model="m", temperature=0.4, max_tokens=100
    )
    assert result.text == "BP"
    assert "CALC_MD" in client.user
    assert "Answer in language: es." in client.user
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_blueprint_polish_llm.py -v`
Expected: FAIL (`polish_blueprint() got an unexpected keyword argument 'lang'`).

- [ ] **Step 3: Add `lang` to `polish_blueprint`**

Replace `polish_blueprint` in `src/quantuum/llm/blueprint_polish.py`:

```python
async def polish_blueprint(client, calc_md, *, lang, model, temperature, max_tokens):
    system = PROMPT_PATH.read_text()
    user = "\n".join(
        [
            "Transform this calculated Markdown into the final premium Quantuum SoulMap Blueprint.",
            f"Answer in language: {lang}.",
            "",
            "CALCULATED MARKDOWN:",
            calc_md,
        ]
    )
    return await client.complete(
        system=system,
        user=user,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
```

- [ ] **Step 4: Update the prompt's language instruction**

In `src/quantuum/llm/prompts/blueprint_writer.txt`, replace line 26:

```
- Write in English unless the source Markdown is clearly in another language.
```

with:

```
- Write in the language requested in the user message.
```

- [ ] **Step 5: Thread lang in the blueprint task**

In `src/quantuum/tasks/blueprint.py`, add the import near the top:

```python
from quantuum.i18n.strings import get_tenant_default_lang
```

Then, inside `blueprint_generate`, just before the `polish_blueprint(...)` call (where `bp` and `tenant_id` are in scope), resolve the language and pass it:

```python
                lang = bp.lang or await get_tenant_default_lang(session, tenant_id) or "ru"
                result = await polish_blueprint(
                    llm_client,
                    calc_md,
                    lang=lang,
                    model=cfg["model"],
                    temperature=cfg["temperature"],
                    max_tokens=cfg["max_tokens"],
                )
```

- [ ] **Step 6: Write a task test that the stored lang reaches the LLM**

Append to `tests/test_task_blueprint.py`:

```python
async def test_blueprint_generate_passes_stored_lang(session, default_tenant):
    acc, _ = await _setup(session, default_tenant.id)
    from quantuum.domain.blueprints import create_blueprint
    from quantuum.domain.natal_profiles import get_natal_profile
    profile = await get_natal_profile(session, acc.id)
    bp = await create_blueprint(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, lang="de",
    )

    capture = {}

    class CaptureLLM:
        async def complete(self, *, system, user, model, temperature, max_tokens):
            capture["user"] = user
            from quantuum.llm.base import LLMResult
            return LLMResult(text="X", tokens_in=1, tokens_out=1, model="m")

    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *a):
            return False

    ctx = {"sessionmaker": _Maker(), "llm_client": CaptureLLM()}
    await blueprint_generate(ctx, bp.id, chat_id=None, request_id=None)
    assert "Answer in language: de." in capture["user"]
```

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/test_blueprint_polish_llm.py tests/test_task_blueprint.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/quantuum/llm/blueprint_polish.py src/quantuum/llm/prompts/blueprint_writer.txt src/quantuum/tasks/blueprint.py tests/test_blueprint_polish_llm.py tests/test_task_blueprint.py
git commit -m "feat(blueprint): generate the reading in the user's chosen language"
```

---

### Task 16: Generate the Q&A answer in the chosen language

**Files:**
- Modify: `src/quantuum/llm/qa_answer.py`
- Modify: `src/quantuum/llm/prompts/qa_astrologer.txt` (line 18)
- Modify: `src/quantuum/tasks/qa.py` (the `qa_answer(...)` call)
- Test: `tests/test_qa_answer.py`, `tests/test_task_qa.py`

- [ ] **Step 1: Write the failing generator test**

Append to `tests/test_qa_answer.py` (or create it mirroring `test_transit_report_llm.py` if minimal):

```python
async def test_qa_answer_passes_language():
    from quantuum.llm.base import LLMResult
    from quantuum.llm.qa_answer import qa_answer

    class CaptureLLM:
        async def complete(self, *, system, user, model, temperature, max_tokens):
            self.user = user
            return LLMResult(text="A", tokens_in=1, tokens_out=2, model=model)

    client = CaptureLLM()
    result = await qa_answer(
        client, "CALC_MD", "What is my path?", lang="it",
        model="m", temperature=0.4, max_tokens=100,
    )
    assert result.text == "A"
    assert "What is my path?" in client.user
    assert "Answer in language: it." in client.user
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_qa_answer.py::test_qa_answer_passes_language -v`
Expected: FAIL (`qa_answer() got an unexpected keyword argument 'lang'`).

- [ ] **Step 3: Add `lang` to `qa_answer`**

Replace `qa_answer` in `src/quantuum/llm/qa_answer.py`:

```python
async def qa_answer(client, calc_md, question, *, lang, model, temperature, max_tokens):
    system = PROMPT_PATH.read_text()
    user = "\n".join(
        [
            "Answer the user's question using only the calculated chart below.",
            f"Answer in language: {lang}.",
            "",
            "CALCULATED CHART:",
            calc_md,
            "",
            "QUESTION:",
            question,
        ]
    )
    return await client.complete(
        system=system,
        user=user,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
```

- [ ] **Step 4: Update the prompt's language instruction**

In `src/quantuum/llm/prompts/qa_astrologer.txt`, replace line 18:

```
- Answer in the SAME language as the person's question.
```

with:

```
- Answer in the language requested in the user message.
```

- [ ] **Step 5: Thread lang in the qa task**

In `src/quantuum/tasks/qa.py`, add the import near the top:

```python
from quantuum.i18n.strings import get_tenant_default_lang
```

Then replace the `qa_answer(...)` call (where `qa` and `tenant_id` are in scope):

```python
            lang = qa.lang or await get_tenant_default_lang(session, tenant_id) or "ru"
            result = await qa_answer(
                llm_client,
                calc_md,
                qa.question,
                lang=lang,
                model=cfg["model"],
                temperature=cfg["temperature"],
                max_tokens=cfg["max_tokens"],
            )
```

- [ ] **Step 6: Write a task test that the stored lang reaches the LLM**

Append to `tests/test_task_qa.py` (mirror its existing setup helpers; key assertion below):

```python
async def test_qa_generate_passes_stored_lang(session, default_tenant):
    from datetime import date, time
    from decimal import Decimal
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.domain.natal_profiles import upsert_natal_profile
    from quantuum.domain.qa import create_qa
    from quantuum.llm.base import LLMResult
    from quantuum.tasks.qa import qa_generate

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="5")
    profile = await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    qa = await create_qa(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, question="Q?", lang="pt",
    )

    capture = {}

    class CaptureLLM:
        async def complete(self, *, system, user, model, temperature, max_tokens):
            capture["user"] = user
            return LLMResult(text="X", tokens_in=1, tokens_out=1, model="m")

    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *a):
            return False

    ctx = {"sessionmaker": _Maker(), "llm_client": CaptureLLM()}
    await qa_generate(ctx, qa.id, chat_id=None, request_id=None)
    assert "Answer in language: pt." in capture["user"]
```

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/test_qa_answer.py tests/test_task_qa.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/quantuum/llm/qa_answer.py src/quantuum/llm/prompts/qa_astrologer.txt src/quantuum/tasks/qa.py tests/test_qa_answer.py tests/test_task_qa.py
git commit -m "feat(qa): answer in the user's chosen language"
```

---

### Task 17: Full-suite verification

- [ ] **Step 1: Run the entire test suite**

Run: `uv run pytest -q`
Expected: all green. If any pre-existing test asserted ru/en-only behavior that the new defaults change, fix the assertion to use `PLATFORM_LANGS` (do not weaken behavior).

- [ ] **Step 2: Lint**

Run: `uv run ruff check src tests`
Expected: clean.

- [ ] **Step 3: Final commit (if any fixups)**

```bash
git add -A
git commit -m "test(i18n): suite green for 10-language support"
```

---

## Self-Review

**Spec coverage:**
- 10 languages defined → Task 1 (`langs.py`), Task 2 (enablement). ✅
- Native picker labels + layout → Task 1. ✅
- All bots get all langs, ru default, existing backfilled → Task 2 (backfill loop + double-default guard). ✅
- All 170 keys × 8 langs, baked, Sonnet subagents → Tasks 3–11. ✅
- No cache invalidation needed (new langs only) → inherent (no edits to existing rows); covered by existing seed idempotency test in Task 12. ✅
- Completeness + placeholder-parity guards → Tasks 3 & 12. ✅
- Blueprint localized (column, capture at creation, generator, prompt, task) → Tasks 13–15. ✅
- Q&A localized (thread stored lang, generator, prompt, task) → Task 16. ✅
- Transits/daily unchanged → not touched. ✅
- Legacy null `lang` fallback → Tasks 15 & 16 (`bp.lang or default or "ru"`). ✅

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N". The per-language tasks are intentionally one parameterized spec with full instructions present; the only variable is the language code.

**Type/signature consistency:**
- `create_blueprint(..., lang: str | None = None)` — defined Task 13, called Task 14.
- `request_blueprint_for_account(..., lang=None)` — Task 14.
- `polish_blueprint(client, calc_md, *, lang, ...)` — Task 15.
- `qa_answer(client, calc_md, question, *, lang, ...)` — Task 16.
- `PLATFORM_LANGS` / `EXTRA_LANGS` / `DEFAULT_LANG` — Task 1, used in Tasks 2 & 12.
- `LANGUAGES` (translations) — Task 3, populated Tasks 4–11.
- Migration `f6a7b8c9d0e1` ← `d9e0f1a2b3c4` (current head). ✅
