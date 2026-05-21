# Q&A Astrologer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox (`- [ ]`) steps.

**Goal:** One-shot grounded Q&A — the user asks a free-form question, the worker answers via LLM using only their calculated chart (`calc_md`), delivered via bot (`/ask`) and API (`POST/GET /v1/me/qa`), billed through the existing quota.

**Architecture:** Mirrors the blueprint pipeline exactly. New `qa_answers` table, `domain/qa.py`, `llm/qa_answer.py` + prompt, `tasks/qa.py` (`qa_generate` arq task), API routes in `me.py`, bot handler `handlers/qa.py`. Spec: `docs/superpowers/specs/2026-05-21-qa-astrologer-design.md`.

**Tech Stack:** SQLModel/Alembic, arq, aiogram 3, the existing LLM client + `get_llm_config` (5d), i18n (`Translator`/`BASE_STRINGS`), pytest. No new deps.

**Reference patterns to mirror (read these):** `tasks/blueprint.py` (task shape: status transitions, refund-on-failure, best-effort delivery, `complete_request` in its own try), `domain/blueprints.py` (create/get/set_status), `api/routes/me.py:98-127` (POST blueprint: consume_quota→create_request→create→enqueue, 402 on InsufficientFundsError, refund+503 on enqueue fail), `tasks/enqueue.py`, `bot/handlers/generate.py` + `buy.py` (quota + buy-offer keyboard), `llm/blueprint_polish.py` (prompt loading + user-message wrap).

---

## Task 1: `qa_answers` model + migration

**Files:** Modify `src/quantuum/db/models.py`; Create `alembic/versions/b7c8d9e0f1a2_qa_answers.py`; Test `tests/test_qa_models.py`.

Model (mirror `Blueprint`):
```python
class QaAnswer(SQLModel, table=True):
    __tablename__ = "qa_answers"
    __table_args__ = (Index("ix_qa_answers_tenant_created", "tenant_id", "created_at"),)
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    natal_profile_id: int = Field(foreign_key="natal_profiles.id")
    blueprint_id: int | None = Field(default=None, foreign_key="blueprints.id")
    question: str
    answer_md: str | None = None
    lang: str | None = None
    status: str = "pending"  # pending|generating|done|failed
    error: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)
    completed_at: datetime | None = _dt_field(default=None)
```
Migration: `down_revision = "a6b7c8d9e0f1"`, `revision = "b7c8d9e0f1a2"`; create_table + the index. Downgrade drops both. Confirm single head with `uv run alembic heads`; validate `uv run alembic upgrade head --sql` (live app DB may be unreachable — see app-db memory).

- [ ] Step 1: failing test (`session` fixture) — insert a QaAnswer (needs tenant+account+natal_profile rows) → read back; status default "pending". Step 2: FAIL. Step 3: model + migration. Step 4: PASS. Step 5: ruff + commit `feat(qa): qa_answers model + migration`.

## Task 2: `domain/qa.py`

**Files:** Create `src/quantuum/domain/qa.py`; Test `tests/test_qa_domain.py`.

```python
async def create_qa(session, *, tenant_id, account_id, natal_profile_id, question, lang) -> QaAnswer
async def get_qa(session, qa_id) -> QaAnswer    # raise NotFoundError if missing (mirror get_blueprint)
async def list_qa(session, *, account_id, limit=50, offset=0) -> list[QaAnswer]   # newest first
async def set_qa_status(session, qa_id, status, **fields) -> None   # mirror blueprints.set_status; sets completed_at on done|failed
async def resolve_calc_md(session, *, account_id, natal_profile_id) -> tuple[str, int | None]
```
`resolve_calc_md`: query the latest `Blueprint` for this account with `status=="done"` and non-null `calc_md`, ordered `created_at DESC`; if found return `(blueprint.calc_md, blueprint.id)`; else `from quantuum.astrology.blueprint import build_blueprint, from_natal_profile`; load the NatalProfile; return `(build_blueprint(from_natal_profile(profile)), None)`.

- [ ] Step 1: failing tests — create/get/list; `set_qa_status("done", answer_md="x")` sets completed_at; `resolve_calc_md` returns a done blueprint's calc_md + its id when present; when no blueprint, builds from natal_profile and returns blueprint_id None (assert the built calc_md starts with "# Quantuum Blueprint —"). Step 2-5: FAIL → implement → PASS + ruff → commit `feat(qa): qa domain (create/get/list/status + calc_md resolution)`.

## Task 3: `llm/qa_answer.py` + prompt

**Files:** Create `src/quantuum/llm/prompts/qa_astrologer.txt`, `src/quantuum/llm/qa_answer.py`; Test `tests/test_qa_answer.py`.

`qa_astrologer.txt` (system prompt) — a grounded astrologer:
- Answer the user's question using ONLY facts present in the provided calculated chart Markdown. Never invent, alter, or "correct" any placement/number/sign/gate/house. If the chart lacks what's needed, say so plainly.
- Answer in the SAME language as the question.
- Concise, warm, practical; Markdown only; no process notes, no "based on the provided data", don't mention an LLM.
(Model it on the discipline of `astrology/prompt.txt` but for a single focused question.)

