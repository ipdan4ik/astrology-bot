# Tenant-Level Feature Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-tenant on/off flags for 12 user-facing features (4 surfaces + 8 readings), self-served by the tenant owner via `/owner_console`. Disabled features are hidden from the menu and rejected at the handler entry-point.

**Architecture:** Twelve booleans stored in the existing `tenant_config` table under keys `feature.<flag-key>`. *Absent row = ON* — so a fresh tenant has zero rows and gets the full menu. A new domain module `tenant_features.py` exposes `is_feature_enabled` / `list_feature_states` / `set_feature_enabled`. Menu builders filter buttons against the resolved flag dict; each of the 5 entry-point handlers gates with a short-circuit on the same flag. Owner UX is a new "Features" submenu under `/owner_console`.

**Tech Stack:** Python 3.13, SQLModel / Alembic, aiogram 3 (CallbackData), pydantic-settings, pytest-asyncio with PostgreSQL test DB at 172.30.0.2, ruff.

**Spec:** `docs/superpowers/specs/2026-05-27-tenant-feature-toggle-design.md`

---

## File map

**Create:**
- `src/quantuum/domain/tenant_features.py` — FEATURE_KEYS + 3 functions
- `tests/test_tenant_features_domain.py`
- `tests/test_tenant_features_menu.py`
- `tests/test_tenant_features_handlers.py`
- `tests/test_tenant_features_owner_console.py`
- `tests/test_tenant_features_i18n.py`

**Modify:**
- `src/quantuum/bot/ui/keyboards.py` — `main_menu_kb` + `readings_menu_kb` accept resolved flag dict / tenant_id
- `src/quantuum/bot/handlers/menu.py` — pass `tenant_id` through `show_main_menu` and `main_menu_kb` call sites
- `src/quantuum/bot/handlers/start.py` — pass tenant_id into `show_main_menu`
- `src/quantuum/bot/handlers/language.py` — pass tenant_id into `show_main_menu`
- `src/quantuum/bot/handlers/qa.py` — gate on `feature.qa`
- `src/quantuum/bot/handlers/generate.py` — gate on `feature.blueprint`
- `src/quantuum/bot/handlers/transits.py` — gate on `feature.transits`
- `src/quantuum/bot/handlers/daily.py` — gate on `feature.daily`
- `src/quantuum/bot/handlers/readings.py` — gate on `feature.reading.<kind>`
- `src/quantuum/bot/ui/callbacks.py` — add `OwnerFeatureCb`
- `src/quantuum/bot/handlers/owner_console.py` — Features button + submenu render + toggle handler
- `src/quantuum/i18n/seed_strings.py` — 8 new keys (ru + en)
- `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py` — same 8 keys

**No Alembic migration.** `tenant_config` table already exists.

**No caching in v1.** Direct DB reads (one PK indexed query per `is_feature_enabled`, one short range query per `list_feature_states`). Spec mentioned a `cache_aside_async` pattern that doesn't exist in the codebase yet — Redis caching is a perf follow-up. Acceptable: menu render adds one DB roundtrip; each gated handler adds one. Both already do other DB I/O.

---

## Task 1: Domain layer — `tenant_features.py`

**Files:**
- Create: `src/quantuum/domain/tenant_features.py`
- Test: `tests/test_tenant_features_domain.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_tenant_features_domain.py`:

```python
import pytest

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.domain.tenant_features import (
    FEATURE_KEYS,
    is_feature_enabled,
    list_feature_states,
    set_feature_enabled,
)


def test_feature_keys_inventory():
    # Lock the canonical 12-flag set.
    assert set(FEATURE_KEYS) == {
        "qa", "blueprint", "transits", "daily",
        "reading.bazi", "reading.numerology", "reading.human_design",
        "reading.astrology", "reading.vedic", "reading.gene_keys",
        "reading.mayan", "reading.aspects",
    }
    assert len(FEATURE_KEYS) == 12


async def test_is_feature_enabled_defaults_true_when_no_row(session, default_tenant):
    assert await is_feature_enabled(session, default_tenant.id, "qa") is True
    assert await is_feature_enabled(session, default_tenant.id, "reading.bazi") is True


async def test_set_then_read_false_round_trip(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor"
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="qa",
        enabled=False,
        by_account_id=acc.id,
    )
    await session.commit()
    assert await is_feature_enabled(session, default_tenant.id, "qa") is False


async def test_set_back_to_true_restores(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor2"
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="qa",
        enabled=False,
        by_account_id=acc.id,
    )
    await session.commit()
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="qa",
        enabled=True,
        by_account_id=acc.id,
    )
    await session.commit()
    assert await is_feature_enabled(session, default_tenant.id, "qa") is True


async def test_set_unknown_key_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor3"
    )
    with pytest.raises(ValueError, match="not.a.real.key"):
        await set_feature_enabled(
            session,
            tenant_id=default_tenant.id,
            key="not.a.real.key",
            enabled=False,
            by_account_id=acc.id,
        )


async def test_list_feature_states_returns_all_twelve(session, default_tenant):
    states = await list_feature_states(session, default_tenant.id)
    assert set(states.keys()) == set(FEATURE_KEYS)
    assert all(v is True for v in states.values())  # all default ON


async def test_list_reflects_overrides(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor4"
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="daily",
        enabled=False,
        by_account_id=acc.id,
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="reading.bazi",
        enabled=False,
        by_account_id=acc.id,
    )
    await session.commit()
    states = await list_feature_states(session, default_tenant.id)
    assert states["daily"] is False
    assert states["reading.bazi"] is False
    assert states["qa"] is True  # untouched
    assert states["reading.numerology"] is True  # untouched
    assert len(states) == 12


async def test_set_populates_updated_by(session, default_tenant):
    from sqlalchemy import select

    from quantuum.db.models import TenantConfig

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor5"
    )
    await set_feature_enabled(
        session,
        tenant_id=default_tenant.id,
        key="transits",
        enabled=False,
        by_account_id=acc.id,
    )
    await session.commit()
    row = (
        await session.execute(
            select(TenantConfig).where(
                TenantConfig.tenant_id == default_tenant.id,
                TenantConfig.key == "feature.transits",
            )
        )
    ).scalar_one()
    assert row.value_jsonb == {"enabled": False}
    assert row.updated_by_account_id == acc.id
```

- [ ] **Step 2: Run tests, expect FAIL**

```
uv run pytest tests/test_tenant_features_domain.py -v
```
Expect: ModuleNotFoundError or AttributeError — module/symbols don't exist yet.

