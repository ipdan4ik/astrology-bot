# White-Label Branding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-tenant override of 4 brand-identity surfaces (display_name, start.welcome, help.text, new brand.signature) editable by tenant owners via `/owner_console`. Per-language opt-in.

**Architecture:** Reuse existing `Tenant.display_name` column and `TenantStringOverride (tenant_id, key, lang)` table. New `domain/tenant_branding.py` mirrors `domain/tenant_features.py`. New rendering helper `bot/rendering/signature.py` appends `brand.signature` to long-form LLM outputs at the worker finalizer layer (outside DB sessions). Owner console gets a "Branding" submenu with an FSM-driven edit flow.

**Tech Stack:** Python 3.13, SQLModel, aiogram 3 FSM + CallbackData, pytest-asyncio, structlog, ruff.

**Spec:** `docs/superpowers/specs/2026-05-27-white-label-branding-design.md`

---

## File Structure

**Create:**
- `src/quantuum/domain/tenant_branding.py` — domain layer (get/set/reset for i18n overrides + display_name update + validation).
- `src/quantuum/bot/rendering/signature.py` — `append_signature(body, *, tenant_id, lang)` helper.
- `src/quantuum/bot/rendering/__init__.py` — empty package init.
- `tests/test_tenant_branding_domain.py` — domain tests.
- `tests/test_tenant_branding_i18n.py` — i18n coverage tests.
- `tests/test_brand_signature_integration.py` — signature integration tests.
- `tests/test_tenant_branding_owner_console.py` — owner UX tests.

**Modify:**
- `src/quantuum/bot/ui/callbacks.py` — add `OwnerBrandingCb` class.
- `src/quantuum/bot/handlers/owner_console.py` — add Branding button on `/manage` keyboard, `on_branding_open`, `on_branding_edit`, `on_branding_value`, `OwnerBranding` FSM state, cancel/reset handlers.
- `src/quantuum/i18n/seed_strings.py` — add `brand.signature` + 14 `owner.branding.*` keys (ru+en).
- `src/quantuum/i18n/translations/{de,es,fr,hi,it,pt,tr,zh}.py` — add same 15 keys per language.
- `src/quantuum/tasks/qa.py` — wrap delivery text with `append_signature`.
- `src/quantuum/tasks/blueprint.py` — wrap delivery text with `append_signature`.
- `src/quantuum/tasks/reading.py` — wrap delivery text with `append_signature`.
- `src/quantuum/tasks/transits.py` — wrap delivery text with `append_signature`.
- `src/quantuum/tasks/daily.py` — wrap delivery text with `append_signature` inside `deliver_daily`.

---

## Task 1: Domain layer — `tenant_branding`

**Files:**
- Create: `src/quantuum/domain/tenant_branding.py`
- Test: `tests/test_tenant_branding_domain.py`

Mirror the SP2 pattern in `src/quantuum/domain/tenant_features.py:1-84`: explicit key validation, length validation, upsert semantics with `updated_at` bump on UPDATE.

- [ ] **Step 1: Write the failing test file**

```python
# tests/test_tenant_branding_domain.py
import asyncio

import pytest
from sqlalchemy import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import Tenant, TenantStringOverride
from quantuum.domain.tenant_branding import (
    BRANDING_I18N_KEYS,
    MAX_DISPLAY_NAME_LEN,
    MAX_HELP_LEN,
    MAX_SIGNATURE_LEN,
    MAX_WELCOME_LEN,
    get_branding_text,
    reset_branding_text,
    set_branding_text,
    set_display_name,
)


def test_branding_i18n_keys_inventory():
    assert set(BRANDING_I18N_KEYS) == {
        "start.welcome",
        "help.text",
        "brand.signature",
    }


def test_length_limits_inventory():
    assert MAX_DISPLAY_NAME_LEN == 64
    assert MAX_WELCOME_LEN == 2000
    assert MAX_HELP_LEN == 2000
    assert MAX_SIGNATURE_LEN == 200


async def test_get_returns_none_when_no_override(session, default_tenant):
    assert (
        await get_branding_text(
            session, tenant_id=default_tenant.id, key="start.welcome", lang="ru"
        )
        is None
    )


async def test_set_then_get_round_trip(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b1"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="start.welcome",
        lang="ru",
        text="Привет от бренда",
        by_account_id=acc.id,
    )
    await session.commit()
    assert (
        await get_branding_text(
            session, tenant_id=default_tenant.id, key="start.welcome", lang="ru"
        )
        == "Привет от бренда"
    )


async def test_set_upsert_overwrites_text(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b2"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="help.text",
        lang="en",
        text="v1",
        by_account_id=acc.id,
    )
    await session.commit()
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="help.text",
        lang="en",
        text="v2",
        by_account_id=acc.id,
    )
    await session.commit()
    assert (
        await get_branding_text(
            session, tenant_id=default_tenant.id, key="help.text", lang="en"
        )
        == "v2"
    )


async def test_set_unknown_key_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b3"
    )
    with pytest.raises(ValueError, match="unknown branding key"):
        await set_branding_text(
            session,
            tenant_id=default_tenant.id,
            key="not.a.real.key",
            lang="ru",
            text="x",
            by_account_id=acc.id,
        )


async def test_set_empty_text_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b4"
    )
    with pytest.raises(ValueError, match="empty"):
        await set_branding_text(
            session,
            tenant_id=default_tenant.id,
            key="start.welcome",
            lang="ru",
            text="",
            by_account_id=acc.id,
        )


async def test_set_too_long_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b5"
    )
    too_long = "x" * (MAX_SIGNATURE_LEN + 1)
    with pytest.raises(ValueError, match="too long"):
        await set_branding_text(
            session,
            tenant_id=default_tenant.id,
            key="brand.signature",
            lang="ru",
            text=too_long,
            by_account_id=acc.id,
        )


async def test_reset_deletes_row(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b6"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
        text="© Brand",
        by_account_id=acc.id,
    )
    await session.commit()
    await reset_branding_text(
        session, tenant_id=default_tenant.id, key="brand.signature", lang="ru"
    )
    await session.commit()
    assert (
        await get_branding_text(
            session, tenant_id=default_tenant.id, key="brand.signature", lang="ru"
        )
        is None
    )


async def test_reset_is_idempotent(session, default_tenant):
    # No row exists; should not raise.
    await reset_branding_text(
        session, tenant_id=default_tenant.id, key="brand.signature", lang="ru"
    )
    await session.commit()


async def test_set_populates_updated_by_and_at(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b7"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="help.text",
        lang="ru",
        text="hello",
        by_account_id=acc.id,
    )
    await session.commit()
    row = (
        await session.execute(
            select(TenantStringOverride).where(
                TenantStringOverride.tenant_id == default_tenant.id,
                TenantStringOverride.key == "help.text",
                TenantStringOverride.lang == "ru",
            )
        )
    ).scalar_one()
    assert row.updated_by_account_id == acc.id
    assert row.updated_at is not None


async def test_set_bumps_updated_at_on_update(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b8"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="start.welcome",
        lang="en",
        text="v1",
        by_account_id=acc.id,
    )
    await session.commit()
    row = (
        await session.execute(
            select(TenantStringOverride).where(
                TenantStringOverride.tenant_id == default_tenant.id,
                TenantStringOverride.key == "start.welcome",
                TenantStringOverride.lang == "en",
            )
        )
    ).scalar_one()
    t1 = row.updated_at

    await asyncio.sleep(0.01)

    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="start.welcome",
        lang="en",
        text="v2",
        by_account_id=acc.id,
    )
    await session.commit()
    await session.refresh(row)
    assert row.updated_at > t1


async def test_set_display_name_updates_column(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b9"
    )
    await set_display_name(
        session,
        tenant_id=default_tenant.id,
        display_name="Mystic Oracle",
        by_account_id=acc.id,
    )
    await session.commit()
    row = await session.get(Tenant, default_tenant.id)
    assert row.display_name == "Mystic Oracle"


async def test_set_display_name_too_long_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b10"
    )
    too_long = "x" * (MAX_DISPLAY_NAME_LEN + 1)
    with pytest.raises(ValueError, match="too long"):
        await set_display_name(
            session,
            tenant_id=default_tenant.id,
            display_name=too_long,
            by_account_id=acc.id,
        )


async def test_set_display_name_empty_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b11"
    )
    with pytest.raises(ValueError, match="empty"):
        await set_display_name(
            session,
            tenant_id=default_tenant.id,
            display_name="",
            by_account_id=acc.id,
        )


async def test_set_display_name_with_newline_raises(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="b12"
    )
    with pytest.raises(ValueError, match="newline"):
        await set_display_name(
            session,
            tenant_id=default_tenant.id,
            display_name="bad\nname",
            by_account_id=acc.id,
        )


async def test_get_unknown_key_raises(session, default_tenant):
    with pytest.raises(ValueError, match="unknown branding key"):
        await get_branding_text(
            session, tenant_id=default_tenant.id, key="not.a.real.key", lang="ru"
        )
```