`qa_answer.py`:
```python
from pathlib import Path
PROMPT_PATH = Path(__file__).parent / "prompts" / "qa_astrologer.txt"

async def qa_answer(client, calc_md, question, *, model, temperature, max_tokens):
    system = PROMPT_PATH.read_text()
    user = "\n".join([
        "Answer the user's question using only the calculated chart below.",
        "", "CALCULATED CHART:", calc_md, "", "QUESTION:", question,
    ])
    return await client.complete(system=system, user=user, model=model, temperature=temperature, max_tokens=max_tokens)
```

- [ ] Step 1: failing test — a `FakeLLM` (returns LLMResult); `qa_answer(fake, "# chart", "What is my Sun?", model="m", temperature=0.5, max_tokens=900)` → returns the result; the captured call's `user` contains "CALCULATED CHART:", "# chart", "QUESTION:", and the question; `system` contains a distinctive phrase from the prompt. Step 2-5: FAIL → implement (+ copy/write the prompt file) → PASS + ruff → commit `feat(qa): qa_answer LLM helper + grounded astrologer prompt`.

## Task 4: `tasks/qa.py` (`qa_generate`) + enqueue + worker registration

**Files:** Create `src/quantuum/tasks/qa.py`; Modify `src/quantuum/tasks/enqueue.py`, `src/quantuum/tasks/worker.py`; Test `tests/test_task_qa.py`.

`qa_generate(ctx, qa_id, chat_id=None, request_id=None)` — mirror `blueprint_generate`:
```
delivery_md = None
async with sessionmaker() as session:
    try:
        qa = await get_qa(session, qa_id)
        calc_md, blueprint_id = await resolve_calc_md(session, account_id=qa.account_id, natal_profile_id=qa.natal_profile_id)
        await set_qa_status(session, qa_id, "generating", blueprint_id=blueprint_id)
        llm_client = ctx.get("llm_client")
        if llm_client is None:
            await set_qa_status(session, qa_id, "failed", error="llm unavailable")
            if request_id is not None: await refund_quota(session, request_id)
            return
        cfg = await get_llm_config(session)
        result = await qa_answer(llm_client, calc_md, qa.question, model=cfg["model"], temperature=cfg["temperature"], max_tokens=cfg["max_tokens"])
        await set_qa_status(session, qa_id, "done", answer_md=result.text, llm_provider=cfg["provider"], llm_model=result.model, llm_tokens_in=result.tokens_in, llm_tokens_out=result.tokens_out)
        delivery_md = result.text
        if request_id is not None:
            try: await complete_request(session, request_id, reference_id=qa_id, reference_type="qa")
            except Exception: logger.exception("qa_complete_request_failed", qa_id=qa_id)
    except Exception:
        logger.exception("qa_generation_failed", qa_id=qa_id)
        try: await set_qa_status(session, qa_id, "failed", error="generation failed")
        except Exception: logger.exception("qa_set_failed_status_error", qa_id=qa_id)
        if request_id is not None: await refund_quota(session, request_id)
        return
# best-effort delivery (no refund)
if chat_id is not None and delivery_md is not None:
    try:
        await bot.send_message(chat_id, delivery_md[:4000])
        if len(delivery_md) > 4000:
            await bot.send_document(chat_id, BufferedInputFile(delivery_md.encode(), filename="answer.md"))
    except Exception: logger.exception("qa_delivery_failed", qa_id=qa_id, chat_id=chat_id)
```
`enqueue.py`: `async def enqueue_qa(qa_id, chat_id=None, request_id=None): pool=...; await pool.enqueue_job("qa_generate", qa_id, chat_id, request_id)`.
`worker.py`: import `qa_generate`, add to `functions=[...]`.

- [ ] Step 1: failing tests (mirror tests/test_task_blueprint.py setup: tenant+account+natal_profile; build a fake ctx with sessionmaker+bot+llm_client) — happy path: `qa_generate` with a FakeLLM → status done, answer_md set, tokens recorded, bot.send_message awaited; failure: FakeLLM.complete raises → status failed + quota refunded; `llm_client=None` → status failed + refunded. Step 2-5: FAIL → implement → PASS (targeted) + ruff → commit `feat(qa): qa_generate task + enqueue + worker registration`.

## Task 5: API routes `/v1/me/qa`

**Files:** Modify `src/quantuum/api/routes/me.py`, `src/quantuum/api/schemas.py`; Test `tests/test_api_qa.py`.

Schemas: `QaCreateIn(question: str)`, `QaCreatedOut(id: int, status: str)`, `QaOut(id, question, answer_md: str|None, status, lang: str|None, created_at, completed_at: datetime|None)`.

