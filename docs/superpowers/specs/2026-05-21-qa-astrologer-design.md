# Q&A Astrologer — Design Spec

**Status:** Approved design (brainstorming). First sub-project of the §24 "future" feature wave (Q&A, transits, compatibility); transits & compatibility get their own spec→plan cycles later.

**One-liner:** A grounded conversational astrologer — the user asks a free-form question and gets an LLM answer derived **only** from their deterministically-calculated chart (`calc_md`), delivered via the bot and the public API, billed through the existing quota model.

---

## 1. Goals / non-goals

**Goals**
- One-shot Q&A: each question is independent and grounded in the asker's own chart.
- Reuse everything already built: the astrology engine (`build_blueprint`/`calc_md`), the LLM client + DB-backed config, the request/quota/billing ledger, the arq worker, i18n.
- Available on the bot (`/ask` + menu button) and the public API (`POST /v1/me/qa`, `GET`).

**Non-goals (this sub-project)**
- Multi-turn threaded conversation (chosen: one-shot).
- New billing/credit types (chosen: reuse `consume_quota`).
- Transits / personal-year / compatibility (separate sub-projects).
- Content moderation beyond the prompt's fact-discipline guardrails.

---

## 2. Decisions (locked during brainstorming)

| Decision | Choice |
|---|---|
| Monetization | Reuse `consume_quota("qa")`: active **subscribers free** (no per-question limit), others spend **one package credit** (shared pool with blueprints). **No free trial** for `qa` (trial is blueprint-only). |
| Dialog model | **One-shot** (stateless per question). |
| Surface | **Bot + public API.** |
| Grounding | Use the latest **done** `Blueprint.calc_md` if one exists; else `build_blueprint(from_natal_profile(profile))` on the fly. Requires a `natal_profile`. |
| Execution | **Async via arq** (`qa_generate`), mirroring `blueprint_generate` — the task-worker is the only process with `llm_client`. |

---

## 3. Data model

New table (mirrors the `blueprints` shape):
```
qa_answers
  id              PK
  tenant_id       FK tenants.id        (index)
  account_id      FK accounts.id       (index)
  natal_profile_id FK natal_profiles.id
  blueprint_id    FK blueprints.id, nullable   -- the blueprint whose calc_md was used, if any
  question        text
  answer_md       text, nullable
  lang            text                 -- answer language (resolved from the asker)
  status          text  default 'pending'   -- pending|generating|done|failed
  error           text, nullable
  llm_provider    text, nullable
  llm_model       text, nullable
  llm_tokens_in   int,  nullable
  llm_tokens_out  int,  nullable
  created_at      timestamptz
  completed_at    timestamptz, nullable
  __table_args__: Index(tenant_id, created_at DESC)
```
A new Alembic migration creates it (down_revision = current head `a6b7c8d9e0f1`). Declare the index in `__table_args__` so the test DB (`create_all`) enforces it too.

The generic ledger row: `Request(kind="qa", reference_id=qa.id, reference_type="qa", charged_against=<result of consume_quota>)`.

---

## 4. Components & data flow

### Domain — `quantuum/domain/qa.py`
- `create_qa(session, *, tenant_id, account_id, natal_profile_id, question, lang) -> QaAnswer` — insert pending row.
- `get_qa(session, qa_id) -> QaAnswer | None`; `list_qa(session, *, account_id, limit, offset)`.
- `set_qa_status(session, qa_id, status, **fields)` — mirror `blueprints.set_status` (sets `completed_at` on terminal states).
- `resolve_calc_md(session, *, account_id, natal_profile_id) -> tuple[str, int | None]` — returns `(calc_md, blueprint_id | None)`: if the account has a latest **done** Blueprint, reuse its `calc_md` (+ its id); else `build_blueprint(from_natal_profile(profile))` and `blueprint_id=None`.

### LLM — `quantuum/llm/qa_answer.py` + `prompts/qa_astrologer.txt`
- `qa_astrologer.txt` (system prompt): a grounded astrologer. Rules: answer the user's question using **only** facts present in the provided calculated chart markdown; never invent or alter placements/numbers; if the chart doesn't contain what's needed, say so plainly; answer in the **same language as the question**; concise, warm, practical; Markdown only; no process notes.
- `async def qa_answer(client, calc_md, question, *, model, temperature, max_tokens) -> LLMResult` — `user = "\n".join(["Answer the user's question using only the calculated chart below.", "", "CALCULATED CHART:", calc_md, "", "QUESTION:", question])`; `client.complete(system=<prompt>, user=user, model=, temperature=, max_tokens=)`.