- [ ] **Step 2: Run tests to verify they fail with ImportError**

Run: `uv run pytest tests/test_tenant_branding_domain.py -x`
Expected: FAIL — `ModuleNotFoundError: No module named 'quantuum.domain.tenant_branding'`.

- [ ] **Step 3: Implement the domain module**

```python
# src/quantuum/domain/tenant_branding.py
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.common.datetime import utcnow
from quantuum.db.models import Tenant, TenantStringOverride

BRANDING_I18N_KEYS: tuple[str, ...] = (
    "start.welcome",
    "help.text",
    "brand.signature",
)

MAX_DISPLAY_NAME_LEN = 64
MAX_WELCOME_LEN = 2000
MAX_HELP_LEN = 2000
MAX_SIGNATURE_LEN = 200

_LIMIT_BY_KEY: dict[str, int] = {
    "start.welcome": MAX_WELCOME_LEN,
    "help.text": MAX_HELP_LEN,
    "brand.signature": MAX_SIGNATURE_LEN,
}


def _require_known_key(key: str) -> None:
    if key not in BRANDING_I18N_KEYS:
        raise ValueError(f"unknown branding key: {key}")


async def get_branding_text(
    session: AsyncSession, *, tenant_id: int, key: str, lang: str
) -> str | None:
    """Return tenant override text for (key, lang), or None when absent."""
    _require_known_key(key)
    row = await session.get(TenantStringOverride, (tenant_id, key, lang))
    return row.text if row is not None else None


async def set_branding_text(
    session: AsyncSession,
    *,
    tenant_id: int,
    key: str,
    lang: str,
    text: str,
    by_account_id: int,
) -> None:
    """Upsert TenantStringOverride for (tenant, key, lang)."""
    _require_known_key(key)
    if text == "":
        raise ValueError("empty text not allowed; use reset_branding_text to clear")
    limit = _LIMIT_BY_KEY[key]
    if len(text) > limit:
        raise ValueError(f"text too long: {len(text)} > {limit}")
    row = await session.get(TenantStringOverride, (tenant_id, key, lang))
    if row is None:
        session.add(
            TenantStringOverride(
                tenant_id=tenant_id,
                key=key,
                lang=lang,
                text=text,
                updated_by_account_id=by_account_id,
            )
        )
    else:
        row.text = text
        row.updated_by_account_id = by_account_id
        row.updated_at = utcnow()
    await session.flush()


async def reset_branding_text(
    session: AsyncSession, *, tenant_id: int, key: str, lang: str
) -> None:
    """Delete tenant override row. No-op when row absent."""
    _require_known_key(key)
    await session.execute(
        delete(TenantStringOverride).where(
            TenantStringOverride.tenant_id == tenant_id,
            TenantStringOverride.key == key,
            TenantStringOverride.lang == lang,
        )
    )
    await session.flush()


async def set_display_name(
    session: AsyncSession,
    *,
    tenant_id: int,
    display_name: str,
    by_account_id: int,
) -> None:
    """Update Tenant.display_name. Validates length and disallows newlines.

    by_account_id is accepted for symmetry; audit is the caller's responsibility.
    """
    if display_name == "":
        raise ValueError("empty display_name not allowed")
    if len(display_name) > MAX_DISPLAY_NAME_LEN:
        raise ValueError(
            f"display_name too long: {len(display_name)} > {MAX_DISPLAY_NAME_LEN}"
        )
    if "\n" in display_name or "\r" in display_name:
        raise ValueError("display_name must not contain newlines")
    row = await session.get(Tenant, tenant_id)
    if row is None:
        raise ValueError(f"tenant {tenant_id} not found")
    row.display_name = display_name
    await session.flush()
```

- [ ] **Step 4: Run domain tests to verify they pass**

Run: `uv run pytest tests/test_tenant_branding_domain.py -x`
Expected: PASS — every test in the file (17 tests covering key validation, length validation, upsert/reset round-trip, audit fields, updated_at bump, display_name validation).

- [ ] **Step 5: Ruff check**

Run: `uv run ruff check src/quantuum/domain/tenant_branding.py tests/test_tenant_branding_domain.py`
Expected: no issues.

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/domain/tenant_branding.py tests/test_tenant_branding_domain.py
git commit -m "$(cat <<'EOF'
feat(tenant-branding): domain layer (get/set/reset + display_name)

Mirrors SP2 tenant_features: explicit key validation, length limits,
updated_at bump on UPDATE branch. Empty text rejected; callers must
use reset_branding_text to clear.
EOF
)"
```

---

## Task 2: i18n seed — `brand.signature` + 14 `owner.branding.*` keys

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py`
- Modify: `src/quantuum/i18n/translations/de.py`
- Modify: `src/quantuum/i18n/translations/es.py`
- Modify: `src/quantuum/i18n/translations/fr.py`
- Modify: `src/quantuum/i18n/translations/hi.py`
- Modify: `src/quantuum/i18n/translations/it.py`
- Modify: `src/quantuum/i18n/translations/pt.py`
- Modify: `src/quantuum/i18n/translations/tr.py`
- Modify: `src/quantuum/i18n/translations/zh.py`
- Test: `tests/test_tenant_branding_i18n.py`

Per `[[i18n-seed-insert-only]]` (auto-memory), the bootstrap inserts missing rows from `BASE_STRINGS` on startup; existing rows are never overwritten. Adding new keys is safe.

- [ ] **Step 1: Write the failing i18n coverage test**

```python
# tests/test_tenant_branding_i18n.py
import pytest

from quantuum.i18n.seed_strings import BASE_STRINGS
from quantuum.i18n.translations import de, es, fr, hi, it, pt, tr, zh

BRANDING_I18N_KEYS = [
    "brand.signature",
    "owner.branding.btn",
    "owner.branding.title",
    "owner.branding.label.name",
    "owner.branding.label.welcome",
    "owner.branding.label.help",
    "owner.branding.label.signature",
    "owner.branding.prompt",
    "owner.branding.saved",
    "owner.branding.reset_done",
    "owner.branding.cancelled",
    "owner.branding.too_long",
    "owner.branding.bad_format",
    "owner.branding.empty_value",
    "owner.branding.preview_empty",
]


@pytest.mark.parametrize("key", BRANDING_I18N_KEYS)
def test_base_strings_has_key_in_ru_and_en(key):
    assert key in BASE_STRINGS, f"missing {key} in BASE_STRINGS"
    entry = BASE_STRINGS[key]
    assert "ru" in entry, f"missing ru for {key}"
    assert "en" in entry, f"missing en for {key}"


@pytest.mark.parametrize(
    "lang_mod, lang_code",
    [(de, "de"), (es, "es"), (fr, "fr"), (hi, "hi"), (it, "it"), (pt, "pt"), (tr, "tr"), (zh, "zh")],
)
@pytest.mark.parametrize("key", BRANDING_I18N_KEYS)
def test_translation_modules_have_all_keys(lang_mod, lang_code, key):
    # brand.signature is intentionally seeded as empty string; assert key presence only.
    assert key in lang_mod.TRANSLATIONS, f"missing {key} in {lang_code}"
    if key != "brand.signature":
        assert lang_mod.TRANSLATIONS[key], f"empty {key} in {lang_code}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_tenant_branding_i18n.py -x`