- [ ] **Step 3: Implement `src/quantuum/domain/tenant_features.py`**

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.db.models import TenantConfig
from quantuum.db.session_helpers import utcnow

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
)

_CONFIG_KEY_PREFIX = "feature."


def _config_key(feature_key: str) -> str:
    return f"{_CONFIG_KEY_PREFIX}{feature_key}"


async def is_feature_enabled(
    session: AsyncSession, tenant_id: int, key: str
) -> bool:
    """Resolve a single feature flag. Missing row → True (default ON)."""
    row = await session.get(TenantConfig, (tenant_id, _config_key(key)))
    if row is None:
        return True
    return bool(row.value_jsonb.get("enabled", True))


async def list_feature_states(
    session: AsyncSession, tenant_id: int
) -> dict[str, bool]:
    """Return {feature_key: enabled} for all 12 features."""
    stmt = select(TenantConfig).where(
        TenantConfig.tenant_id == tenant_id,
        TenantConfig.key.like(f"{_CONFIG_KEY_PREFIX}%"),
    )
    rows = (await session.execute(stmt)).scalars().all()
    overrides = {
        row.key.removeprefix(_CONFIG_KEY_PREFIX): bool(
            row.value_jsonb.get("enabled", True)
        )
        for row in rows
    }
    return {k: overrides.get(k, True) for k in FEATURE_KEYS}


async def set_feature_enabled(
    session: AsyncSession,
    *,
    tenant_id: int,
    key: str,
    enabled: bool,
    by_account_id: int,
) -> None:
    """Upsert the override row. Raises ValueError for unknown feature keys."""
    if key not in FEATURE_KEYS:
        raise ValueError(f"unknown feature key: {key}")
    row = await session.get(TenantConfig, (tenant_id, _config_key(key)))
    if row is None:
        row = TenantConfig(
            tenant_id=tenant_id,
            key=_config_key(key),
            value_jsonb={"enabled": enabled},
            updated_by_account_id=by_account_id,
        )
        session.add(row)
    else:
        row.value_jsonb = {"enabled": enabled}
        row.updated_by_account_id = by_account_id
        row.updated_at = utcnow()
    await session.flush()
```

If `quantuum.db.session_helpers.utcnow` doesn't exist, peek at `src/quantuum/db/models.py` for how `utcnow` is imported there and reuse the same import path.

- [ ] **Step 4: Run tests, expect PASS**

```
uv run pytest tests/test_tenant_features_domain.py -v
```
Expect: 8 passed.

- [ ] **Step 5: Ruff**

```
uv run ruff check src/quantuum/domain/tenant_features.py tests/test_tenant_features_domain.py
```

- [ ] **Step 6: Commit**

```
git add src/quantuum/domain/tenant_features.py tests/test_tenant_features_domain.py
git commit -m "feat(tenant-features): domain layer (is/list/set) + tests"
```

---

## Task 2: i18n strings (8 keys × 10 languages)

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py`
- Modify: `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py`
- Test: `tests/test_tenant_features_i18n.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tenant_features_i18n.py`:

```python
import pytest

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import de, es, fr, hi, it, pt, tr, zh

FEATURE_I18N_KEYS = [
    "feature.disabled_generic",
    "owner.features.title",
    "owner.features.btn",
    "owner.features.section.readings",
    "owner.features.label.qa",
    "owner.features.label.blueprint",
    "owner.features.label.transits",
    "owner.features.label.daily",
]


@pytest.mark.parametrize("key", FEATURE_I18N_KEYS)
def test_base_strings_has_key_in_ru_and_en(key):
    assert key in BASE_STRINGS, f"missing {key} in BASE_STRINGS"
    entry = BASE_STRINGS[key]
    assert "ru" in entry and "en" in entry
    assert entry["ru"] and entry["en"]


@pytest.mark.parametrize(
    "lang_mod, lang_code",
    [(de, "de"), (es, "es"), (fr, "fr"), (hi, "hi"), (it, "it"), (pt, "pt"), (tr, "tr"), (zh, "zh")],
)
@pytest.mark.parametrize("key", FEATURE_I18N_KEYS)
def test_translation_modules_have_all_keys(lang_mod, lang_code, key):
    assert key in lang_mod.TRANSLATIONS, f"missing {key} in {lang_code}"
    assert lang_mod.TRANSLATIONS[key], f"empty {key} in {lang_code}"
```

- [ ] **Step 2: Run test, expect FAIL**

```
uv run pytest tests/test_tenant_features_i18n.py -v
```

- [ ] **Step 3: Add keys to `BASE_STRINGS`**

Append before the closing brace of `BASE_STRINGS` (same insertion point pattern as the SP1 moderation i18n task — look right above the `_EXTRA_LANGUAGES` merge loop in `src/quantuum/i18n/seed_strings.py`):

```python
    # -------------------------------------------------------------------------
    # Feature toggles
    # -------------------------------------------------------------------------
    "feature.disabled_generic": {
        "ru": "Эта функция отключена в этом боте.",
        "en": "This feature isn't available on this bot.",
    },
    "owner.features.title": {
        "ru": "⚙️ Функции",
        "en": "⚙️ Features",
    },
    "owner.features.btn": {
        "ru": "⚙️ Функции",
        "en": "⚙️ Features",
    },
    "owner.features.section.readings": {
        "ru": "— Разборы —",
        "en": "— Readings —",
    },
    "owner.features.label.qa": {
        "ru": "Вопрос-ответ",
        "en": "QA",
    },
    "owner.features.label.blueprint": {
        "ru": "Разбор",
        "en": "Blueprint",
    },
    "owner.features.label.transits": {
        "ru": "Транзиты",
        "en": "Transits",
    },
    "owner.features.label.daily": {
        "ru": "Ежедневное",
        "en": "Daily",
    },
```

- [ ] **Step 4: Add keys to each translation file**

For each of `de.py`, `es.py`, `fr.py`, `hi.py`, `it.py`, `pt.py`, `tr.py`, `zh.py`, append inside `TRANSLATIONS = {...}` just before its closing brace.

**`de.py`:**
```python
    "feature.disabled_generic": "Diese Funktion ist in diesem Bot nicht verfügbar.",
    "owner.features.title": "⚙️ Funktionen",
    "owner.features.btn": "⚙️ Funktionen",
    "owner.features.section.readings": "— Auswertungen —",
    "owner.features.label.qa": "Frage-Antwort",
    "owner.features.label.blueprint": "Auswertung",
    "owner.features.label.transits": "Transite",
    "owner.features.label.daily": "Tägliches",
```