Routes (auth `current_account`, scope = account):
- `POST /v1/me/qa` — load the caller's natal_profile (404 if none, detail "natal profile required"); validate question non-empty + ≤1000 (422/400 if empty, trim to 1000); resolve `lang` (the account's `preferred_lang` or "ru" fallback — keep simple; the LLM mirrors the question language anyway); `consume_quota(account.id, "qa")` (402 on InsufficientFundsError); `create_request(kind="qa", charged_against=charged)`; `create_qa(... question, lang)`; `enqueue.enqueue_qa(qa.id, None, request.id)` (on enqueue failure: refund_quota + 503, mirror blueprint); return `202 QaCreatedOut`.
- `GET /v1/me/qa/{qa_id}` — `get_qa`; 404 if missing or `qa.account_id != account.id`; return QaOut.
- `GET /v1/me/qa?limit=&offset=` — `list_qa(account_id=account.id, ...)` → list[QaOut].

- [ ] Step 1: failing tests (use the customer_headers/client pattern from tests/test_api_*; seed a natal_profile + give the account quota e.g. an active subscription or package_credits) — POST without profile → 404; POST without quota → 402; POST with quota → 202 {id,status:"pending"} + a Request(kind="qa") + qa row + enqueue called (monkeypatch enqueue.enqueue_qa to a spy); GET own qa → 200; GET another account's qa → 404; list returns the caller's, newest first. Step 2-5: FAIL → implement → PASS + ruff → commit `feat(qa): /v1/me/qa API (post/get/list)`.

## Task 6: bot `/ask` handler + i18n + dispatcher registration

**Files:** Create `src/quantuum/bot/handlers/qa.py`; Modify `src/quantuum/i18n/seed_strings.py` (add `qa.*` + `btn.ask`), `src/quantuum/bot/app.py` (register router), `src/quantuum/bot/ui/keyboards.py`/`menu.py` (add the menu button + route it); Test `tests/test_qa_bot.py`.

Add BASE_STRINGS keys (ru+en): `qa.no_profile`, `qa.no_quota`, `qa.thinking`, `qa.too_long`, `qa.ask_prompt`, `qa.failed`, `btn.ask` ("❓ Спросить астролога" / "❓ Ask the astrologer"), `qa.cancel`.

Handler (`qa.router`):
- `Ask(StatesGroup): awaiting_question = State()`.
- `@router.message(Command("ask"))` `on_ask(message, command, state, account, i18n)`: if `command.args` present, treat as the question → `_submit`; else set FSM `awaiting_question` + reply `qa.ask_prompt` (+ cancel kb).
- Menu button "❓ Спросить астролога" (label = `btn.ask`): same as `/ask` with no args → FSM prompt. (Add the button to the main menu keyboard + a `menu.py` handler matching the label across langs, mirroring how other menu buttons route.)
- `@router.message(Ask.awaiting_question)` `on_ask_question(message, state, account, i18n)` → `_submit(message.text)` + `state.clear()`.
- `_submit(message, text, account, i18n)`: trim; empty → re-prompt; len>1000 → `qa.too_long`. Load natal_profile (none → `qa.no_profile`). `consume_quota(account.id,"qa")` → `InsufficientFundsError` → reply `qa.no_quota` + buy-offer kb (reuse `_buy_offer_kb`/`BuyCb action="open"` from generate.py/buy.py). Else `create_request(kind="qa", charged_against=...)` + `create_qa(... lang=i18n.lang)` + `enqueue_qa(qa.id, chat_id, request.id)` → reply `qa.thinking`.
- Register `qa.router` in `bot/app.py` after `buy.router` (before generate is fine; ensure `/ask` Command doesn't collide — it won't).

- [ ] Step 1: failing tests (mirror tests/test_generate_no_quota_offer.py + the FSM pattern) — `/ask вопрос` with quota → consumes quota, creates qa+request, enqueues (spy), replies thinking; no quota → buy offer; no profile → qa.no_profile; FSM: `/ask` (no args) → prompt, then a message → submits; too-long → qa.too_long. Use a real Translator via conftest `build_translator`. Step 2-5: FAIL → implement → PASS + ruff → commit `feat(qa): /ask bot handler + menu button + i18n`.

## Stage completion
- Full suite `uv run pytest -q` + `uv run ruff check .` + `uv run alembic heads` (single head `b7c8d9e0f1a2`).
- Holistic review (auth/scoping on qa routes, refund-on-failure incl. no-llm, delivery best-effort, i18n keys present, migration linear).
- finishing-a-development-branch → merge.

## Self-review checklist
- qa_generate mirrors blueprint: status transitions, refund only on generation failure (not delivery/complete_request), no-llm → fail+refund. ✓
- API: 404 no-profile, 402 no-quota, 503+refund on enqueue fail, cross-account 404. ✓
- consume_quota("qa"): subscribers free, others package; no trial. ✓
- One migration, single head, index in __table_args__ (test DB) + migration. ✓
- All bot strings i18n; no hardcoded Cyrillic. ✓

## Deploy notes
- `alembic upgrade head` (qa_answers). `LLM_API_KEY` REQUIRED (no degraded fallback). Register `qa_generate` in task-worker (rebuild image). New bot strings auto-seed.