Expected: FAIL — every parametrized case fails because the keys are not yet seeded.

- [ ] **Step 3: Add the 15 keys to `BASE_STRINGS` (ru + en)**

Open `src/quantuum/i18n/seed_strings.py`. Locate the closing `}` of the `BASE_STRINGS` dict (around line 1046). Insert the following block immediately before that `}`:

```python
    # -------------------------------------------------------------------------
    # White-label branding (SP3)
    # -------------------------------------------------------------------------
    "brand.signature": {
        "ru": "",
        "en": "",
    },
    "owner.branding.btn": {
        "ru": "🎨 Брендинг",
        "en": "🎨 Branding",
    },
    "owner.branding.title": {
        "ru": "🎨 Брендинг (язык: {lang})",
        "en": "🎨 Branding (lang: {lang})",
    },
    "owner.branding.label.name": {
        "ru": "Название",
        "en": "Name",
    },
    "owner.branding.label.welcome": {
        "ru": "Приветствие",
        "en": "Welcome",
    },
    "owner.branding.label.help": {
        "ru": "Помощь",
        "en": "Help",
    },
    "owner.branding.label.signature": {
        "ru": "Подпись",
        "en": "Signature",
    },
    "owner.branding.prompt": {
        "ru": (
            "Пришлите новый текст для **{label}** ({lang}), "
            "или /cancel — оставить как есть, /reset — вернуть дефолт."
        ),
        "en": (
            "Send new text for **{label}** ({lang}), "
            "or /cancel to keep current, /reset to restore default."
        ),
    },
    "owner.branding.saved": {
        "ru": "✅ Обновлено.",
        "en": "✅ Updated.",
    },
    "owner.branding.reset_done": {
        "ru": "↩️ Сброшено к дефолту.",
        "en": "↩️ Reset to default.",
    },
    "owner.branding.cancelled": {
        "ru": "Отменено.",
        "en": "Cancelled.",
    },
    "owner.branding.too_long": {
        "ru": "Слишком длинно: {actual} символов (максимум {limit}).",
        "en": "Too long: {actual} chars (max {limit}).",
    },
    "owner.branding.bad_format": {
        "ru": "Имя должно быть 1-64 символов и не содержать переводов строки.",
        "en": "Name must be 1-64 chars and contain no newlines.",
    },
    "owner.branding.empty_value": {
        "ru": "Пустое значение запрещено. Используйте /reset для сброса.",
        "en": "Empty value not allowed. Use /reset to clear.",
    },
    "owner.branding.preview_empty": {
        "ru": "(пусто)",
        "en": "(empty)",
    },
```

- [ ] **Step 4: Add the same 15 keys to each translation module**

For each of `de.py, es.py, fr.py, hi.py, it.py, pt.py, tr.py, zh.py` in `src/quantuum/i18n/translations/`, append the following block before the closing `}` of `TRANSLATIONS`. **Translate the values** appropriately for each language; `brand.signature` stays empty in every language. Suggested translations:

`de.py`:
```python
    # White-label branding (SP3)
    "brand.signature": "",
    "owner.branding.btn": "🎨 Branding",
    "owner.branding.title": "🎨 Branding (Sprache: {lang})",
    "owner.branding.label.name": "Name",
    "owner.branding.label.welcome": "Begrüßung",
    "owner.branding.label.help": "Hilfe",
    "owner.branding.label.signature": "Signatur",
    "owner.branding.prompt": (
        "Sende neuen Text für **{label}** ({lang}), "
        "oder /cancel um abzubrechen, /reset um Standard wiederherzustellen."
    ),
    "owner.branding.saved": "✅ Aktualisiert.",
    "owner.branding.reset_done": "↩️ Auf Standard zurückgesetzt.",
    "owner.branding.cancelled": "Abgebrochen.",
    "owner.branding.too_long": "Zu lang: {actual} Zeichen (max {limit}).",
    "owner.branding.bad_format": "Name muss 1-64 Zeichen lang sein und keine Zeilenumbrüche enthalten.",
    "owner.branding.empty_value": "Leerer Wert nicht erlaubt. /reset zum Löschen.",
    "owner.branding.preview_empty": "(leer)",
```

`es.py`:
```python
    "brand.signature": "",
    "owner.branding.btn": "🎨 Marca",
    "owner.branding.title": "🎨 Marca (idioma: {lang})",
    "owner.branding.label.name": "Nombre",
    "owner.branding.label.welcome": "Bienvenida",
    "owner.branding.label.help": "Ayuda",
    "owner.branding.label.signature": "Firma",
    "owner.branding.prompt": (
        "Envía nuevo texto para **{label}** ({lang}), "
        "o /cancel para mantener, /reset para restaurar predeterminado."
    ),
    "owner.branding.saved": "✅ Actualizado.",
    "owner.branding.reset_done": "↩️ Restaurado al predeterminado.",
    "owner.branding.cancelled": "Cancelado.",
    "owner.branding.too_long": "Demasiado largo: {actual} caracteres (máx {limit}).",
    "owner.branding.bad_format": "El nombre debe tener 1-64 caracteres sin saltos de línea.",
    "owner.branding.empty_value": "Valor vacío no permitido. Usa /reset para limpiar.",
    "owner.branding.preview_empty": "(vacío)",
```

`fr.py`:
```python
    "brand.signature": "",
    "owner.branding.btn": "🎨 Branding",
    "owner.branding.title": "🎨 Branding (langue : {lang})",
    "owner.branding.label.name": "Nom",
    "owner.branding.label.welcome": "Bienvenue",
    "owner.branding.label.help": "Aide",
    "owner.branding.label.signature": "Signature",
    "owner.branding.prompt": (
        "Envoyez le nouveau texte pour **{label}** ({lang}), "
        "ou /cancel pour garder l'actuel, /reset pour restaurer le défaut."
    ),
    "owner.branding.saved": "✅ Mis à jour.",
    "owner.branding.reset_done": "↩️ Réinitialisé au défaut.",
    "owner.branding.cancelled": "Annulé.",
    "owner.branding.too_long": "Trop long : {actual} caractères (max {limit}).",
    "owner.branding.bad_format": "Le nom doit faire 1-64 caractères sans saut de ligne.",
    "owner.branding.empty_value": "Valeur vide interdite. Utilisez /reset pour effacer.",
    "owner.branding.preview_empty": "(vide)",
```

`hi.py`:
```python
    "brand.signature": "",
    "owner.branding.btn": "🎨 ब्रांडिंग",
    "owner.branding.title": "🎨 ब्रांडिंग (भाषा: {lang})",
    "owner.branding.label.name": "नाम",
    "owner.branding.label.welcome": "स्वागत",
    "owner.branding.label.help": "मदद",
    "owner.branding.label.signature": "हस्ताक्षर",
    "owner.branding.prompt": (
        "**{label}** ({lang}) के लिए नया पाठ भेजें, "
        "या रखने के लिए /cancel, डिफ़ॉल्ट पर पुनर्स्थापित करने के लिए /reset।"
    ),
    "owner.branding.saved": "✅ अपडेट किया गया।",
    "owner.branding.reset_done": "↩️ डिफ़ॉल्ट पर पुनर्स्थापित।",
    "owner.branding.cancelled": "रद्द किया गया।",
    "owner.branding.too_long": "बहुत लंबा: {actual} अक्षर (अधिकतम {limit})।",
    "owner.branding.bad_format": "नाम 1-64 अक्षर का होना चाहिए, बिना लाइन ब्रेक के।",
    "owner.branding.empty_value": "खाली मान की अनुमति नहीं है। साफ़ करने के लिए /reset का उपयोग करें।",
    "owner.branding.preview_empty": "(खाली)",
```