### Task — `quantuum/tasks/qa.py: qa_generate(ctx, qa_id, chat_id=None, request_id=None)`
Mirror `blueprint_generate`:
1. Load qa + natal_profile. `calc_md, blueprint_id = resolve_calc_md(...)`. `set_qa_status(generating, blueprint_id=blueprint_id)`.
2. `llm_client = ctx.get("llm_client")`. **If None → fail + refund** (Q&A has no meaningful no-LLM output): `set_qa_status(failed, error="llm unavailable")`, `refund_quota`, return.
3. `cfg = await get_llm_config(session)`; `result = await qa_answer(llm_client, calc_md, qa.question, model=cfg["model"], temperature=cfg["temperature"], max_tokens=cfg["max_tokens"])`. `set_qa_status(done, answer_md=result.text, llm_provider=cfg["provider"], llm_model=result.model, llm_tokens_in=..., llm_tokens_out=...)`.
4. `complete_request(request_id, reference_id=qa_id, reference_type="qa")` (own try, never refunds — same nuance as the 5d invite/complete_request fix).
5. On exception → `failed` + `refund_quota`, return.
6. Delivery (best-effort, outside the session, no refund): `bot.send_message(chat_id, answer_md[:4000])`; if longer, also `send_document(BufferedInputFile(answer_md.encode(), "answer.md"))`.

Register `qa_generate` in `tasks/worker.py functions`. `enqueue_qa_generate(qa_id, chat_id, request_id)` in `tasks/enqueue.py` (mirror the blueprint enqueue).

### Bot — `quantuum/bot/handlers/qa.py`
- `/ask <question>` (Command) and a menu button "❓ Спросить астролога" → FSM `Ask.awaiting_question` if no inline text.
- Validate: question non-empty, ≤ 1000 chars (trim/`qa.too_long`). Require a `natal_profile` (else `qa.no_profile`).
- `consume_quota(account_id, "qa")` → `InsufficientFundsError` → reply `qa.no_quota` + the existing buy-offer keyboard (reuse `BuyCb action="open"`). Else: `create_request(kind="qa", charged_against=result)` + `create_qa(pending)` + `enqueue_qa_generate(qa.id, chat_id, request.id)` → reply `qa.thinking`.
- Register `qa.router` on the customer dispatcher (`bot/app.py`), after `buy.router`. (Master bot unaffected.)
- All strings via the injected `i18n`.

### API — `quantuum/api/routes/me.py` (or a small `me_qa` section)
- `POST /v1/me/qa {question}` (auth = customer) → require natal_profile (404/409 if none), `consume_quota` (402 `InsufficientFundsError`), create request + qa, enqueue → `202 {id, status:"pending"}`.
- `GET /v1/me/qa/{id}` → qa detail (answer when done); 404 if not the caller's.
- `GET /v1/me/qa?limit=&offset=` → history (caller's, newest first).
- Schemas: `QaCreateIn(question)`, `QaCreatedOut(id, status)`, `QaOut(id, question, answer_md, status, lang, created_at, completed_at)`.

---

## 5. i18n
New `qa.*` keys in `BASE_STRINGS` (ru + en): `qa.no_profile`, `qa.no_quota`, `qa.thinking`, `qa.too_long`, `qa.ask_prompt` (FSM prompt), `qa.answer_header` (optional prefix), `qa.failed`, plus `btn.ask` and `qa.cancel`. The answer body itself is produced by the LLM in the question's language (not a seeded string).

---

## 6. Error handling
- LLM failure / no `llm_client` → `qa_answers.status="failed"` + `refund_quota` (the asker is not charged).
- Delivery failure (bot) → logged, **no** refund (the answer is stored; the user can fetch via API/history).
- `complete_request` wrapped so a bookkeeping failure can't trigger a refund of a successful answer.
- Missing natal_profile → handled before quota is consumed (no charge).

## 7. Testing
- **domain/qa**: create/get/list/status; `resolve_calc_md` reuses a done blueprint's calc_md when present, else builds one (assert blueprint_id None vs set).
- **llm/qa_answer**: with a fake client, asserts the prompt is loaded and the user message wraps calc_md + question.
- **task/qa_generate**: mocked llm_client → answer stored + tokens + delivered; exception → failed + refund; `llm_client=None` → failed + refund.
- **bot/qa**: `/ask` happy path (quota consumed, qa+request created, enqueued, "thinking" reply); no-quota → buy offer; no-profile → prompt; FSM question capture; too-long.
- **api/qa**: POST 202 + GET detail + list; 402 on no quota; 404/cross-account scoping.
- One migration; `alembic heads` single linear head; validate via `--sql` (live app DB may be unreachable — see the app-db memory).

## 8. Deploy notes
- `alembic upgrade head` for `qa_answers`.
- `LLM_API_KEY` is **required** for Q&A to work (no degraded fallback, unlike blueprints).
- New bot strings auto-seed via `ensure_base_strings`.
- Register `qa_generate` in the task-worker (rebuild image); register `qa.router` on the customer bot dispatcher.

## 9. Future (out of scope here)
- Multi-turn threads (would add a `qa_threads` table + context-window management).
- Q&A over transits/compatibility once those engines exist.
- Per-question rate limiting for subscribers (currently unlimited for active subs).
