# Content Moderation / Safety — Design

**Date:** 2026-05-27
**Scope:** SP1 of the platform-plumbing feature wave (content-moderation → tenant-feature-toggle → white-label → referrals → gifts → tarot).
**Goal:** Pre-LLM filter on free-text QA input. Block trigger topics (self-harm, violence, sexual-minors, hate, medical/legal advice) and emit a canonical, localized response instead of calling the LLM. Do not charge quota on a moderation hit.

---

## 1. Scope and non-goals

**In scope.** Free-text user input that reaches the LLM. Currently the **only** such surface is `bot/handlers/qa.py::_submit()`. Every other ingest path is structured (name / date / time / place / button callbacks).

**Out of scope.**
- Output moderation (filtering the LLM's response).
- Blueprint / transits / daily / readings — their input is structured and bounded.
- Per-tenant toggles (covered by SP2 `tenant-feature-toggle`).
- External alerting (Sentry / Slack) — separate observability work.
- Storing cleartext of triggering messages.

---

## 2. Architecture

### 2.1 Where the check runs

In `bot/handlers/qa.py::_submit()`, **before** `consume_quota`. Rationale:

- Pre-check means we never charge the user for a blocked attempt. No refund path.
- Worker-side moderation would mean the user sees `"qa.thinking"`, then a moderation answer — confusing.
- It is also the **only** point that needs moderation right now; centralizing it in middleware is YAGNI.

If moderation returns non-`Safe`, the handler:
1. Sends the canonical localized response (helpline link when applicable).
2. Writes a `moderation_events` row.
3. Returns without creating a `qa` row, without `consume_quota`, without enqueueing.

### 2.2 New package

```
src/quantuum/moderation/
├── __init__.py
├── classifier.py      # moderate(text, lang) -> ModerationVerdict
├── policy.py          # category → action map; canonical i18n keys
├── events.py          # record_moderation_event(session, ...)
└── prompts/
    └── advice_classifier.txt  # mini-LLM prompt for Tier2
```

### 2.3 Detection pipeline

```python
async def moderate(text: str, lang: str, llm_client) -> ModerationVerdict:
    # Run Tier1 (OpenAI Moderation API) and Tier2 (mini-LLM advice classifier)
    # in parallel for latency. Tier1 errors → fail-open.
    tier1, tier2 = await asyncio.gather(
        _openai_moderate(text),
        _llm_advice_classifier(text, lang, llm_client),
        return_exceptions=True,
    )
    if isinstance(tier1, Tier1Hit):
        return tier1  # Safety wins over scope
    if isinstance(tier2, Tier2Hit):
        return tier2
    return Safe()
```

- **Tier1** uses `omni-moderation-latest` via the OpenAI Moderation endpoint. It is free, fast (~50ms), multilingual, and covers safety categories well.
- **Tier2** uses a cheap model (gpt-4o-mini-class) configured via env `MODERATION_ADVICE_MODEL`, falling back to `cfg["model"]`. Prompt returns strict JSON `{"category": "medical" | "legal" | "safe"}`. Adds ~200–400ms.
- Total added latency at handler time: ≤ 400ms (parallel gather, dominated by Tier2).

### 2.4 Fail-open policy

If `_openai_moderate` raises (network, 5xx, rate limit) → treat as Safe and emit `moderation.api_error` log. Same for `_llm_advice_classifier`. Rationale: we are an astrology product, not a clinical system; outage of the moderation provider should not break QA. A `MODERATION_FAIL_OPEN = True` env knob lets ops flip this in incident response.

### 2.5 Kill switch

`settings.MODERATION_ENABLED: bool = True`. When `False`, `moderate()` returns `Safe()` unconditionally without making any API call. Useful for tests and emergency disable.

---

## 3. Categories and actions

| Category         | Tier | Source             | Action           | i18n key                       | Helpline |
|------------------|------|--------------------|------------------|--------------------------------|----------|
| `self_harm`      | 1    | OpenAI Moderation  | `soft_redirect`  | `moderation.self_harm`         | yes      |
| `violence`       | 1    | OpenAI Moderation  | `hard_block`     | `moderation.violence`          | no       |
| `sexual_minors`  | 1    | OpenAI Moderation  | `hard_block`     | `moderation.blocked_generic`   | no       |
| `hate`           | 1    | OpenAI Moderation  | `soft_redirect`  | `moderation.hate`              | no       |
| `medical_advice` | 2    | mini-LLM           | `soft_redirect`  | `moderation.medical`           | no       |
| `legal_advice`   | 2    | mini-LLM           | `soft_redirect`  | `moderation.legal`             | no       |

`soft_redirect` vs `hard_block` differ only in i18n tone and `events.action` enum value — both skip the LLM call and the quota charge. The distinction exists for downstream analytics: hard-blocks are policy-violations, soft-redirects are scope-redirects.

The `helpline_url` in `moderation.self_harm` is `https://findahelpline.com/topics/suicidal-thoughts` (international aggregator, supports 130+ countries). Stored in `i18n` as a substitution variable, not hard-coded in code.

---

## 4. Data model

New table `moderation_events`:

| Column         | Type          | Notes                                   |
|----------------|---------------|-----------------------------------------|
| `id`           | int PK        |                                         |
| `account_id`   | int FK        | nullable for anonymous edge cases       |
| `tenant_id`    | int FK        |                                         |
| `lang`         | str(8)        | user's locale at submission time        |
| `category`     | enum string   | one of the 6 categories above           |
| `action`       | enum string   | `soft_redirect` \| `hard_block`         |
| `source`       | enum string   | `openai` \| `mini_llm`                  |
| `text_sha256`  | bytes(32)     | SHA-256 of the raw input                |
| `text_preview` | str(80)       | first 80 chars, hard-truncated          |
| `created_at`   | datetime      | utc, indexed                            |

Privacy posture:
- Raw text is never persisted.
- `text_preview` is a debugging aid for support, capped at 80 chars to avoid leaking longer PII.
- `text_sha256` enables grouping repeated identical submissions from the same account without storing content.

Indexes: `(account_id, created_at)` for "how often does X trigger moderation", `(category, created_at)` for category-level trends.

Alembic migration adds the table; no backfill needed.

---

## 5. i18n strings

13 new keys (6 user-facing messages + helpline URL variable + `moderation.api_error` log marker):

| Key                            | Type     | Example (RU)                                                                                  |
|--------------------------------|----------|-----------------------------------------------------------------------------------------------|
| `moderation.self_harm`         | message  | "Если ты сейчас в трудной точке — обратись за поддержкой: {helpline_url}. Рядом."             |
| `moderation.violence`          | message  | "Этот вопрос за пределами того, чем я могу помочь."                                           |
| `moderation.hate`              | message  | "Я тут не для этого."                                                                         |
| `moderation.medical`           | message  | "Это вопрос к врачу, не к астрологу. Клинических рекомендаций не даю."                        |
| `moderation.legal`             | message  | "Это к юристу. Я говорю про энергии и циклы, не про правовые риски."                          |
| `moderation.blocked_generic`   | message  | "Этот запрос невозможен."                                                                     |
| `moderation.helpline_url`      | constant | `https://findahelpline.com/topics/suicidal-thoughts`                                          |

All 6 message keys added in 10 languages via `src/quantuum/i18n/seed_strings.py` and each `i18n/translations/<lang>.py`. `helpline_url` is identical across all locales (find-a-helpline auto-detects country).

---

## 6. Configuration

| Env                              | Default                     | Purpose                              |
|----------------------------------|-----------------------------|--------------------------------------|
| `MODERATION_ENABLED`             | `true`                      | kill switch                          |
| `MODERATION_FAIL_OPEN`           | `true`                      | API error → Safe                     |
| `MODERATION_OPENAI_MODEL`        | `omni-moderation-latest`    | Tier1 model id                       |
| `MODERATION_ADVICE_MODEL`        | falls back to `cfg["model"]`| Tier2 mini-LLM model id              |
| `MODERATION_ADVICE_MAX_TOKENS`   | `32`                        | mini-LLM response cap (JSON)         |
| `MODERATION_ADVICE_TEMPERATURE`  | `0.0`                       | deterministic classification         |

Settings live in `src/quantuum/settings.py` next to existing LLM settings.

---

## 7. Telemetry

Structured logs (via existing `logging_setup.get_logger`):

- `moderation.triggered` — fields: `account_id`, `tenant_id`, `category`, `action`, `source`, `text_sha256_hex` (first 16 chars), `lang`. Emitted every hit.
- `moderation.api_error` — fields: `provider` (`"openai"` \| `"mini_llm"`), `error`. Emitted on fail-open.
- `moderation.disabled` — emitted once at startup if `MODERATION_ENABLED=false`.

No external alerting in this SP. CSAM hits (`sexual_minors`) are logged at WARNING level for future alert integration.

---

## 8. Testing

### 8.1 Unit (`tests/test_moderation_classifier.py`)
- Table-driven: ~15 fixture inputs, each labeled with expected verdict.
- OpenAI Moderation client mocked at HTTP level.
- mini-LLM client mocked with `FakeLLM`-style return.
- Cases: clean astrology question → Safe; self-harm RU/EN → Tier1; medical RU → Tier2; ambiguous "хочу убить время" → Safe (not violence).
- Fail-open: `_openai_moderate` raises → result is Safe, logs `api_error`.

### 8.2 End-to-end handler (`tests/test_qa_moderation_e2e.py`)
- Use full handler stack with stubbed Tier1/Tier2.
- Trigger self_harm → assert: `moderate.triggered` log present, `moderation_events` row created with `category="self_harm"`, **zero** credits deducted, **no** `qa` row, response message matches `moderation.self_harm` rendering.
- Clean question → assert: existing flow runs untouched (quota deducted, `qa` row exists).

### 8.3 Kill switch (`tests/test_moderation_killswitch.py`)
- `MODERATION_ENABLED=false` → `moderate()` returns Safe without making API calls (assert `_openai_moderate` not invoked).

### 8.4 No regressions
- All existing `test_qa_*` tests must continue to pass with moderation enabled (clean inputs).
- All existing `test_blueprint_*`, `test_reading_*`, `test_daily_*`, `test_transit_*` tests untouched — moderation does not run on their paths.

---

## 9. Open questions / deferred

1. **Hard-coded helpline URL** assumes find-a-helpline.com stays online. Acceptable risk; URL is in i18n so swappable without code change.
2. **Per-tenant policy** (e.g., an adult-themed tenant relaxing `sexual_minors` — never; relaxing `hate` — maybe) is deferred to SP2's tenant-feature-toggle work.
3. **Output moderation** on LLM responses is deferred; current QA prompt is already heavily scoped to astrology tone, low probability of unsafe output.
4. **Hashing salt** for `text_sha256`: not adding a per-account salt now, so identical messages across accounts hash identically. This is intentional for cross-account pattern detection. If privacy posture tightens, add `HMAC(account_id, text)`.

---

## 10. Acceptance criteria

- `bot/handlers/qa.py::_submit()` calls `moderate()` before `consume_quota`. On non-Safe verdict: canonical message sent, no quota deducted, no `qa` row, `moderation_events` row written.
- `moderate()` handles OpenAI Moderation outage by falling back to Safe and logging.
- All 6 categories produce the expected i18n message in 10 languages.
- Kill switch (`MODERATION_ENABLED=false`) bypasses all moderation calls.
- New tests pass; no existing tests broken.
- Alembic migration applies cleanly and is reversible.