`it.py`:
```python
    "brand.signature": "",
    "owner.branding.btn": "🎨 Branding",
    "owner.branding.title": "🎨 Branding (lingua: {lang})",
    "owner.branding.label.name": "Nome",
    "owner.branding.label.welcome": "Benvenuto",
    "owner.branding.label.help": "Aiuto",
    "owner.branding.label.signature": "Firma",
    "owner.branding.prompt": (
        "Invia il nuovo testo per **{label}** ({lang}), "
        "o /cancel per mantenere, /reset per ripristinare il predefinito."
    ),
    "owner.branding.saved": "✅ Aggiornato.",
    "owner.branding.reset_done": "↩️ Ripristinato al predefinito.",
    "owner.branding.cancelled": "Annullato.",
    "owner.branding.too_long": "Troppo lungo: {actual} caratteri (max {limit}).",
    "owner.branding.bad_format": "Il nome deve essere 1-64 caratteri senza ritorni a capo.",
    "owner.branding.empty_value": "Valore vuoto non permesso. Usa /reset per cancellare.",
    "owner.branding.preview_empty": "(vuoto)",
```

`pt.py`:
```python
    "brand.signature": "",
    "owner.branding.btn": "🎨 Marca",
    "owner.branding.title": "🎨 Marca (idioma: {lang})",
    "owner.branding.label.name": "Nome",
    "owner.branding.label.welcome": "Boas-vindas",
    "owner.branding.label.help": "Ajuda",
    "owner.branding.label.signature": "Assinatura",
    "owner.branding.prompt": (
        "Envie o novo texto para **{label}** ({lang}), "
        "ou /cancel para manter, /reset para restaurar o padrão."
    ),
    "owner.branding.saved": "✅ Atualizado.",
    "owner.branding.reset_done": "↩️ Restaurado para o padrão.",
    "owner.branding.cancelled": "Cancelado.",
    "owner.branding.too_long": "Muito longo: {actual} caracteres (máx {limit}).",
    "owner.branding.bad_format": "Nome deve ter 1-64 caracteres sem quebras de linha.",
    "owner.branding.empty_value": "Valor vazio não permitido. Use /reset para limpar.",
    "owner.branding.preview_empty": "(vazio)",
```

`tr.py`:
```python
    "brand.signature": "",
    "owner.branding.btn": "🎨 Markalama",
    "owner.branding.title": "🎨 Markalama (dil: {lang})",
    "owner.branding.label.name": "Ad",
    "owner.branding.label.welcome": "Karşılama",
    "owner.branding.label.help": "Yardım",
    "owner.branding.label.signature": "İmza",
    "owner.branding.prompt": (
        "**{label}** ({lang}) için yeni metin gönderin, "
        "veya korumak için /cancel, varsayılana döndürmek için /reset."
    ),
    "owner.branding.saved": "✅ Güncellendi.",
    "owner.branding.reset_done": "↩️ Varsayılana sıfırlandı.",
    "owner.branding.cancelled": "İptal edildi.",
    "owner.branding.too_long": "Çok uzun: {actual} karakter (maks {limit}).",
    "owner.branding.bad_format": "Ad 1-64 karakter olmalı ve satır sonu içermemeli.",
    "owner.branding.empty_value": "Boş değer izin verilmez. Temizlemek için /reset kullanın.",
    "owner.branding.preview_empty": "(boş)",
```

`zh.py`:
```python
    "brand.signature": "",
    "owner.branding.btn": "🎨 品牌",
    "owner.branding.title": "🎨 品牌 (语言: {lang})",
    "owner.branding.label.name": "名称",
    "owner.branding.label.welcome": "欢迎语",
    "owner.branding.label.help": "帮助",
    "owner.branding.label.signature": "签名",
    "owner.branding.prompt": (
        "为 **{label}** ({lang}) 发送新文本，"
        "或 /cancel 保持当前，/reset 恢复默认。"
    ),
    "owner.branding.saved": "✅ 已更新。",
    "owner.branding.reset_done": "↩️ 已恢复默认。",
    "owner.branding.cancelled": "已取消。",
    "owner.branding.too_long": "太长：{actual} 字符（最多 {limit}）。",
    "owner.branding.bad_format": "名称必须为 1-64 字符且不含换行。",
    "owner.branding.empty_value": "不允许空值。使用 /reset 清除。",
    "owner.branding.preview_empty": "(空)",
```

- [ ] **Step 5: Run the i18n tests to verify they pass**

Run: `uv run pytest tests/test_tenant_branding_i18n.py -x`
Expected: PASS — 135 parametrized cases (15 keys × 1 BASE assertion + 15 keys × 8 translation files).

- [ ] **Step 6: Ruff check on touched files**

Run: `uv run ruff check src/quantuum/i18n/ tests/test_tenant_branding_i18n.py`
Expected: no issues.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/i18n/seed_strings.py src/quantuum/i18n/translations/ tests/test_tenant_branding_i18n.py
git commit -m "$(cat <<'EOF'
feat(tenant-branding): i18n seed 15 keys (brand.signature + owner.branding.*)

brand.signature seeds as empty string in 10 languages (no-op default).
14 owner.branding.* keys for the FSM-driven owner UX.
Per [[i18n-seed-insert-only]]: insert-only on startup, no migration.
EOF
)"
```

---

## Task 3: Signature rendering helper

**Files:**
- Create: `src/quantuum/bot/rendering/__init__.py`
- Create: `src/quantuum/bot/rendering/signature.py`
- Test: `tests/test_brand_signature_integration.py`

- [ ] **Step 1: Write the failing test for the helper**

```python
# tests/test_brand_signature_integration.py
from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.rendering.signature import append_signature
from quantuum.domain.tenant_branding import set_branding_text
from quantuum.i18n.cache import invalidate_i18n


async def test_empty_signature_returns_body_unchanged(session, default_tenant):
    out = await append_signature(
        "BODY", tenant_id=default_tenant.id, lang="ru"
    )
    assert out == "BODY"


async def test_set_signature_appends_with_blank_line(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="sig1"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
        text="© Mystic Oracle",
        by_account_id=acc.id,
    )
    await session.commit()
    await invalidate_i18n(default_tenant.id, "ru")

    out = await append_signature(
        "BODY", tenant_id=default_tenant.id, lang="ru"
    )
    assert out == "BODY\n\n© Mystic Oracle"


async def test_whitespace_only_signature_treated_as_empty(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="sig2"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
        text="   ",
        by_account_id=acc.id,
    )
    await session.commit()
    await invalidate_i18n(default_tenant.id, "ru")

    out = await append_signature(
        "BODY", tenant_id=default_tenant.id, lang="ru"
    )
    assert out == "BODY"


async def test_signature_per_lang_routing(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="sig3"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
        text="© RU only",
        by_account_id=acc.id,
    )
    await session.commit()
    await invalidate_i18n(default_tenant.id, "ru")
    await invalidate_i18n(default_tenant.id, "en")

    ru_out = await append_signature(
        "BODY", tenant_id=default_tenant.id, lang="ru"
    )
    en_out = await append_signature(
        "BODY", tenant_id=default_tenant.id, lang="en"
    )
    assert ru_out == "BODY\n\n© RU only"
    assert en_out == "BODY"  # platform default is ""
```

- [ ] **Step 2: Run to verify failure (ImportError)**

Run: `uv run pytest tests/test_brand_signature_integration.py -x -k "test_empty_signature_returns_body_unchanged"`
Expected: FAIL — `ModuleNotFoundError: No module named 'quantuum.bot.rendering'`.

- [ ] **Step 3: Create the package init**

```python
# src/quantuum/bot/rendering/__init__.py
```

(Empty file.)

- [ ] **Step 4: Implement the signature helper**

```python
# src/quantuum/bot/rendering/signature.py
from quantuum.i18n import Translator