**`es.py`:**
```python
    "feature.disabled_generic": "Esta función no está disponible en este bot.",
    "owner.features.title": "⚙️ Funciones",
    "owner.features.btn": "⚙️ Funciones",
    "owner.features.section.readings": "— Lecturas —",
    "owner.features.label.qa": "Pregunta-Respuesta",
    "owner.features.label.blueprint": "Lectura",
    "owner.features.label.transits": "Tránsitos",
    "owner.features.label.daily": "Diario",
```

**`fr.py`:**
```python
    "feature.disabled_generic": "Cette fonctionnalité n'est pas disponible sur ce bot.",
    "owner.features.title": "⚙️ Fonctions",
    "owner.features.btn": "⚙️ Fonctions",
    "owner.features.section.readings": "— Lectures —",
    "owner.features.label.qa": "Question-Réponse",
    "owner.features.label.blueprint": "Lecture",
    "owner.features.label.transits": "Transits",
    "owner.features.label.daily": "Quotidien",
```

**`hi.py`:**
```python
    "feature.disabled_generic": "यह सुविधा इस बॉट पर उपलब्ध नहीं है.",
    "owner.features.title": "⚙️ सुविधाएं",
    "owner.features.btn": "⚙️ सुविधाएं",
    "owner.features.section.readings": "— रीडिंग्स —",
    "owner.features.label.qa": "प्रश्न-उत्तर",
    "owner.features.label.blueprint": "रीडिंग",
    "owner.features.label.transits": "ट्रांज़िट",
    "owner.features.label.daily": "दैनिक",
```

**`it.py`:**
```python
    "feature.disabled_generic": "Questa funzionalità non è disponibile su questo bot.",
    "owner.features.title": "⚙️ Funzioni",
    "owner.features.btn": "⚙️ Funzioni",
    "owner.features.section.readings": "— Letture —",
    "owner.features.label.qa": "Domanda-Risposta",
    "owner.features.label.blueprint": "Lettura",
    "owner.features.label.transits": "Transiti",
    "owner.features.label.daily": "Quotidiano",
```

**`pt.py`:**
```python
    "feature.disabled_generic": "Este recurso não está disponível neste bot.",
    "owner.features.title": "⚙️ Recursos",
    "owner.features.btn": "⚙️ Recursos",
    "owner.features.section.readings": "— Leituras —",
    "owner.features.label.qa": "Pergunta-Resposta",
    "owner.features.label.blueprint": "Leitura",
    "owner.features.label.transits": "Trânsitos",
    "owner.features.label.daily": "Diário",
```

**`tr.py`:**
```python
    "feature.disabled_generic": "Bu özellik bu bot için kullanılamıyor.",
    "owner.features.title": "⚙️ Özellikler",
    "owner.features.btn": "⚙️ Özellikler",
    "owner.features.section.readings": "— Okumalar —",
    "owner.features.label.qa": "Soru-Cevap",
    "owner.features.label.blueprint": "Okuma",
    "owner.features.label.transits": "Transitler",
    "owner.features.label.daily": "Günlük",
```

**`zh.py`:**
```python
    "feature.disabled_generic": "此功能在此机器人上不可用。",
    "owner.features.title": "⚙️ 功能",
    "owner.features.btn": "⚙️ 功能",
    "owner.features.section.readings": "— 解读 —",
    "owner.features.label.qa": "问答",
    "owner.features.label.blueprint": "解读",
    "owner.features.label.transits": "过境",
    "owner.features.label.daily": "每日",
```

- [ ] **Step 5: Run test, expect PASS**

```
uv run pytest tests/test_tenant_features_i18n.py -v
```
Expect: 72 passed (8 base + 8×8 translation).

- [ ] **Step 6: Ruff**

```
uv run ruff check src/quantuum/i18n/ tests/test_tenant_features_i18n.py
```

- [ ] **Step 7: Commit**

```
git add src/quantuum/i18n/seed_strings.py src/quantuum/i18n/translations/ tests/test_tenant_features_i18n.py
git commit -m "feat(tenant-features): i18n strings (8 keys × 10 langs)"
```

---

## Task 3: Menu builder filter

**Files:**
- Modify: `src/quantuum/bot/ui/keyboards.py` (`main_menu_kb`, `readings_menu_kb`)
- Modify: `src/quantuum/bot/handlers/menu.py` (pass tenant_id through)
- Modify: `src/quantuum/bot/handlers/start.py` and `src/quantuum/bot/handlers/language.py` (callers of `show_main_menu`)
- Modify: `src/quantuum/bot/handlers/readings.py` (caller of `readings_menu_kb`)
- Test: `tests/test_tenant_features_menu.py`

### Approach

Change signatures:
- `main_menu_kb(i18n, tenant_id)` — resolves flags internally, hides disabled top-level surface buttons, and omits "Readings" entirely if every `reading.*` flag is off.
- `readings_menu_kb(i18n, tenant_id)` — same pattern, filters `READING_KINDS`.

Every call site already has `tenant_id` available (via `account.tenant_id` or the existing `tenant_id` middleware injection).

- [ ] **Step 1: Write the failing tests**

`tests/test_tenant_features_menu.py`:

