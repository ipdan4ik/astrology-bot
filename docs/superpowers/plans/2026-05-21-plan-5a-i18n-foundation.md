# Plan 5a — i18n Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add per-tenant internationalization: the config/string data model, a cached `t()` resolver with the spec's fallback chain, user-language resolution, seeded platform strings (ru + en), and wiring the customer bot UI off hardcoded Russian strings onto `t()`.

**Architecture:** New `quantuum/i18n/` package. Five new tables (`platform_config`, `tenant_config`, `platform_strings`, `tenant_string_overrides`, `tenant_languages`). A `Translator` bound to `(tenant_id, lang)` resolves keys through a Redis-cached fallback chain (tenant override → platform → tenant-default-lang override → platform-default-lang → arg default → `[missing: key]`). The `AccountMiddleware` resolves the user's language and injects a ready `Translator` (`data["i18n"]`) so handlers call `await i18n("key", **vars)`. Admin string editing (cache invalidation endpoints) lands in Plan 5b; 5a exposes the `invalidate_i18n` primitive it will call.

**Tech Stack:** SQLModel/asyncpg/Alembic, Redis (hash cache + pub/sub seam), aiogram 3, pytest. Spec refs: §4 "Config & i18n" (data model), §6 "i18n" (resolver + cache + lang resolution).

---

## Key design decisions (read first)

1. **Fallback chain** (spec §414), for `t(key, lang)` under `tenant_id` with the tenant's default lang `D`:
   1. `tenant_string_overrides(tenant_id, key, lang)`
   2. `platform_strings(key, lang)`
   3. `tenant_string_overrides(tenant_id, key, D)`
   4. `platform_strings(key, D)`
   5. `default` argument (if provided)
   6. `f"[missing: {key}]"` + a `warning` log
   Then `.format(**vars)` (use a forgiving format that leaves unknown braces intact — see Task 3).

2. **Cache shape:** Redis hash `i18n:{tenant_id}:{lang}` = the merged `{key: text}` for that `(tenant, lang)` — platform_strings(lang) overlaid with tenant_string_overrides(tenant, lang). TTL 3600s. Steps 1-2 of the chain resolve from `cache[(tenant, lang)]`; steps 3-4 from `cache[(tenant, D)]`. A sentinel value (e.g. empty hash → store a `__loaded__` marker) distinguishes "cache built, key genuinely absent" from "cache cold", so a missing key doesn't trigger a DB reload every call.

3. **Language resolution** (spec §427): `account.preferred_lang` → `tg_user.language_code` → tenant default. The chosen lang must be in `tenant_languages` with `enabled=true`; otherwise fall back to the tenant default. The tenant default = the `tenant_languages` row with `is_default=true` (guaranteed unique by a partial index).

4. **`Translator`** is the handler-facing surface: built once per update by the middleware, holds `(tenant_id, lang, default_lang)`, and `await translator(key, default=None, **vars)` resolves via the cache (opening its own short-lived session only on a cache miss). API/admin code uses the lower-level `resolve_string`/`t` functions directly.

5. **No hard dependency inversion:** `quantuum/i18n/` may import db + redis layers, but the bot handlers depend on `i18n` (not vice versa).

---

## File Structure

Created:
- `src/quantuum/i18n/__init__.py` — re-exports `Translator`, `t`, `resolve_lang`, `invalidate_i18n`
- `src/quantuum/i18n/strings.py` — DB access (load platform strings, overrides, tenant languages/default)
- `src/quantuum/i18n/cache.py` — Redis hash build / get / invalidate (+ pub/sub seam)
- `src/quantuum/i18n/resolver.py` — `t`, `Translator`, `resolve_lang`, `safe_format`
- `src/quantuum/i18n/seed_strings.py` — the canonical `BASE_STRINGS` (ru + en) for the customer bot UI
- Tests per task