async def append_signature(body: str, *, tenant_id: int, lang: str) -> str:
    """Append brand.signature on a blank line. No-op when resolved value is empty.

    Resolves via the standard Translator (default empty string), so platform
    base + tenant override merging is handled by the existing i18n stack.
    """
    translator = Translator(tenant_id=tenant_id, lang=lang)
    raw = await translator("brand.signature", default="")
    sig = raw.strip()
    if not sig:
        return body
    return f"{body}\n\n{sig}"
```

- [ ] **Step 5: Run the integration tests to verify they pass**

Run: `uv run pytest tests/test_brand_signature_integration.py -x`
Expected: PASS (4 tests).

- [ ] **Step 6: Ruff check**

Run: `uv run ruff check src/quantuum/bot/rendering/ tests/test_brand_signature_integration.py`
Expected: no issues.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/bot/rendering/__init__.py src/quantuum/bot/rendering/signature.py tests/test_brand_signature_integration.py
git commit -m "$(cat <<'EOF'
feat(tenant-branding): append_signature rendering helper

Resolves brand.signature via existing Translator (default ''); no-op when
empty or whitespace-only. Per-lang opt-in routed through the standard
override resolver — no special-case branching.
EOF
)"
```

---

## Task 4: Worker integration — append signature in all 5 finalizers

**Files:**
- Modify: `src/quantuum/tasks/qa.py:80-92`
- Modify: `src/quantuum/tasks/blueprint.py:89-102`
- Modify: `src/quantuum/tasks/reading.py:79-92`
- Modify: `src/quantuum/tasks/transits.py:94-107`
- Modify: `src/quantuum/tasks/daily.py:30-44`
- Test: append to `tests/test_brand_signature_integration.py`

The pattern in the four `deliver_via_tenant_bot` callers is identical: a delivery block at the end of the function, outside any DB session. We wrap `delivery_md` (or equivalent) with `append_signature` immediately before passing it to `deliver_via_tenant_bot`. The `lang` value comes from the same source already used (or `qa.lang`, `transit_lang`, etc.).

Daily is slightly different: `deliver_daily` builds its own Translator inside. We append the signature there after composing the `header + text` body.

- [ ] **Step 1: Write the failing wire-up tests**

Append to `tests/test_brand_signature_integration.py` a parametrized test that asserts each worker module re-exports `append_signature` (i.e. the import is in place):

```python
import importlib

import pytest


@pytest.mark.parametrize(
    "module_path",
    [
        "quantuum.tasks.qa",
        "quantuum.tasks.blueprint",
        "quantuum.tasks.reading",
        "quantuum.tasks.transits",
        "quantuum.tasks.daily",
    ],
)
def test_worker_module_imports_append_signature(module_path):
    mod = importlib.import_module(module_path)
    assert getattr(mod, "append_signature", None) is not None, (
        f"{module_path} must import append_signature for delivery wrapping"
    )
```

This proves that each worker module has the import line wired up. End-to-end behavior of the workers themselves is exercised by the existing per-worker test files (run in Step 9).

- [ ] **Step 2: Run to verify failures**

Run: `uv run pytest tests/test_brand_signature_integration.py::test_worker_module_imports_append_signature -x`
Expected: FAIL — `AssertionError: quantuum.tasks.qa must import append_signature for delivery wrapping`.

- [ ] **Step 3: Modify `src/quantuum/tasks/qa.py`**

At the top of the file (after the existing `from quantuum.tasks.delivery import deliver_via_tenant_bot` line), add:

```python
from quantuum.bot.rendering.signature import append_signature
```

The `lang` local is already computed inside the `async with sessionmaker()` block at line 39 (`lang = qa.lang or await get_tenant_default_lang(...) or "ru"`) and remains in scope outside the block. Replace the existing delivery block (lines 79-92) with:

```python
    # Delivery is best-effort and must NOT trigger a refund of a successful generation.
    if chat_id is not None and delivery_md is not None and tenant_id is not None:
        try:
            delivery_md = await append_signature(
                delivery_md, tenant_id=tenant_id, lang=lang
            )
            await deliver_via_tenant_bot(
                sessionmaker,
                tenant_id=tenant_id,
                chat_id=chat_id,
                text=delivery_md,
                filename="answer.md",
                preview_len=4000,
                always_document=False,
            )
        except Exception:
            logger.exception("qa_delivery_failed", qa_id=qa_id, chat_id=chat_id)
```

- [ ] **Step 4: Modify `src/quantuum/tasks/blueprint.py`**

Add the import at the top:

```python
from quantuum.bot.rendering.signature import append_signature
```

In `blueprint.py` the `lang` local is currently only computed inside the `if llm_client is not None:` branch (line 38). The `else` branch (line 60) also produces a `delivery_md` but never computes lang. Hoist the lang computation BEFORE the if/else, so it's available for the delivery block. Change line 34-38 from:

```python
            cfg = await get_llm_config(session)
            llm_client = ctx.get("llm_client")

            if llm_client is not None:
                lang = bp.lang or await get_tenant_default_lang(session, tenant_id) or "ru"
                result = await polish_blueprint(
```

to:

```python
            cfg = await get_llm_config(session)
            llm_client = ctx.get("llm_client")
            lang = bp.lang or await get_tenant_default_lang(session, tenant_id) or "ru"

            if llm_client is not None:
                result = await polish_blueprint(
```

Then replace the delivery block (lines 89-102) with:

```python
    # Delivery is best-effort and must NOT trigger a refund of a successful generation.
    if chat_id is not None and delivery_md is not None and tenant_id is not None:
        try:
            delivery_md = await append_signature(
                delivery_md, tenant_id=tenant_id, lang=lang
            )
            await deliver_via_tenant_bot(
                sessionmaker,
                tenant_id=tenant_id,
                chat_id=chat_id,
                text=delivery_md,
                filename="blueprint.md",
                preview_len=500,
                always_document=True,
            )
        except Exception:
            logger.exception("blueprint_delivery_failed", blueprint_id=blueprint_id, chat_id=chat_id)
```

- [ ] **Step 5: Modify `src/quantuum/tasks/reading.py`**

Add the import at the top:

```python
from quantuum.bot.rendering.signature import append_signature
```

Like blueprint, `lang` is only set in the `else` branch (line 46). Hoist it before the if/else. Change lines 36-46 from:

```python
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
```

to:

```python
            cfg = await get_llm_config(session)
            llm_client = ctx.get("llm_client")
            lang = reading.lang or await get_tenant_default_lang(session, tenant_id) or "ru"

            if llm_client is None:
                await set_reading_status(
                    session, reading_id, "done",
                    llm_md=calc_md, llm_provider="none", llm_model="none",
                )
                delivery_md = calc_md
            else:
                result = await polish_reading(
```

Then replace the delivery block (lines 79-92) with:

```python
    # Delivery is best-effort and must NOT trigger a refund of a successful generation.
    if chat_id is not None and delivery_md is not None and tenant_id is not None:
        try:
            delivery_md = await append_signature(
                delivery_md, tenant_id=tenant_id, lang=lang
            )
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
```

- [ ] **Step 6: Modify `src/quantuum/tasks/transits.py`**

Add the import at the top:

```python
from quantuum.bot.rendering.signature import append_signature
```

In `transits.py` the lang is computed inline as a kwarg of `transit_report` (lines 54-59). Extract it to a local. Change lines 49-63 from:

```python
            cfg = await get_llm_config(session)
            result = await transit_report(
                llm_client,
                natal_md,
                transit_md,
                lang=await resolve_lang(
                    session,
                    tenant_id=row.tenant_id,
                    preferred_lang=row.lang,
                    tg_language_code=None,
                ),
                model=cfg["model"],
                temperature=cfg["temperature"],
                max_tokens=cfg["max_tokens"],
            )
```