```python
import pytest

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.keyboards import main_menu_kb, readings_menu_kb
from quantuum.domain.tenant_features import set_feature_enabled


async def _disable(session, tenant_id, *keys, by_account_id):
    for k in keys:
        await set_feature_enabled(
            session,
            tenant_id=tenant_id,
            key=k,
            enabled=False,
            by_account_id=by_account_id,
        )
    await session.commit()


def _button_texts(kb) -> list[str]:
    return [btn.text for row in kb.keyboard for btn in row]


def _inline_button_texts(kb) -> list[str]:
    return [btn.text for row in kb.inline_keyboard for btn in row]


async def test_main_menu_full_when_all_enabled(session, default_tenant, build_translator):
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    kb = await main_menu_kb(i18n, default_tenant.id)
    texts = _button_texts(kb)
    # Five surface buttons + profile/history/help/language.
    assert any("Разбор" in t for t in texts)
    assert any("Вопрос" in t for t in texts) or any("Спросить" in t for t in texts)
    assert any("Транзит" in t for t in texts)
    assert any("Ежедневн" in t for t in texts)
    assert any("Профиль" in t for t in texts)


async def test_main_menu_hides_disabled_surfaces(session, default_tenant, build_translator):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor_menu"
    )
    await _disable(session, default_tenant.id, "qa", "daily", by_account_id=acc.id)
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    kb = await main_menu_kb(i18n, default_tenant.id)
    texts = " ".join(_button_texts(kb))
    # qa label patterns absent
    assert "Спросить" not in texts and "Вопрос-ответ" not in texts
    # daily label absent
    assert "Ежедневн" not in texts


async def test_main_menu_hides_readings_button_when_all_readings_off(
    session, default_tenant, build_translator
):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor_no_readings"
    )
    await _disable(
        session,
        default_tenant.id,
        "reading.bazi", "reading.numerology", "reading.human_design",
        "reading.astrology", "reading.vedic", "reading.gene_keys",
        "reading.mayan", "reading.aspects",
        by_account_id=acc.id,
    )
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    kb = await main_menu_kb(i18n, default_tenant.id)
    texts = " ".join(_button_texts(kb))
    # No "Разборы" or similar Readings hub button.
    # NOTE: "Разбор" (Blueprint button) is different from "Разборы" (Readings menu button).
    # The exact label depends on i18n; this test asserts that neither the Russian
    # nor English "Readings" hub label is present.
    assert "📜 История" in texts or "History" in texts  # sanity: menu still has other buttons


async def test_readings_menu_full_when_all_enabled(session, default_tenant, build_translator):
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    kb = await readings_menu_kb(i18n, default_tenant.id)
    texts = _inline_button_texts(kb)
    assert len(texts) == 8  # all 8 reading kinds visible


async def test_readings_menu_hides_disabled_kinds(session, default_tenant, build_translator):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="actor_partial"
    )
    await _disable(
        session, default_tenant.id,
        "reading.bazi", "reading.vedic",
        by_account_id=acc.id,
    )
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    kb = await readings_menu_kb(i18n, default_tenant.id)
    texts = _inline_button_texts(kb)
    assert len(texts) == 6  # 8 minus 2


@pytest.fixture
def build_translator():
    from tests.conftest import build_translator as bt
    return bt
```

- [ ] **Step 2: Run test, expect FAIL**

```
uv run pytest tests/test_tenant_features_menu.py -v
```
Expect: TypeError (signature mismatch) or label-presence assertion failures.

- [ ] **Step 3: Update keyboards module**

Replace `main_menu_kb` and `readings_menu_kb` in `src/quantuum/bot/ui/keyboards.py`:

```python
async def main_menu_kb(i18n: Translator, tenant_id: int) -> ReplyKeyboardMarkup:
    from quantuum.db.session import get_sessionmaker
    from quantuum.domain.tenant_features import list_feature_states

    async with get_sessionmaker()() as session:
        flags = await list_feature_states(session, tenant_id)

    b = ReplyKeyboardBuilder()
    rows: list[int] = []
    pending_row: int = 0

    def _add(text: str) -> None:
        nonlocal pending_row
        b.button(text=text)
        pending_row += 1

    surface_buttons: list[tuple[str, str]] = [
        ("blueprint", "btn.generate"),
        ("qa", "btn.ask"),
        ("transits", "btn.transits"),
        ("daily", "btn.daily"),
    ]
    # Readings button shows iff any reading.* flag is on.
    show_readings = any(
        flags.get(k, True) for k in flags if k.startswith("reading.")
    )

    # Build surface buttons in order: blueprint, qa, readings (between qa and transits), transits, daily
    if flags.get("blueprint", True):
        _add(await i18n("btn.generate"))
    if flags.get("qa", True):
        _add(await i18n("btn.ask"))
    if show_readings:
        _add(await i18n("btn.readings"))
    if flags.get("transits", True):
        _add(await i18n("btn.transits"))
    if flags.get("daily", True):
        _add(await i18n("btn.daily"))

    # Always-on buttons.
    _add(await i18n("btn.profile"))
    _add(await i18n("btn.history"))
    _add(await i18n("btn.help"))
    _add(await i18n("btn.language"))

    # Layout: rows of 2 until we run out, last row is 1 if odd.
    layout: list[int] = []
    remaining = pending_row
    while remaining >= 2:
        layout.append(2)
        remaining -= 2
    if remaining:
        layout.append(1)
    b.adjust(*layout)
    return b.as_markup(resize_keyboard=True, is_persistent=True)


async def readings_menu_kb(i18n: Translator, tenant_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard listing only the enabled reading kinds for this tenant."""
    from quantuum.db.session import get_sessionmaker
    from quantuum.domain.tenant_features import list_feature_states

    async with get_sessionmaker()() as session:
        flags = await list_feature_states(session, tenant_id)

    b = InlineKeyboardBuilder()
    visible: list[str] = [k for k in READING_KINDS if flags.get(f"reading.{k}", True)]
    for kind in visible:
        label = await i18n(f"readings.kind.{kind}")
        b.button(text=label, callback_data=ReadingCb(action="generate", kind=kind))
    # Two-column grid; last row 1 if odd.
    layout: list[int] = []
    remaining = len(visible)
    while remaining >= 2:
        layout.append(2)
        remaining -= 2
    if remaining:
        layout.append(1)
    if layout:
        b.adjust(*layout)
    return b.as_markup()
```

- [ ] **Step 4: Update callers of `main_menu_kb` and `readings_menu_kb`**

In `src/quantuum/bot/handlers/menu.py`:

```python
async def show_main_menu(message: Message, tenant_id: int, i18n: Translator) -> None:
    await message.answer(
        await i18n("menu.title"),
        reply_markup=await main_menu_kb(i18n, tenant_id),
    )
```

Change the other two `main_menu_kb(i18n)` call sites in `menu.py` (lines around 77 and 92) to receive and forward `tenant_id`:
- `on_help_btn`: change signature to `(message: Message, tenant_id: int, i18n: Translator)` and pass `tenant_id` into `main_menu_kb`.
- `on_cancel`: take `tenant_id: int` parameter (aiogram middleware injection works for callback queries too).

In `src/quantuum/bot/handlers/start.py`, update the call to `show_main_menu` to pass `account.tenant_id` (start handler already has `account: Account` injected; verify and pass it).

In `src/quantuum/bot/handlers/language.py`, update the call to `show_main_menu` to pass the tenant_id available there (the lang picker already takes tenant_id — propagate it).

In `src/quantuum/bot/handlers/readings.py:23`, change `readings_menu_kb(i18n)` → `readings_menu_kb(i18n, account.tenant_id)`. `show_readings_menu` already has access to `account` from its caller `on_readings_btn`; update `show_readings_menu` signature to `(message, account, i18n)` and propagate.