Modified:
- `src/quantuum/db/models.py` — 5 new models
- `alembic/versions/f5e6a7b8c9d0_i18n_tables.py` — migration
- `src/quantuum/db/bootstrap.py` — `ensure_base_strings`, `ensure_tenant_default_language`
- `src/quantuum/bot/middleware/account.py` — inject `data["i18n"]` + `data["lang"]`
- `src/quantuum/bot/ui/text.py` — keep render helpers but source strings via passed-in translator (or move to keys)
- `src/quantuum/bot/handlers/{start,menu,profile,generate,history,buy}.py` — use `i18n` from handler data
- API/bot startup paths that run bootstrap (api/app.py lifespan, bot polling.py, runner.py) — call the new bootstrap seeders

---

## Phase 1 — Data model

### Task 1: i18n models + migration

**Files:**
- Modify: `src/quantuum/db/models.py`
- Create: `alembic/versions/f5e6a7b8c9d0_i18n_tables.py`
- Test: `tests/test_i18n_models.py`

Add to `models.py` (follow existing style — `_dt_field`, `JSONB`, `Index`/`UniqueConstraint` via `__table_args__`):

```python
class PlatformConfig(SQLModel, table=True):
    __tablename__ = "platform_config"
    key: str = Field(primary_key=True)
    value_jsonb: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    updated_at: datetime = _dt_field(default_factory=utcnow)
    updated_by_account_id: int | None = Field(default=None, foreign_key="accounts.id")


class TenantConfig(SQLModel, table=True):
    __tablename__ = "tenant_config"
    tenant_id: int = Field(foreign_key="tenants.id", primary_key=True)
    key: str = Field(primary_key=True)
    value_jsonb: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    updated_at: datetime = _dt_field(default_factory=utcnow)
    updated_by_account_id: int | None = Field(default=None, foreign_key="accounts.id")


class PlatformString(SQLModel, table=True):
    __tablename__ = "platform_strings"
    key: str = Field(primary_key=True)
    lang: str = Field(primary_key=True)
    text: str


class TenantStringOverride(SQLModel, table=True):
    __tablename__ = "tenant_string_overrides"
    tenant_id: int = Field(foreign_key="tenants.id", primary_key=True)
    key: str = Field(primary_key=True)
    lang: str = Field(primary_key=True)
    text: str
    updated_at: datetime = _dt_field(default_factory=utcnow)
    updated_by_account_id: int | None = Field(default=None, foreign_key="accounts.id")


class TenantLanguage(SQLModel, table=True):
    __tablename__ = "tenant_languages"
    tenant_id: int = Field(foreign_key="tenants.id", primary_key=True)
    lang: str = Field(primary_key=True)
    enabled: bool = True
    is_default: bool = False
    created_at: datetime = _dt_field(default_factory=utcnow)
```

Migration: create all 5 tables. Add the partial unique index for exactly-one default language per tenant:
```python
op.create_index(
    "uq_tenant_default_language",
    "tenant_languages",
    ["tenant_id"],
    unique=True,
    postgresql_where=sa.text("is_default = true"),
)
```
The `down_revision` is the current head `e4d5f6a7b8c9`. Confirm with `uv run alembic heads` before writing.

- [ ] **Step 1: write failing test** `tests/test_i18n_models.py` — uses the test DB session fixture; insert a `PlatformString(key="x", lang="en", text="X")`, a `TenantLanguage(tenant_id=..., lang="en", is_default=True)`, read them back; assert the partial unique index forbids a second `is_default=true` row for the same tenant (expect IntegrityError). Use the existing test session fixtures (see other `tests/test_*` for the `session`/`default_tenant` fixtures).
- [ ] **Step 2:** run `uv run pytest tests/test_i18n_models.py -v` → FAIL.
- [ ] **Step 3:** add models + migration.
- [ ] **Step 4:** the test DB uses `SQLModel.metadata.create_all` (no alembic) — so the models alone make the table; verify the test passes. ALSO verify the migration is valid: `DATABASE_URL=postgresql+asyncpg://quantuum:quantuum@172.29.0.2:5432/quantuum uv run alembic upgrade head` then `uv run alembic check` (per the app-DB memory: alembic only works against bridge IP 172.29.0.2). If the app DB is unreachable in this environment, at minimum run `uv run alembic upgrade head --sql` to confirm the migration script is syntactically valid offline.
- [ ] **Step 5:** `uv run ruff check .`; commit `feat(5a): i18n data model (config, strings, overrides, languages) + migration`.