to:

```python
            cfg = await get_llm_config(session)
            lang = await resolve_lang(
                session,
                tenant_id=row.tenant_id,
                preferred_lang=row.lang,
                tg_language_code=None,
            )
            result = await transit_report(
                llm_client,
                natal_md,
                transit_md,
                lang=lang,
                model=cfg["model"],
                temperature=cfg["temperature"],
                max_tokens=cfg["max_tokens"],
            )
```

Then replace the delivery block (lines 94-107) with:

```python
    # Delivery is best-effort and must NOT trigger a refund of a successful report.
    if chat_id is not None and delivery_md is not None and tenant_id is not None:
        try:
            delivery_md = await append_signature(
                delivery_md, tenant_id=tenant_id, lang=lang
            )
            await deliver_via_tenant_bot(
                sessionmaker,
                tenant_id=tenant_id,
                chat_id=chat_id,
                text=delivery_md,
                filename="transits.md",
                preview_len=4000,
                always_document=False,
            )
        except Exception:
            logger.exception("transit_delivery_failed", report_id=report_id, chat_id=chat_id)
```

- [ ] **Step 7: Modify `src/quantuum/tasks/daily.py`**

Add import:

```python
from quantuum.bot.rendering.signature import append_signature
```

Modify `deliver_daily` (lines 30-44) to append signature to the body before sending:

```python
async def deliver_daily(sessionmaker, *, tenant_id: int, chat_id: str, lang: str | None, text: str) -> None:
    """Send the horoscope via the user's tenant bot. Best-effort."""
    async with sessionmaker() as session:
        tb = await get_active_tenant_bot(session, tenant_id)
        if tb is None:
            return
        i18n = await Translator.build(
            session, tenant_id=tenant_id, preferred_lang=lang, tg_language_code=None
        )
        header = await i18n("daily.header")
    body = await append_signature(
        f"{header}\n\n{text}", tenant_id=tenant_id, lang=lang or "ru"
    )
    bot = Bot(token=decrypt_token(tb.bot_token_enc))
    try:
        await bot.send_message(int(chat_id), body[:4000])
    finally:
        await bot.session.close()
```

- [ ] **Step 8: Run the wire-up + helper tests**

Run: `uv run pytest tests/test_brand_signature_integration.py -x`
Expected: PASS (4 helper tests + 5 wire-up parametrized cases = 9 cases).

- [ ] **Step 9: Run the whole worker test set to confirm no regression**

Run: `uv run pytest tests/test_qa_worker.py tests/test_blueprint_worker.py tests/test_reading_worker.py tests/test_transit_worker.py tests/test_daily_worker.py 2>&1 | tail -20`
Expected: PASS (or, if those exact filenames don't exist, run `pytest -k "worker" --co -q` first to discover them and then run the discovered set).

- [ ] **Step 10: Ruff check**

Run: `uv run ruff check src/quantuum/tasks/ src/quantuum/bot/rendering/`
Expected: no issues.

- [ ] **Step 11: Commit**

```bash
git add src/quantuum/tasks/qa.py src/quantuum/tasks/blueprint.py src/quantuum/tasks/reading.py src/quantuum/tasks/transits.py src/quantuum/tasks/daily.py tests/test_brand_signature_integration.py
git commit -m "$(cat <<'EOF'
feat(tenant-branding): append brand.signature in 5 worker finalizers

QA / blueprint / reading / transits / daily wrap delivery text via
append_signature before deliver_via_tenant_bot. Default-empty signature
means zero output change for un-customized tenants.
EOF
)"
```

---

## Task 5: Owner callback class + Branding button

**Files:**
- Modify: `src/quantuum/bot/ui/callbacks.py`
- Modify: `src/quantuum/bot/handlers/owner_console.py:67-87` (the `/manage` keyboard builder)
- Test: `tests/test_tenant_branding_owner_console.py` (start file)

- [ ] **Step 1: Write the failing test — Branding button visible on /manage**

```python
# tests/test_tenant_branding_owner_console.py
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import Message

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.owner_console import on_manage
from quantuum.bot.ui.callbacks import OwnerBrandingCb
from quantuum.db.models import TenantRole
from tests.conftest import build_translator


async def _make_owner(session, tenant_id, *, tg):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=tg
    )
    session.add(TenantRole(tenant_id=tenant_id, account_id=acc.id, role="owner"))
    await session.commit()
    return acc


def _make_message(tg_user_id: str) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock()
    msg.from_user.id = int(tg_user_id)
    msg.answer = AsyncMock()
    return msg


async def test_manage_keyboard_includes_branding_button(session, default_tenant):
    await _make_owner(session, default_tenant.id, tg="201")
    i18n = await build_translator(session, default_tenant.id, lang="ru")

    msg = _make_message("201")
    command = MagicMock()
    command.args = default_tenant.slug
    await on_manage(msg, command, i18n)

    msg.answer.assert_awaited_once()
    _, kwargs = msg.answer.await_args
    markup = kwargs.get("reply_markup")
    assert markup is not None
    button_datas = [
        btn.callback_data for row in markup.inline_keyboard for btn in row
        if btn.callback_data is not None
    ]
    branding_buttons = [
        cd for cd in button_datas if cd.startswith("obrand:")
    ]
    assert len(branding_buttons) == 1
    assert branding_buttons[0].startswith("obrand:open")


def test_owner_branding_cb_class_exists():
    cb = OwnerBrandingCb(action="open", tenant_id=1, key="")
    assert cb.pack().startswith("obrand:")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_tenant_branding_owner_console.py -x`
Expected: FAIL — `ImportError: cannot import name 'OwnerBrandingCb'`.

- [ ] **Step 3: Add the callback class**

Edit `src/quantuum/bot/ui/callbacks.py`. At the end of the file, after `ReadingDownloadCb`, append:

```python
class OwnerBrandingCb(CallbackData, prefix="obrand"):
    action: str    # open | edit
    tenant_id: int = 0
    key: str = ""  # display_name | start.welcome | help.text | brand.signature | empty for open
```

- [ ] **Step 4: Add the Branding button to `/manage` keyboard**

Edit `src/quantuum/bot/handlers/owner_console.py`. Update the import block at the top:

```python
from quantuum.bot.ui.callbacks import OwnerBrandingCb, OwnerFeatureCb, OwnerManageCb, OwnerUserCb
```

Then in `on_manage`, after the existing `OwnerFeatureCb` button row (around line 87), add another row:

```python
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.branding.btn"),
            callback_data=OwnerBrandingCb(
                action="open", tenant_id=tenant.id, key=""
            ).pack(),
        )
    )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_tenant_branding_owner_console.py -x`
Expected: PASS (2 tests).

- [ ] **Step 6: Ruff check**

Run: `uv run ruff check src/quantuum/bot/ui/callbacks.py src/quantuum/bot/handlers/owner_console.py tests/test_tenant_branding_owner_console.py`
Expected: no issues.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/bot/ui/callbacks.py src/quantuum/bot/handlers/owner_console.py tests/test_tenant_branding_owner_console.py
git commit -m "$(cat <<'EOF'
feat(tenant-branding): OwnerBrandingCb + Branding button on /manage

New callback class with action=open|edit. Branding row sits between
Features and Pause/Resume on the /manage inline keyboard.
EOF
)"
```

---

## Task 6: Branding submenu + FSM edit flow

**Files:**
- Modify: `src/quantuum/bot/handlers/owner_console.py` (append the submenu + FSM handlers)
- Modify: `tests/test_tenant_branding_owner_console.py` (append flow tests)

The submenu is a 4-button inline keyboard with current-value previews truncated to 40 chars. Tapping a button enters FSM state `OwnerBranding.awaiting_value`. The owner sends a message; we validate and upsert (or for `/reset`, delete the row; or for `/cancel`, clear state).

- [ ] **Step 1: Write the failing test — submenu render**

Append to `tests/test_tenant_branding_owner_console.py`:

```python
from aiogram.types import CallbackQuery