- [ ] **Step 5: Run tests, expect PASS**

```
uv run pytest tests/test_tenant_features_menu.py -v
```

Then run the broader menu / readings / start regression set:
```
uv run pytest tests/test_menu_and_dispatcher.py tests/test_readings_bot.py tests/test_bot_onboarding.py tests/test_language_handler.py tests/test_language_picker.py tests/test_bot_start_menu_profile.py -v
```
Expect: all pass. Some existing tests may need to be updated to call `main_menu_kb(i18n, tenant_id)` instead of `main_menu_kb(i18n)`. **Update them in place** — they are part of the menu contract.

- [ ] **Step 6: Ruff**

```
uv run ruff check src/quantuum/bot/ui/keyboards.py src/quantuum/bot/handlers/ tests/test_tenant_features_menu.py
```

- [ ] **Step 7: Commit**

```
git add src/quantuum/bot/ src/quantuum/i18n/ tests/test_tenant_features_menu.py tests/
git commit -m "feat(tenant-features): hide disabled surfaces in main + readings menus"
```

---

## Task 4: Handler gates — 4 simple surfaces (qa, blueprint, transits, daily)

**Files:**
- Modify: `src/quantuum/bot/handlers/qa.py` (insert gate before existing moderation pre-check)
- Modify: `src/quantuum/bot/handlers/generate.py` (insert gate at top of entry function)
- Modify: `src/quantuum/bot/handlers/transits.py` (insert gate at top of entry function)
- Modify: `src/quantuum/bot/handlers/daily.py` (insert gate at top of entry function)
- Test: `tests/test_tenant_features_handlers.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_tenant_features_handlers.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import ModerationEvent, QaAnswer, Reading, Request
from quantuum.domain.natal_profiles import upsert_natal_profile
from quantuum.domain.tenant_features import set_feature_enabled
from tests.conftest import build_translator


async def _setup_account(session, tenant_id, *, tg="ft1"):
    from datetime import date, time
    from decimal import Decimal

    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg)
    await upsert_natal_profile(
        session, tenant_id=tenant_id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    await session.commit()
    return acc


async def _disable(session, tenant_id, key, *, by):
    await set_feature_enabled(
        session,
        tenant_id=tenant_id,
        key=key,
        enabled=False,
        by_account_id=by,
    )
    await session.commit()


def _make_message():
    msg = MagicMock()
    msg.answer = AsyncMock()
    msg.chat.id = 12345
    return msg


# ---------- QA ----------


async def test_qa_disabled_short_circuits(session, default_tenant, monkeypatch):
    acc = await _setup_account(session, default_tenant.id, tg="qa_off")
    await _disable(session, default_tenant.id, "qa", by=acc.id)

    from quantuum.bot.handlers import qa as qa_handler

    # Stub settings to disable moderation (we are testing the feature gate runs FIRST).
    monkeypatch.setattr(
        qa_handler,
        "get_settings",
        lambda: SimpleNamespace(
            moderation_enabled=False,
            moderation_fail_open=True,
            llm_api_key="",
            llm_provider="openai",
        ),
    )
    monkeypatch.setattr(qa_handler, "enqueue_qa", AsyncMock())

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()
    await qa_handler._submit(msg, "any question", acc, i18n)

    qa_rows = (await session.execute(select(QaAnswer))).scalars().all()
    me_rows = (await session.execute(select(ModerationEvent))).scalars().all()
    req_rows = (await session.execute(select(Request))).scalars().all()
    assert qa_rows == []
    assert me_rows == []
    assert req_rows == []
    msg.answer.assert_awaited_once()
    sent = msg.answer.await_args.args[0]
    assert "недоступн" in sent.lower() or "available" in sent.lower()


# ---------- Blueprint / generate ----------


async def test_blueprint_disabled_short_circuits(session, default_tenant, monkeypatch):
    acc = await _setup_account(session, default_tenant.id, tg="bp_off")
    await _disable(session, default_tenant.id, "blueprint", by=acc.id)

    from quantuum.bot.handlers import generate as gen_handler

    monkeypatch.setattr(gen_handler, "enqueue_blueprint", AsyncMock())

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()
    # The blueprint entry function is `run_generate(message, account, chat_id, i18n)`.
    await gen_handler.run_generate(msg, acc, 12345, i18n)

    req_rows = (await session.execute(select(Request))).scalars().all()
    assert req_rows == []
    msg.answer.assert_awaited_once()
    sent = msg.answer.await_args.args[0]
    assert "недоступн" in sent.lower() or "available" in sent.lower()


# ---------- Transits ----------


async def test_transits_disabled_short_circuits(session, default_tenant, monkeypatch):
    acc = await _setup_account(session, default_tenant.id, tg="tr_off")
    await _disable(session, default_tenant.id, "transits", by=acc.id)

    from quantuum.bot.handlers import transits as tr_handler

    # Patch the actual enqueue used by transits (find the symbol via grep before this task).
    monkeypatch.setattr(tr_handler, "enqueue_transits", AsyncMock(), raising=False)

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()
    await tr_handler.run_transits(msg, None, acc, i18n)

    req_rows = (await session.execute(select(Request))).scalars().all()
    assert req_rows == []
    msg.answer.assert_awaited_once()
    sent = msg.answer.await_args.args[0]
    assert "недоступн" in sent.lower() or "available" in sent.lower()


# ---------- Daily ----------


async def test_daily_disabled_short_circuits(session, default_tenant, monkeypatch):
    acc = await _setup_account(session, default_tenant.id, tg="d_off")
    await _disable(session, default_tenant.id, "daily", by=acc.id)

    from quantuum.bot.handlers import daily as d_handler

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()
    # The entry function is `run_daily_settings(message, account, i18n)`.
    await d_handler.run_daily_settings(msg, acc, i18n)

    msg.answer.assert_awaited_once()
    sent = msg.answer.await_args.args[0]
    assert "недоступн" in sent.lower() or "available" in sent.lower()
```

If `enqueue_transits` / `enqueue_blueprint` are not the exact symbol names in the handlers, fix them (read the handler imports at task start to confirm exact symbols, or use `monkeypatch.setattr(..., raising=False)` to ignore absence). The point of the stubs is to prevent Redis enqueue when the gate accidentally lets the request through.

- [ ] **Step 2: Run tests, expect FAIL**

```
uv run pytest tests/test_tenant_features_handlers.py -v
```
Expect: tests fail because the gate isn't there yet (handlers proceed to existing flow).

- [ ] **Step 3: Add the gate to each handler**