---

## Phase 2 — Resolver, cache, language resolution

### Task 2: string DB access (`strings.py`)

**Files:** Create `src/quantuum/i18n/__init__.py` (empty for now), `src/quantuum/i18n/strings.py`; Test `tests/test_i18n_strings.py`.

Implement (all `async`, take `session`):
- `load_platform_strings(session, lang) -> dict[str, str]` — all `platform_strings` rows for `lang`.
- `load_tenant_overrides(session, tenant_id, lang) -> dict[str, str]`.
- `merged_strings(session, tenant_id, lang) -> dict[str, str]` — platform overlaid with tenant overrides.
- `get_tenant_default_lang(session, tenant_id) -> str | None` — the `tenant_languages` row where `is_default`.
- `get_enabled_langs(session, tenant_id) -> set[str]` — enabled langs for the tenant.

- [ ] Step 1: failing test — seed platform strings + a tenant override for one key; assert `merged_strings` overlays the override on top; assert `get_tenant_default_lang` returns the default; `get_enabled_langs` returns enabled set.
- [ ] Step 2: FAIL. Step 3: implement. Step 4: PASS + ruff. Step 5: commit `feat(5a): i18n string DB access (merged strings, tenant default/enabled langs)`.

### Task 3: resolver + safe_format (`resolver.py`, no cache yet)

**Files:** Create `src/quantuum/i18n/resolver.py`; Test `tests/test_i18n_resolver.py`.