from quantuum.bot.handlers.owner_console import (
    on_branding_edit,
    on_branding_open,
    on_branding_value,
)
from quantuum.domain.tenant_branding import (
    get_branding_text,
    set_branding_text,
)


def _make_query(tg_user_id: str):
    query = MagicMock()
    query.from_user = MagicMock()
    query.from_user.id = int(tg_user_id)
    query.message = MagicMock()
    query.message.edit_text = AsyncMock()
    query.message.answer = AsyncMock()
    query.answer = AsyncMock()
    return query


async def test_branding_submenu_renders_four_entries(session, default_tenant):
    await _make_owner(session, default_tenant.id, tg="210")
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = _make_query("210")
    cb = OwnerBrandingCb(action="open", tenant_id=default_tenant.id, key="")
    await on_branding_open(query, cb, i18n)

    query.message.edit_text.assert_awaited_once()
    _, kwargs = query.message.edit_text.await_args
    markup = kwargs.get("reply_markup")
    button_datas = [
        btn.callback_data for row in markup.inline_keyboard for btn in row
        if btn.callback_data is not None
    ]
    edit_callbacks = [cd for cd in button_datas if cd.startswith("obrand:edit")]
    assert len(edit_callbacks) == 4


async def test_non_owner_cannot_open_branding(session, default_tenant):
    await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="999b"
    )
    await session.commit()
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = _make_query("999b")
    cb = OwnerBrandingCb(action="open", tenant_id=default_tenant.id, key="")
    await on_branding_open(query, cb, i18n)

    query.message.edit_text.assert_not_called()
    query.answer.assert_awaited_once()
    args, kwargs = query.answer.await_args
    assert kwargs.get("show_alert") is True
```

- [ ] **Step 2: Write the failing test — edit FSM flow saves an override**

Append to the same test file:

```python
from aiogram.fsm.context import FSMContext


def _make_fsm():
    state = MagicMock(spec=FSMContext)
    state.set_state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state


async def test_branding_edit_flow_saves_override(session, default_tenant):
    await _make_owner(session, default_tenant.id, tg="220")
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    state = _make_fsm()

    # 1) Tap "Welcome" entry -> enters FSM
    query = _make_query("220")
    cb = OwnerBrandingCb(
        action="edit", tenant_id=default_tenant.id, key="start.welcome"
    )
    await on_branding_edit(query, cb, state, i18n)
    state.set_state.assert_awaited_once()
    state.update_data.assert_awaited_once()

    # 2) Owner sends the new value -> upserts override
    state.get_data = AsyncMock(
        return_value={
            "tenant_id": default_tenant.id,
            "key": "start.welcome",
            "lang": "ru",
        }
    )
    msg = _make_message("220")
    msg.text = "Custom welcome from Mystic Oracle"
    await on_branding_value(msg, state, i18n)

    stored = await get_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="start.welcome",
        lang="ru",
    )
    assert stored == "Custom welcome from Mystic Oracle"
    state.clear.assert_awaited_once()


async def test_branding_edit_flow_validates_too_long(session, default_tenant):
    acc = await _make_owner(session, default_tenant.id, tg="221")
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    state = _make_fsm()
    state.get_data = AsyncMock(
        return_value={
            "tenant_id": default_tenant.id,
            "key": "brand.signature",
            "lang": "ru",
        }
    )
    msg = _make_message("221")
    msg.text = "x" * 1000  # exceeds 200-char signature limit

    await on_branding_value(msg, state, i18n)

    msg.answer.assert_awaited_once()
    args, _ = msg.answer.await_args
    assert "макси" in args[0].lower() or "max" in args[0].lower()
    stored = await get_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
    )
    assert stored is None  # nothing saved
    state.clear.assert_not_called()  # stay in state for retry


async def test_branding_edit_flow_display_name_newline_rejected(
    session, default_tenant
):
    await _make_owner(session, default_tenant.id, tg="222")
    i18n = await build_translator(session, default_tenant.id, lang="ru")
    state = _make_fsm()
    state.get_data = AsyncMock(
        return_value={
            "tenant_id": default_tenant.id,
            "key": "display_name",
            "lang": "ru",
        }
    )
    msg = _make_message("222")
    msg.text = "bad\nname"

    await on_branding_value(msg, state, i18n)

    msg.answer.assert_awaited_once()
    state.clear.assert_not_called()


async def test_branding_reset_clears_override(session, default_tenant):
    acc = await _make_owner(session, default_tenant.id, tg="223")
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
        text="© will be reset",
        by_account_id=acc.id,
    )
    await session.commit()

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    state = _make_fsm()
    state.get_data = AsyncMock(
        return_value={
            "tenant_id": default_tenant.id,
            "key": "brand.signature",
            "lang": "ru",
        }
    )
    msg = _make_message("223")
    msg.text = "/reset"

    await on_branding_value(msg, state, i18n)

    stored = await get_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
    )
    assert stored is None
    state.clear.assert_awaited_once()


async def test_branding_per_lang_scoping(session, default_tenant):
    """Override saved while owner.lang=ru does not leak to en."""
    await _make_owner(session, default_tenant.id, tg="224")
    i18n_ru = await build_translator(session, default_tenant.id, lang="ru")
    state = _make_fsm()
    state.get_data = AsyncMock(
        return_value={
            "tenant_id": default_tenant.id,
            "key": "start.welcome",
            "lang": "ru",
        }
    )
    msg = _make_message("224")
    msg.text = "Russian welcome"
    await on_branding_value(msg, state, i18n_ru)

    assert (
        await get_branding_text(
            session,
            tenant_id=default_tenant.id,
            key="start.welcome",
            lang="ru",
        )
        == "Russian welcome"
    )
    assert (
        await get_branding_text(
            session,
            tenant_id=default_tenant.id,
            key="start.welcome",
            lang="en",
        )
        is None
    )
```

- [ ] **Step 3: Run to verify failures**

Run: `uv run pytest tests/test_tenant_branding_owner_console.py -x`
Expected: FAIL on every new test — `ImportError: cannot import name 'on_branding_open'`.

- [ ] **Step 4: Implement the submenu + FSM in owner_console.py**

First, hoist the new imports to the **top of the file**. The `OwnerBrandingCb` import was already added in Task 5; now also add the `tenant_branding` domain imports. Update the existing `quantuum.domain.tenant_features` import to sit next to a new line:

```python
from quantuum.domain.tenant_branding import (
    MAX_DISPLAY_NAME_LEN,
    MAX_HELP_LEN,
    MAX_SIGNATURE_LEN,
    MAX_WELCOME_LEN,
    get_branding_text,
    reset_branding_text,
    set_branding_text,
    set_display_name,
)
```

Then append to `src/quantuum/bot/handlers/owner_console.py` (after the SP2 features block, around line 478):

```python
# ── SP3: Branding submenu + edit FSM ────────────────────────────────────────────

_branding_log = get_logger("tenant_branding.console")

_BRANDING_PREVIEW_LEN = 40

_BRANDING_LIMITS: dict[str, int] = {
    "display_name": MAX_DISPLAY_NAME_LEN,
    "start.welcome": MAX_WELCOME_LEN,
    "help.text": MAX_HELP_LEN,
    "brand.signature": MAX_SIGNATURE_LEN,
}

_BRANDING_LABEL_KEYS: dict[str, str] = {
    "display_name": "owner.branding.label.name",
    "start.welcome": "owner.branding.label.welcome",
    "help.text": "owner.branding.label.help",
    "brand.signature": "owner.branding.label.signature",
}


class OwnerBranding(StatesGroup):
    awaiting_value = State()


def _truncate(s: str) -> str:
    if len(s) <= _BRANDING_PREVIEW_LEN:
        return s
    return s[: _BRANDING_PREVIEW_LEN - 1] + "…"