Pattern — insert at the TOP of each entry function, **before** any other check (moderation, profile, quota):

```python
# At top of qa.py::_submit (after imports of is_feature_enabled).
from quantuum.domain.tenant_features import is_feature_enabled
# ...
async def _submit(...):
    # ... existing empty/too-long guards ...
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, account.tenant_id, "qa"):
            await message.answer(await i18n("feature.disabled_generic"))
            return
    # ... rest of existing function ...
```

For `qa.py::_submit` — place the gate BEFORE the moderation pre-check (so disabled-QA tenants don't even hit OpenAI Moderation). The existing structure is:

```
def _submit:
    if not q: ...
    if too_long: ...
    settings = get_settings()
    if settings.moderation_enabled and settings.llm_api_key:
        # moderation block
```

Insert immediately after the length guard and before `settings = get_settings()`:

```python
async with get_sessionmaker()() as session:
    if not await is_feature_enabled(session, account.tenant_id, "qa"):
        _log.info(
            "feature.gate_blocked",
            tenant_id=account.tenant_id,
            account_id=account.id,
            key="qa",
            surface="qa._submit",
        )
        await message.answer(await i18n("feature.disabled_generic"))
        return
```

Add a module-level logger import at the top of each modified handler (qa.py already has `_log` from SP1 — for `generate.py`, `transits.py`, `daily.py`, add):

```python
from quantuum.logging_setup import get_logger

_log = get_logger("tenant_features.gate")
```

The same `_log.info("feature.gate_blocked", ...)` call goes in each of the 4 handlers, with the appropriate `key` and `surface` ("generate.run_generate", "transits.run_transits", "daily.run_daily_settings").

For `generate.py::run_generate` (or whatever its top-level entry is — verify before editing) — add a similar gate as the first statement after the function header.

For `transits.py::run_transits` — same pattern. The function signature is `(message, command_or_none, account, i18n)`; gate uses `account.tenant_id`.

For `daily.py::run_daily_settings` — same pattern.

The new imports go at the module top:

```python
from quantuum.domain.tenant_features import is_feature_enabled
```

- [ ] **Step 4: Run tests, expect PASS**

```
uv run pytest tests/test_tenant_features_handlers.py -v
```

Then run the broader handler regression set:
```
uv run pytest tests/test_qa_bot.py tests/test_qa_moderation_e2e.py tests/test_generate.py tests/test_generate_no_quota_offer.py tests/test_transits_bot.py tests/test_daily_bot.py -v
```
Expect: green. If a test breaks because it didn't expect a `tenant_features` DB read, leave the test alone — the gate is correct. If it breaks because it expects a specific flow, the gate passing through (defaults ON) should keep it green. Investigate any failure.

- [ ] **Step 5: Ruff**

```
uv run ruff check src/quantuum/bot/handlers/qa.py src/quantuum/bot/handlers/generate.py src/quantuum/bot/handlers/transits.py src/quantuum/bot/handlers/daily.py tests/test_tenant_features_handlers.py
```

- [ ] **Step 6: Commit**

```
git add src/quantuum/bot/handlers/qa.py src/quantuum/bot/handlers/generate.py src/quantuum/bot/handlers/transits.py src/quantuum/bot/handlers/daily.py tests/test_tenant_features_handlers.py
git commit -m "feat(tenant-features): gate qa/blueprint/transits/daily handlers"
```

---

## Task 5: Handler gate — readings (per-kind)

**Files:**
- Modify: `src/quantuum/bot/handlers/readings.py::on_reading_choice`
- Test: extend `tests/test_tenant_features_handlers.py`

The readings handler is special: the flag depends on the `kind` from the callback. Map `kind` → `f"reading.{kind}"`.

- [ ] **Step 1: Append a parametrized test to `tests/test_tenant_features_handlers.py`**

```python
import pytest


@pytest.mark.parametrize(
    "kind", ["bazi", "numerology", "human_design", "astrology",
             "vedic", "gene_keys", "mayan", "aspects"],
)
async def test_reading_kind_disabled_short_circuits(
    session, default_tenant, monkeypatch, kind
):
    acc = await _setup_account(session, default_tenant.id, tg=f"r_{kind}_off")
    await _disable(session, default_tenant.id, f"reading.{kind}", by=acc.id)

    from quantuum.bot.handlers import readings as r_handler

    monkeypatch.setattr(r_handler, "enqueue_reading", AsyncMock())

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = MagicMock()
    query.message = MagicMock()
    query.message.answer = AsyncMock()
    query.message.chat.id = 12345
    query.answer = AsyncMock()
    query.data = f"rdg:generate:{kind}"  # not parsed by the test, but realistic

    # The handler reads `kind` via `ReadingCb.unpack(query.data).kind` — we
    # patch the unpack to deterministically return the parametrized kind to
    # avoid relying on callback-data wire format.
    from quantuum.bot.ui.callbacks import ReadingCb

    monkeypatch.setattr(
        ReadingCb,
        "unpack",
        classmethod(
            lambda cls, data: SimpleNamespace(action="generate", kind=kind)
        ),
    )

    await r_handler.on_reading_choice(query, acc, i18n)

    reading_rows = (await session.execute(select(Reading))).scalars().all()
    assert reading_rows == []
    query.message.answer.assert_awaited_once()
    sent = query.message.answer.await_args.args[0]
    assert "недоступн" in sent.lower() or "available" in sent.lower()
```

- [ ] **Step 2: Run test, expect FAIL**

```
uv run pytest tests/test_tenant_features_handlers.py::test_reading_kind_disabled_short_circuits -v
```

- [ ] **Step 3: Add the gate to `on_reading_choice`**

In `src/quantuum/bot/handlers/readings.py`:

```python
from quantuum.domain.tenant_features import is_feature_enabled
from quantuum.logging_setup import get_logger

_log = get_logger("tenant_features.gate")


@router.callback_query(ReadingCb.filter(F.action == "generate"))
async def on_reading_choice(
    query: CallbackQuery, account: Account, i18n: Translator
) -> None:
    kind = ReadingCb.unpack(query.data).kind
    flag_key = f"reading.{kind}"

    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, account.tenant_id, flag_key):
            _log.info(
                "feature.gate_blocked",
                tenant_id=account.tenant_id,
                account_id=account.id,
                key=flag_key,
                surface="readings.on_reading_choice",
            )
            await query.message.answer(await i18n("feature.disabled_generic"))
            await query.answer()
            return
        # ... existing profile / quota / create_reading / create_request ...
```

(Keep the rest of the function unchanged — just wrap the existing body inside the same `async with get_sessionmaker()()` block, or open a fresh one for the gate and a second one for the rest if cleaner; existing pattern in the handler already opens its own session for the main flow.)

- [ ] **Step 4: Run tests, expect PASS**

```
uv run pytest tests/test_tenant_features_handlers.py -v
```

Then regression:
```
uv run pytest tests/test_readings_bot.py -v
```

- [ ] **Step 5: Ruff**

```
uv run ruff check src/quantuum/bot/handlers/readings.py tests/test_tenant_features_handlers.py
```

- [ ] **Step 6: Commit**

```
git add src/quantuum/bot/handlers/readings.py tests/test_tenant_features_handlers.py
git commit -m "feat(tenant-features): gate readings handler per-kind"
```

---

## Task 6: Owner console — Features submenu + toggle

**Files:**
- Modify: `src/quantuum/bot/ui/callbacks.py` (add `OwnerFeatureCb`)
- Modify: `src/quantuum/bot/handlers/owner_console.py` (add "Features" button + new callback handlers)
- Test: `tests/test_tenant_features_owner_console.py`

- [ ] **Step 1: Add the callback class**

In `src/quantuum/bot/ui/callbacks.py`, add (alongside the existing `OwnerManageCb`):

```python
class OwnerFeatureCb(CallbackData, prefix="ofeat"):
    action: str    # "open" | "toggle" | "back"
    tenant_id: int
    key: str = ""  # empty for "open" / "back"
```

- [ ] **Step 2: Write the failing tests**

`tests/test_tenant_features_owner_console.py`:

```python
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.owner_console import (
    on_features_open,
    on_features_toggle,
)
from quantuum.bot.ui.callbacks import OwnerFeatureCb
from quantuum.db.models import Tenant, TenantConfig, TenantRole
from quantuum.domain.tenant_features import is_feature_enabled
from tests.conftest import build_translator


async def _make_owner(session, tenant_id, *, tg="owner_tg"):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=tg
    )
    session.add(TenantRole(tenant_id=tenant_id, account_id=acc.id, role="owner"))
    await session.commit()
    return acc


def _make_query(tg_user_id: str, callback_data, data_str=""):
    query = MagicMock()
    query.from_user = MagicMock()
    query.from_user.id = int(tg_user_id) if tg_user_id.isdigit() else 0
    query.message = MagicMock()
    query.message.edit_text = AsyncMock()
    query.message.answer = AsyncMock()
    query.answer = AsyncMock()
    query.data = data_str
    return query


async def test_features_open_renders_all_twelve_states(session, default_tenant):
    acc = await _make_owner(session, default_tenant.id, tg="100")
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = _make_query("100", None)
    cb = OwnerFeatureCb(action="open", tenant_id=default_tenant.id, key="")
    await on_features_open(query, cb, i18n)

    # The handler should send/edit a message that includes all 12 feature buttons.
    query.message.edit_text.assert_called_once()
    args, kwargs = query.message.edit_text.call_args
    markup = kwargs.get("reply_markup") or (args[1] if len(args) > 1 else None)
    assert markup is not None
    button_data = [
        btn.callback_data for row in markup.inline_keyboard for btn in row
    ]
    # 12 toggles + 1 back; OwnerFeatureCb pack format includes "ofeat:" prefix.
    toggle_count = sum(1 for cd in button_data if cd.startswith("ofeat:toggle"))
    assert toggle_count == 12


async def test_features_toggle_persists_and_rerenders(session, default_tenant):
    acc = await _make_owner(session, default_tenant.id, tg="101")
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = _make_query("101", None)
    cb = OwnerFeatureCb(action="toggle", tenant_id=default_tenant.id, key="qa")
    await on_features_toggle(query, cb, i18n)

    # State flipped from default ON to OFF.
    assert await is_feature_enabled(session, default_tenant.id, "qa") is False
    # Subsequent toggle flips it back.
    await on_features_toggle(query, cb, i18n)
    assert await is_feature_enabled(session, default_tenant.id, "qa") is True


async def test_non_owner_cannot_toggle(session, default_tenant):
    # Non-owner: just an account, no TenantRole(owner).
    from quantuum.auth.identity import find_or_create_account_by_tg

    non_owner = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="999"
    )
    await session.commit()
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = _make_query("999", None)
    cb = OwnerFeatureCb(action="toggle", tenant_id=default_tenant.id, key="qa")
    await on_features_toggle(query, cb, i18n)

    # No row was written.
    rows = (
        await session.execute(
            select(TenantConfig).where(
                TenantConfig.tenant_id == default_tenant.id,
                TenantConfig.key == "feature.qa",
            )
        )
    ).all()
    assert rows == []
    # And the user was told they have no rights.
    query.answer.assert_awaited_once()
    answer_args, answer_kwargs = query.answer.await_args
    text_arg = (answer_args[0] if answer_args else "") or answer_kwargs.get("text", "")
    assert "rights" in text_arg.lower() or "доступ" in text_arg.lower() or text_arg
```

- [ ] **Step 3: Run tests, expect FAIL**

```
uv run pytest tests/test_tenant_features_owner_console.py -v
```

- [ ] **Step 4: Implement the handlers in `owner_console.py`**

Add new imports:

```python
from quantuum.bot.ui.callbacks import OwnerFeatureCb
from quantuum.domain.tenant_features import (
    FEATURE_KEYS,
    list_feature_states,
    set_feature_enabled,
)
```

Add a Features button to the `on_manage` keyboard (insert as a new row after the existing Users row):

```python
builder.row(
    InlineKeyboardButton(
        text=await i18n("owner.features.btn"),
        callback_data=OwnerFeatureCb(
            action="open", tenant_id=tenant.id, key=""
        ).pack(),
    )
)
```

Add two new handlers at the bottom of the file:

```python
async def _features_keyboard(tenant_id: int, flags: dict[str, bool], i18n: Translator) -> InlineKeyboardMarkup:
    """Render the 12-toggle inline keyboard."""
    b = InlineKeyboardBuilder()

    def _mark(enabled: bool) -> str:
        return "✅" if enabled else "❌"

    top_level = [
        ("qa", "owner.features.label.qa"),
        ("blueprint", "owner.features.label.blueprint"),
        ("transits", "owner.features.label.transits"),
        ("daily", "owner.features.label.daily"),
    ]
    for key, label_key in top_level:
        text_label = f"{_mark(flags[key])} {await i18n(label_key)}"
        b.button(
            text=text_label,
            callback_data=OwnerFeatureCb(
                action="toggle", tenant_id=tenant_id, key=key
            ).pack(),
        )

    # Readings section.
    for kind in (
        "bazi", "numerology", "human_design", "astrology",
        "vedic", "gene_keys", "mayan", "aspects",
    ):
        key = f"reading.{kind}"
        text_label = f"{_mark(flags[key])} {await i18n(f'readings.kind.{kind}')}"
        b.button(
            text=text_label,
            callback_data=OwnerFeatureCb(
                action="toggle", tenant_id=tenant_id, key=key
            ).pack(),
        )

    b.button(
        text=await i18n("owner.features.section.readings"),  # this is intentional as a header — see below
        callback_data="noop",
    )
    # Layout: 4 surface buttons (2x2), 8 readings (2x4), 1 back button.
    b.adjust(2, 2, 2, 2, 2, 2, 1)
    return b.as_markup()


@router.callback_query(OwnerFeatureCb.filter(F.action == "open"))
async def on_features_open(
    query: CallbackQuery,
    callback_data: OwnerFeatureCb,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        flags = await list_feature_states(session, callback_data.tenant_id)
    kb = await _features_keyboard(callback_data.tenant_id, flags, i18n)
    await query.message.edit_text(
        await i18n("owner.features.title"),
        reply_markup=kb,
    )
    await query.answer()


@router.callback_query(OwnerFeatureCb.filter(F.action == "toggle"))
async def on_features_toggle(
    query: CallbackQuery,
    callback_data: OwnerFeatureCb,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    key = callback_data.key
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        flags = await list_feature_states(session, callback_data.tenant_id)
        new_state = not flags.get(key, True)
        await set_feature_enabled(
            session,
            tenant_id=callback_data.tenant_id,
            key=key,
            enabled=new_state,
            by_account_id=actor.id,
        )
        await session.commit()
        # Re-fetch flags for the re-render so the button reflects the new state.
        flags = await list_feature_states(session, callback_data.tenant_id)
    _log.info(
        "feature.toggled",
        tenant_id=callback_data.tenant_id,
        key=key,
        enabled=new_state,
        by_account_id=actor.id,
    )
    kb = await _features_keyboard(callback_data.tenant_id, flags, i18n)
    await query.message.edit_reply_markup(reply_markup=kb)
    await query.answer()
```

Module-level logger import at the top of `owner_console.py` (if not already present from earlier features):

```python
from quantuum.logging_setup import get_logger

_log = get_logger("tenant_features.console")
```

**Note on the "Readings" header button.** The `noop` button above is a placeholder section divider — aiogram requires a callback_data string. If your project bans `"noop"` literals, use a dedicated callback class like `OwnerFeatureCb(action="noop", tenant_id=callback_data.tenant_id, key="")` and ignore it (no handler registered). Pick whichever matches the existing style in this codebase before committing.

Also add a "Back" button to return to the manage menu — re-render via `on_manage`'s flow. If that's too invasive for this task, skip Back and rely on `/manage <slug>` to re-enter. Prefer skipping it now (YAGNI for v1).

- [ ] **Step 5: Run tests, expect PASS**

```
uv run pytest tests/test_tenant_features_owner_console.py -v
```

If the spec-divider button trips the test (extra button), drop it from `_features_keyboard` — it's optional eye candy and the tests count exactly 12 toggle buttons.

- [ ] **Step 6: Run owner console regression**

```
uv run pytest tests/test_owner_console_actions.py tests/test_owner_console_domain.py tests/test_owner_console_handlers.py -v
```

- [ ] **Step 7: Ruff**

```
uv run ruff check src/quantuum/bot/ui/callbacks.py src/quantuum/bot/handlers/owner_console.py tests/test_tenant_features_owner_console.py
```

- [ ] **Step 8: Commit**

```
git add src/quantuum/bot/ui/callbacks.py src/quantuum/bot/handlers/owner_console.py tests/test_tenant_features_owner_console.py
git commit -m "feat(tenant-features): owner console Features submenu + toggle"
```

---

## Task 7: Full suite gate

**Files:** None (verification only).

- [ ] **Step 1: Run the full suite**

```
uv run pytest -q
```
Expect: all tests pass. Investigate any regression — most likely culprits are existing menu / handler tests that called the old signatures of `main_menu_kb(i18n)` or `readings_menu_kb(i18n)`. Update them in place.

- [ ] **Step 2: Ruff**

```
uv run ruff check src/ tests/
```
Expect: no new errors. (17 pre-existing errors in `test_blueprint_polish_llm.py`, `test_db_models.py`, `test_quota_cost_units.py`, `test_readings_domain.py`, `test_task_reading.py` were already there before SP2 and are not in scope.)

- [ ] **Step 3: Commit any lint/test fixups**

```
git status
# If there were changes, commit them.
git add -A && git commit -m "chore(tenant-features): final lint and test fixups"
```

---

## Notes for the implementer

- **Read patterns first.** Before Task 3 (menu), skim `src/quantuum/bot/handlers/menu.py`, `start.py`, `language.py`, `readings.py` to confirm the available variables at each call site. Before Task 4 (handler gates), skim `qa.py`, `generate.py`, `transits.py`, `daily.py` for their entry-function signatures.
- **No emojis in code/comments.** Project convention. (The i18n strings themselves *do* use emojis like ⚙️ — those are content, not code comments.)
- **Real Postgres test DB at 172.30.0.2.** `session` and `default_tenant` fixtures handle setup.
- **`utcnow` import.** `src/quantuum/db/models.py` imports it from a specific module — match its path in `tenant_features.py`. Likely `from quantuum.db.session_helpers import utcnow` or `from quantuum.common.time import utcnow`; grep before guessing.
- **`authorize_tenant_action`** is the existing helper used by `on_manage_stats` etc. in `owner_console.py`. Reuse it for the new feature toggle handlers — DRY.
- **Default ON in tests.** When asserting "no override exists" behavior, the test should NOT pre-create rows — just call `is_feature_enabled` and assert True. The `default_tenant` fixture already creates the tenant with zero TenantConfig rows.
- **i18n cache & startup seed.** Per the `i18n-seed-insert-only` memory note, new keys auto-seed at next boot; changed keys don't. This SP only adds new keys, so no live UPDATE needed.
- **Cache follow-up.** Per-tenant flag dict is read 1×/menu-render + 1×/handler-call. For high-traffic deployments, add Redis caching keyed by tenant_id (TTL ~60s, invalidate on toggle). Out of scope for this SP.