Implement:
- `safe_format(template: str, vars: dict) -> str` — `str.format_map` with a defaultdict-like that leaves unknown `{x}` intact (so a template with an unfilled placeholder doesn't raise). Implement via a custom `dict` subclass returning `"{" + key + "}"` from `__missing__`.
- `async def t(session, key, lang, *, tenant_id, default=None, **vars) -> str` — implements the 6-step fallback using `merged_strings(tenant, lang)` (steps 1-2) and, if `lang != default_lang`, `merged_strings(tenant, default_lang)` (steps 3-4); then `default`; then `f"[missing: {key}]"` with `logger.warning("i18n_missing", key=key, lang=lang, tenant_id=tenant_id)`. Apply `safe_format(text, vars)` to whatever non-missing text is chosen (including the `default`). The `[missing]` sentinel is returned as-is (not formatted).

(No Redis yet — `t` reads the DB directly via `strings.py`. Caching is added in Task 4 transparently.)

- [ ] Step 1: failing test covering all 6 fallback steps (override hit, platform hit, default-lang fallback, arg default, missing sentinel) + `safe_format` with present and absent vars. Step 2: FAIL. Step 3: implement. Step 4: PASS + ruff. Step 5: commit `feat(5a): i18n resolver with 6-step fallback + safe_format`.

### Task 4: Redis cache + invalidation (`cache.py`), wire into resolver

**Files:** Create `src/quantuum/i18n/cache.py`; Modify `resolver.py`; Test `tests/test_i18n_cache.py` (uses the test Redis at 172.30.0.3 per the docker-loopback memory) OR a fakeredis/monkeypatched client — prefer monkeypatching `get_redis` with an in-memory async stub to keep the test hermetic.

Implement in `cache.py`:
- `_cache_key(tenant_id, lang) -> str` → `f"i18n:{tenant_id}:{lang}"`.
- `async def get_cached_strings(session, tenant_id, lang) -> dict[str, str]` — `HGETALL` the hash; if it has the `__loaded__` marker, return it (minus marker); else build via `merged_strings`, `HSET` all + `__loaded__="1"`, `EXPIRE` 3600, return.
- `async def invalidate_i18n(tenant_id, lang=None) -> None` — DELETE the `(tenant, lang)` hash (or all langs for the tenant when `lang is None` via `SCAN i18n:{tenant}:*`), then `PUBLISH i18n_invalidate` a small JSON `{tenant_id, lang}` (pub/sub consumers added later; publishing now is harmless).

Rewire `t` to read from `get_cached_strings` instead of `merged_strings` directly (the default-lang lookup also goes through the cache). Keep the DB path inside the cache builder.

- [ ] Step 1: failing test — monkeypatch an in-memory async redis stub; assert first `t` call builds the cache (one DB read), second call hits cache (no DB read — assert via a counter/spy on `merged_strings`); `invalidate_i18n` clears it so the next call rebuilds. Step 2: FAIL. Step 3: implement. Step 4: PASS + ruff. Step 5: commit `feat(5a): i18n Redis cache + invalidate (hash per tenant/lang, __loaded__ marker)`.

### Task 5: `Translator` + `resolve_lang`

**Files:** Modify `resolver.py`; Modify `src/quantuum/i18n/__init__.py` (export `Translator`, `t`, `resolve_lang`, `invalidate_i18n`); Test `tests/test_i18n_translator.py`.

- `async def resolve_lang(session, *, tenant_id, preferred_lang, tg_language_code) -> str` — pick the first of `[preferred_lang, tg_language_code]` that is in `get_enabled_langs(tenant_id)`; else `get_tenant_default_lang(tenant_id)`; if the tenant has no languages configured at all, fall back to a module constant `FALLBACK_LANG = "en"`.
- `class Translator`: `__init__(self, *, tenant_id, lang, default_lang)`; `async def __call__(self, key, default=None, **vars) -> str` → calls `t` (opening a short-lived session via `get_sessionmaker()` only when needed — or accept that `t` uses the cache and only touches DB on cache miss). Provide `@classmethod async def build(cls, session, *, tenant_id, preferred_lang, tg_language_code) -> "Translator"` that resolves lang + default_lang and returns an instance.

- [ ] Step 1: failing test — enabled langs {en, ru}, default ru; `resolve_lang` honors preferred when enabled, falls to tg code, then default; a non-enabled preferred falls back to default. `Translator.build(...)("key")` returns the resolved string. Step 2-5 as usual; commit `feat(5a): Translator + user language resolution`.

---

## Phase 3 — Seed strings + bootstrap

### Task 6: canonical bot strings (ru + en) + bootstrap seeders

**Files:** Create `src/quantuum/i18n/seed_strings.py`; Modify `src/quantuum/db/bootstrap.py`; wire into `api/app.py`, `bot/polling.py`, `bot/runner.py` startups; Test `tests/test_i18n_seed.py`.

`seed_strings.py` defines `BASE_STRINGS: dict[str, dict[str, str]]` = `{key: {"ru": "...", "en": "..."}}` covering every customer-bot string currently hardcoded (audit `ui/text.py` + inline strings in start/menu/profile/generate/history/buy). Use dotted keys, e.g. `btn.generate`, `btn.profile`, `btn.history`, `btn.help`, `status.pending`…`status.refunded`, `help.text`, `profile.title`, `profile.name`, `profile.birth_date`, `profile.birth_time`, `profile.place`, `profile.coords`, `profile.timezone`, `generate.queued`, `generate.no_quota`, `buy.menu_title`, etc. Templates use `{var}` placeholders where interpolation is needed (e.g. `profile.coords` = `"Координаты: {lat}, {lon}"`).

`bootstrap.py` additions:
- `async def ensure_base_strings(session) -> None` — idempotently upsert `BASE_STRINGS` into `platform_strings` (insert missing `(key, lang)` rows only; do NOT overwrite existing — so admin edits survive re-seeding).
- `async def ensure_tenant_default_language(session, tenant_id, lang="ru") -> None` — idempotently ensure a `tenant_languages(tenant_id, lang, enabled=True, is_default=True)` row exists (and `en` enabled non-default). Call it for the default tenant + platform tenant during bootstrap.

Wire `ensure_base_strings` + `ensure_tenant_default_language` (for default + platform tenants) into the same startup paths that already call `ensure_global_plans` / `ensure_platform_stars_provider`.

- [ ] Step 1: failing test — run `ensure_base_strings` twice; assert all BASE_STRINGS present and re-running doesn't duplicate or overwrite an edited row (edit one row, re-run, assert the edit survives). `ensure_tenant_default_language` creates exactly one default. Step 2-5; commit `feat(5a): seed platform strings (ru/en) + tenant default language bootstrap`.

---

## Phase 4 — Wire the customer bot UI to t()

### Task 7: middleware injects `data["i18n"]` + `data["lang"]`

**Files:** Modify `src/quantuum/bot/middleware/account.py`; Test `tests/test_bot_i18n_middleware.py` (or extend existing middleware test).

After resolving `account`, build a `Translator` and inject it: `data["lang"] = lang`; `data["i18n"] = translator`. Use `Translator.build(session, tenant_id=tenant_id, preferred_lang=account.preferred_lang, tg_language_code=getattr(from_user, "language_code", None))` inside the existing session block. Keep `chat_id` behavior (note the callback-vs-message `chat` quirk from memory — unchanged here).

- [ ] Step 1: failing test — drive the middleware with a fake event/account; assert `data["i18n"]` is a Translator and `data["lang"]` is set. Step 2-5; commit `feat(5a): bot middleware injects Translator + resolved lang`.

### Task 8: wire start/menu/help + profile handlers to t()

**Files:** Modify `src/quantuum/bot/ui/text.py`, `bot/handlers/start.py`, `menu.py`, `profile.py`; Test updates to the corresponding handler tests.

Replace hardcoded strings with `await i18n("key", **vars)` (the handler receives `i18n` from `data`). For `ui/text.py` render helpers (e.g. `render_profile`), convert to async functions taking the translator, or build the text in the handler from per-field keys. Keep keyboards' button labels sourced from `btn.*` keys.

- [ ] Step 1: update the start/menu/profile handler tests to assert the rendered text comes from i18n (seed a known string, assert it appears). Use a Translator built against the test tenant (seed BASE_STRINGS in the test or a minimal subset). Step 2-5; commit `feat(5a): wire start/menu/profile bot UI to i18n`.

### Task 9: wire generate/history/buy handlers to t()

**Files:** Modify `bot/handlers/generate.py`, `history.py`, `buy.py`; Test updates.

Same approach: replace inline strings (e.g. "Бесплатная генерация уже использована…", status labels via `status.*`, buy menu) with `i18n` keys. The `status_ru` helper becomes `status_label(status, i18n)` resolving `status.{status}`.

- [ ] Step 1: update generate/history/buy handler tests to assert i18n-sourced text. Step 2-5; commit `feat(5a): wire generate/history/buy bot UI to i18n`.

---

## Self-review checklist (run after writing, before execution)
- Fallback chain matches spec §414 exactly (6 steps, default-lang via cache too). ✓
- Partial unique index guarantees one default language per tenant. ✓
- `ensure_base_strings` is non-destructive (admin edits survive re-seed). ✓
- Cache miss vs genuinely-absent key distinguished by `__loaded__` marker (no per-call DB storms). ✓
- Bot handlers depend on i18n; i18n does not import bot. ✓
- Re-seeding idempotent; bootstrap wired into all startup paths. ✓

## Deploy notes
- Run `alembic upgrade head` against the app DB for the i18n tables migration.
- On deploy, bootstrap auto-seeds `platform_strings` (ru/en) and the default/platform tenants' default language; no manual step.
- New Redis keys `i18n:{tenant}:{lang}` (TTL 1h) and a `i18n_invalidate` pub/sub channel (consumers wired in Plan 5b).