async def _branding_current_value(
    session, *, tenant_id: int, key: str, lang: str
) -> str | None:
    """Resolve current value: Tenant.display_name for display_name; override
    text for the three i18n keys (None when no row)."""
    if key == "display_name":
        row = await session.get(Tenant, tenant_id)
        return row.display_name if row is not None else None
    return await get_branding_text(
        session, tenant_id=tenant_id, key=key, lang=lang
    )


async def _branding_keyboard(
    tenant_id: int, previews: dict[str, str], i18n: Translator
):
    b = InlineKeyboardBuilder()
    empty_marker = await i18n("owner.branding.preview_empty")
    for key in ("display_name", "start.welcome", "help.text", "brand.signature"):
        label = await i18n(_BRANDING_LABEL_KEYS[key])
        preview = previews.get(key) or ""
        preview = _truncate(preview) if preview else empty_marker
        b.button(
            text=f"{label}: {preview}",
            callback_data=OwnerBrandingCb(
                action="edit", tenant_id=tenant_id, key=key
            ).pack(),
        )
    b.adjust(1, 1, 1, 1)
    return b.as_markup()


@router.callback_query(OwnerBrandingCb.filter(F.action == "open"))
async def on_branding_open(
    query: CallbackQuery,
    callback_data: OwnerBrandingCb,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        previews = {}
        for key in ("display_name", "start.welcome", "help.text", "brand.signature"):
            previews[key] = await _branding_current_value(
                session, tenant_id=callback_data.tenant_id, key=key, lang=i18n.lang
            )
    kb = await _branding_keyboard(callback_data.tenant_id, previews, i18n)
    await query.message.edit_text(
        await i18n("owner.branding.title", lang=i18n.lang),
        reply_markup=kb,
    )
    await query.answer()


@router.callback_query(OwnerBrandingCb.filter(F.action == "edit"))
async def on_branding_edit(
    query: CallbackQuery,
    callback_data: OwnerBrandingCb,
    state: FSMContext,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    key = callback_data.key
    if key not in _BRANDING_LIMITS:
        await query.answer(await i18n("owner.no_rights"), show_alert=True)
        return
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
    await state.set_state(OwnerBranding.awaiting_value)
    await state.update_data(
        tenant_id=callback_data.tenant_id,
        key=key,
        lang=i18n.lang,
    )
    label = await i18n(_BRANDING_LABEL_KEYS[key])
    await query.message.answer(
        await i18n("owner.branding.prompt", label=label, lang=i18n.lang)
    )
    await query.answer()


@router.message(Command("cancel"), OwnerBranding.awaiting_value)
async def on_branding_cancel(message: Message, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await message.answer(await i18n("owner.branding.cancelled"))


@router.message(OwnerBranding.awaiting_value)
async def on_branding_value(message: Message, state: FSMContext, i18n: Translator) -> None:
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    key = data["key"]
    lang = data["lang"]
    raw = message.text or ""

    if raw.strip() == "/reset":
        async with get_sessionmaker()() as session:
            actor_id = await authorize_tenant_action(
                session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id
            )
            if actor_id is None:
                await message.answer(await i18n("owner.no_rights"))
                await state.clear()
                return
            if key == "display_name":
                # display_name has no override row to clear.
                await message.answer(
                    await i18n("owner.branding.bad_format")
                )
                return
            await reset_branding_text(
                session, tenant_id=tenant_id, key=key, lang=lang
            )
            await session.commit()
        _branding_log.info(
            "branding.reset",
            tenant_id=tenant_id,
            key=key,
            lang=lang,
            by_account_id=actor_id,
        )
        await state.clear()
        await message.answer(await i18n("owner.branding.reset_done"))
        return

    if raw == "":
        await message.answer(await i18n("owner.branding.empty_value"))
        return  # stay in state

    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id
        )
        if actor_id is None:
            await message.answer(await i18n("owner.no_rights"))
            await state.clear()
            return
        try:
            if key == "display_name":
                await set_display_name(
                    session,
                    tenant_id=tenant_id,
                    display_name=raw,
                    by_account_id=actor_id,
                )
            else:
                await set_branding_text(
                    session,
                    tenant_id=tenant_id,
                    key=key,
                    lang=lang,
                    text=raw,
                    by_account_id=actor_id,
                )
            await session.commit()
        except ValueError as exc:
            err = str(exc)
            if "too long" in err:
                limit = _BRANDING_LIMITS[key]
                await message.answer(
                    await i18n(
                        "owner.branding.too_long",
                        actual=len(raw),
                        limit=limit,
                    )
                )
            elif "newline" in err:
                await message.answer(await i18n("owner.branding.bad_format"))
            elif "empty" in err:
                await message.answer(await i18n("owner.branding.empty_value"))
            else:
                await message.answer(await i18n("owner.branding.bad_format"))
            return  # stay in state for retry

    _branding_log.info(
        "branding.updated",
        tenant_id=tenant_id,
        key=key,
        lang=None if key == "display_name" else lang,
        by_account_id=actor_id,
        length=len(raw),
    )
    await state.clear()
    await message.answer(await i18n("owner.branding.saved"))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_tenant_branding_owner_console.py -x`
Expected: PASS — every test in the file (2 from Task 5 + 7 from Task 6 = 9 tests).

- [ ] **Step 6: Ruff check**

Run: `uv run ruff check src/quantuum/bot/handlers/owner_console.py tests/test_tenant_branding_owner_console.py`
Expected: no issues.

- [ ] **Step 7: Commit**

```bash
git add src/quantuum/bot/handlers/owner_console.py tests/test_tenant_branding_owner_console.py
git commit -m "$(cat <<'EOF'
feat(tenant-branding): owner console Branding submenu + edit FSM

Submenu renders 4 entries with truncated previews. Tap enters
OwnerBranding.awaiting_value FSM; owner sends text, /cancel, or /reset.
Validates length / newlines and replies with localized error keys.
Emits branding.updated and branding.reset structured logs.
EOF
)"
```

---

## Task 7: Full-suite gate + ruff sweep

**Files:**
- No new edits; verification only.

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest 2>&1 | tail -30`
Expected: PASS — 964 (pre-SP3) + ~30 new tests = ~994 tests passing, zero failures.

- [ ] **Step 2: Ruff sweep over the project source**

Run: `uv run ruff check src/`
Expected: no issues.

- [ ] **Step 3: Run ruff on tests**

Run: `uv run ruff check tests/test_tenant_branding_domain.py tests/test_tenant_branding_i18n.py tests/test_brand_signature_integration.py tests/test_tenant_branding_owner_console.py`
Expected: no issues.

- [ ] **Step 4: Sanity check — git log shows the SP3 chain**

Run: `git log --oneline -10`
Expected: top 6 commits are the SP3 task commits.

- [ ] **Step 5: No commit needed at this stage**

This task is a verification gate; the work is already committed across Tasks 1-6.

---

## Acceptance verification (per spec §9)

After Task 7 passes, verify each acceptance criterion against the actual code:

- [ ] `domain/tenant_branding.py` exposes `get_branding_text`, `set_branding_text`, `reset_branding_text`, `set_display_name` — Task 1.
- [ ] Owner can edit display_name, welcome, help, signature from `/manage → Branding` — Tasks 5+6.
- [ ] Non-owners cannot open or edit — Task 6.
- [ ] Editing welcome / help / signature creates a `TenantStringOverride` row only for owner's current lang — Task 6 (per-lang scoping test).
- [ ] `brand.signature` seeded as empty string in 10 languages; absent override → no footer rendered — Task 2 + Task 3.
- [ ] Non-empty signature appears in QA, blueprint, readings, daily, transit outputs — Task 4.
- [ ] `branding.updated` and `branding.reset` logs with documented fields — Task 6.
- [ ] All 15 new i18n keys exist in 10 languages — Task 2.
- [ ] Full test suite passes — Task 7.
