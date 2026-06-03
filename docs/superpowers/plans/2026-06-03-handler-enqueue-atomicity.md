# Handler Enqueue Atomicity (Workstream A-handlers) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure a user is never charged a credit without a worker job being enqueued — refund the charge whenever `enqueue_*` fails in the reading/qa/transit/blueprint/divination handlers.

**Architecture:** `consume_quota` and `create_request` each commit internally, so by the time a handler calls `enqueue_*` (outside the DB session) the credit and `Request` row are already durable. If `enqueue_*` raises (Redis/arq down), the user is charged with no job to process. We add one shared helper, `enqueue_or_refund(coro, *, request_id)`, that awaits the enqueue coroutine and, on any exception, opens a fresh session and calls the already-idempotent `refund_quota(session, request_id)`. Every handler routes its enqueue through this helper and shows a localized "queued failed, try again" message when it returns `False`.

**Tech Stack:** aiogram handlers, SQLAlchemy async (`get_sessionmaker`), arq enqueue, pytest (`uv run pytest`), i18n seed strings + per-language translation files.

**Test command:** `uv run pytest <path> -v` (plain `pytest` fails — missing pytest_asyncio). Tests use the `session` and `default_tenant` fixtures; asyncio auto mode (no decorator).

---

### Task 1: i18n key `errors.queue_failed`

**Files:**
- Modify: `src/quantuum/i18n/seed_strings.py` (add key to BASE_STRINGS, in the "Shared / generic" block near `kb.cancel` ~line 509)
- Modify: `src/quantuum/i18n/translations/de.py`, `es.py`, `fr.py`, `hi.py`, `it.py`, `pt.py`, `tr.py`, `zh.py`
- Test: `tests/test_i18n_queue_failed_key.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_i18n_queue_failed_key.py
from quantuum.i18n.seed_strings import BASE_STRINGS

ALL_LANGS = {"ru", "en", "de", "es", "fr", "hi", "it", "pt", "tr", "zh"}


def test_queue_failed_key_present_in_all_langs():
    assert "errors.queue_failed" in BASE_STRINGS
    entry = BASE_STRINGS["errors.queue_failed"]
    assert ALL_LANGS.issubset(entry.keys())
    for lang in ALL_LANGS:
        assert entry[lang].strip(), f"empty translation for {lang}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_i18n_queue_failed_key.py -v`
Expected: FAIL — `"errors.queue_failed" not in BASE_STRINGS` (after merge it only has ru/en until translation files are updated).

- [ ] **Step 3: Add the key to BASE_STRINGS**

In `src/quantuum/i18n/seed_strings.py`, in the "Shared / generic" block (right after the `kb.cancel` entry, ~line 512), add:

```python
    "errors.queue_failed": {
        "ru": "Не удалось поставить запрос в очередь. Кредит возвращён — попробуй ещё раз чуть позже.",
        "en": "Couldn't queue your request. Your credit was refunded — please try again shortly.",
    },
```

- [ ] **Step 4: Add the key to every translation file**

Add this entry to the `TRANSLATIONS` dict in each file (place near the other shared/error keys, or at the end before the closing brace):

`src/quantuum/i18n/translations/de.py`:
```python
    "errors.queue_failed": "Anfrage konnte nicht eingereiht werden. Dein Guthaben wurde erstattet — bitte versuche es gleich noch einmal.",
```

`src/quantuum/i18n/translations/es.py`:
```python
    "errors.queue_failed": "No se pudo poner tu solicitud en cola. Se te devolvió el crédito; inténtalo de nuevo en un momento.",
```

`src/quantuum/i18n/translations/fr.py`:
```python
    "errors.queue_failed": "Impossible de mettre votre demande en file d'attente. Votre crédit a été remboursé — réessayez dans un instant.",
```

`src/quantuum/i18n/translations/hi.py`:
```python
    "errors.queue_failed": "आपका अनुरोध कतार में नहीं डाला जा सका। आपका क्रेडिट लौटा दिया गया — कृपया थोड़ी देर में फिर से प्रयास करें।",
```

`src/quantuum/i18n/translations/it.py`:
```python
    "errors.queue_failed": "Impossibile mettere in coda la richiesta. Il credito è stato rimborsato — riprova tra poco.",
```

`src/quantuum/i18n/translations/pt.py`:
```python
    "errors.queue_failed": "Não foi possível colocar seu pedido na fila. Seu crédito foi devolvido — tente novamente em instantes.",
```

`src/quantuum/i18n/translations/tr.py`:
```python
    "errors.queue_failed": "İsteğin kuyruğa alınamadı. Kredin iade edildi — lütfen birazdan tekrar dene.",
```

`src/quantuum/i18n/translations/zh.py`:
```python
    "errors.queue_failed": "无法将你的请求加入队列。积分已退回——请稍后再试。",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_i18n_queue_failed_key.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/i18n/seed_strings.py src/quantuum/i18n/translations/ tests/test_i18n_queue_failed_key.py
git commit -m "feat(i18n): errors.queue_failed key in all 10 languages"
```

---

### Task 2: `enqueue_or_refund` shared helper

**Files:**
- Create: `src/quantuum/bot/handlers/_guard.py`
- Test: `tests/test_enqueue_guard.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enqueue_guard.py
from quantuum.bot.handlers._guard import enqueue_or_refund
from quantuum.db.models import AccountBalance, Request
from quantuum.domain.billing import grant_credits
from quantuum.domain.quota import consume_quota
from quantuum.domain.requests import create_request


async def _seed_charged_request(session, default_tenant):
    from quantuum.db.models import Account
    acc = Account(tenant_id=default_tenant.id, tg_user_id=555001, role="user")
    session.add(acc)
    await session.flush()
    await grant_credits(
        session, account_id=acc.id, tenant_id=default_tenant.id, amount=3, source="manual"
    )
    await session.commit()
    charged = await consume_quota(session, acc.id, "qa")
    request = await create_request(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        kind="qa", charged_against=charged,
    )
    return acc, request


async def test_success_returns_true_no_refund(session, default_tenant):
    acc, request = await _seed_charged_request(session, default_tenant)

    async def ok():
        return None

    result = await enqueue_or_refund(ok(), request_id=request.id)
    assert result is True
    refreshed = await session.get(Request, request.id)
    await session.refresh(refreshed)
    assert refreshed.charged_against == "package"  # untouched
    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.package_credits == 2  # 3 - 1, not refunded


async def test_failure_returns_false_and_refunds(session, default_tenant):
    acc, request = await _seed_charged_request(session, default_tenant)

    async def boom():
        raise RuntimeError("redis down")

    result = await enqueue_or_refund(boom(), request_id=request.id)
    assert result is False
    refreshed = await session.get(Request, request.id)
    await session.refresh(refreshed)
    assert refreshed.charged_against == "none"
    assert refreshed.status == "refunded"
    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.package_credits == 3  # refunded back to 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enqueue_guard.py -v`
Expected: FAIL — `ModuleNotFoundError: quantuum.bot.handlers._guard`.

- [ ] **Step 3: Write the helper**

```python
# src/quantuum/bot/handlers/_guard.py
from collections.abc import Awaitable

from quantuum.db.session import get_sessionmaker
from quantuum.domain.quota import refund_quota
from quantuum.logging_setup import get_logger

logger = get_logger(__name__)


async def enqueue_or_refund(coro: Awaitable[None], *, request_id: int) -> bool:
    """Await an enqueue coroutine; refund the request's charge if it fails.

    The charge (``consume_quota``) and the ``Request`` row are already committed
    by the time a handler enqueues, so a failed enqueue would otherwise leave the
    user charged with no worker job. On failure we open a fresh session and call
    the idempotent ``refund_quota``.

    Returns True if the job was enqueued, False if it failed and was refunded.
    """
    try:
        await coro
        return True
    except Exception:
        logger.exception("enqueue_failed", request_id=request_id)
        async with get_sessionmaker()() as session:
            await refund_quota(session, request_id)
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enqueue_guard.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/_guard.py tests/test_enqueue_guard.py
git commit -m "feat(handlers): enqueue_or_refund guard for charge/enqueue atomicity"
```

---

### Task 3: Wire `readings.py`

**Files:**
- Modify: `src/quantuum/bot/handlers/readings.py:95` (the `enqueue_reading` call)
- Test: `tests/test_readings_bot.py` (add a test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_readings_bot.py` (reuse existing fixtures/helpers in that file for building `query`, `account`, profile, and credits; mirror the existing happy-path test's setup). The new test patches the module's `enqueue_reading` to raise and asserts the credit is refunded and the failure message is shown:

```python
async def test_reading_enqueue_failure_refunds_credit(session, default_tenant, monkeypatch):
    # Arrange: account with a natal profile and >=1 credit, reading feature enabled.
    # (Build `query`, `account`, `i18n` exactly like the happy-path test in this file.)
    # ... reuse this file's existing setup helper ...

    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "quantuum.bot.handlers.readings.enqueue_reading",
        AsyncMock(side_effect=RuntimeError("redis down")),
    )

    # Act
    await on_reading_choice(query, account, i18n)  # use this file's actual call signature

    # Assert: failure message shown, not the "queued" message
    answers = [c.args[0] for c in query.message.answer.await_args_list]
    assert any("errors.queue_failed" in a for a in answers)
    # Assert: credit refunded
    from quantuum.db.models import AccountBalance
    bal = await session.get(AccountBalance, account.id)
    await session.refresh(bal)
    assert bal.package_credits == STARTING_CREDITS  # restored
```

NOTE for implementer: read the existing happy-path test in `tests/test_readings_bot.py` and copy its exact arrange/act shape (handler name, args, how credits and profile are seeded, how `i18n` stringifies keys). The assertions above are the contract; adapt the scaffolding to match the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_readings_bot.py -k enqueue_failure -v`
Expected: FAIL — credit not refunded / no `errors.queue_failed` message (current code calls `enqueue_reading` directly and lets the exception propagate).

- [ ] **Step 3: Implement**

In `src/quantuum/bot/handlers/readings.py`, add the import at the top with the other handler imports:

```python
from quantuum.bot.handlers._guard import enqueue_or_refund
```

Replace lines 95-97:

```python
    await enqueue_reading(reading.id, query.message.chat.id, request.id)
    await query.message.answer(await i18n("readings.queued"))
    await query.answer()
```

with:

```python
    if not await enqueue_or_refund(
        enqueue_reading(reading.id, query.message.chat.id, request.id),
        request_id=request.id,
    ):
        await query.message.answer(await i18n("errors.queue_failed"))
        await query.answer()
        return
    await query.message.answer(await i18n("readings.queued"))
    await query.answer()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_readings_bot.py -v`
Expected: PASS (new test + existing tests still green)

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/readings.py tests/test_readings_bot.py
git commit -m "fix(readings): refund credit when enqueue fails"
```

---

### Task 4: Wire `qa.py`

**Files:**
- Modify: `src/quantuum/bot/handlers/qa.py:149` (the `enqueue_qa` call)
- Test: `tests/test_qa_moderation_e2e.py` or the qa handler test file (add a test; pick the file that already drives the qa handler happy path)

- [ ] **Step 1: Write the failing test**

Find the existing qa-handler happy-path test (grep `enqueue_qa` in tests). Add a sibling test that patches `quantuum.bot.handlers.qa.enqueue_qa` to raise, runs the handler, and asserts: (a) the `errors.queue_failed` message is shown, (b) the credit is refunded (balance back to its pre-charge value), (c) the `Request` row's `charged_against == "none"`. Mirror the existing test's arrange/act exactly.

```python
async def test_qa_enqueue_failure_refunds_credit(session, default_tenant, monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "quantuum.bot.handlers.qa.enqueue_qa",
        AsyncMock(side_effect=RuntimeError("redis down")),
    )
    # ... reuse existing qa happy-path setup: account + profile + credits, message, i18n ...
    # await the qa handler entrypoint used by the happy-path test
    answers = [c.args[0] for c in message.answer.await_args_list]
    assert any("errors.queue_failed" in a for a in answers)
    from quantuum.db.models import AccountBalance
    bal = await session.get(AccountBalance, account.id)
    await session.refresh(bal)
    assert bal.package_credits == STARTING_CREDITS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest <qa test file> -k enqueue_failure -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `src/quantuum/bot/handlers/qa.py`, add the import:

```python
from quantuum.bot.handlers._guard import enqueue_or_refund
```

Replace lines 149-150:

```python
    await enqueue_qa(qa.id, message.chat.id, request.id)
    await message.answer(await i18n("qa.thinking"))
```

with:

```python
    if not await enqueue_or_refund(
        enqueue_qa(qa.id, message.chat.id, request.id),
        request_id=request.id,
    ):
        await message.answer(await i18n("errors.queue_failed"))
        return
    await message.answer(await i18n("qa.thinking"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest <qa test file> -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/qa.py <qa test file>
git commit -m "fix(qa): refund credit when enqueue fails"
```

---

### Task 5: Wire `transits.py`

**Files:**
- Modify: `src/quantuum/bot/handlers/transits.py:71` (the `enqueue_transit` call)
- Test: `tests/test_transits_bot.py` (add a test)

- [ ] **Step 1: Write the failing test**

Mirror the existing transits happy-path test in `tests/test_transits_bot.py`. Patch `quantuum.bot.handlers.transits.enqueue_transit` to raise; assert `errors.queue_failed` shown and credit refunded (`charged_against == "none"`, balance restored).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_transits_bot.py -k enqueue_failure -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `src/quantuum/bot/handlers/transits.py`, add the import:

```python
from quantuum.bot.handlers._guard import enqueue_or_refund
```

Replace lines 71-72:

```python
    await enqueue_transit(report.id, message.chat.id, request.id)
    await message.answer(await i18n("transit.thinking"))
```

with:

```python
    if not await enqueue_or_refund(
        enqueue_transit(report.id, message.chat.id, request.id),
        request_id=request.id,
    ):
        await message.answer(await i18n("errors.queue_failed"))
        return
    await message.answer(await i18n("transit.thinking"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_transits_bot.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/transits.py tests/test_transits_bot.py
git commit -m "fix(transits): refund credit when enqueue fails"
```

---

### Task 6: Wire `generate.py` (blueprint)

**Files:**
- Modify: `src/quantuum/bot/handlers/generate.py:63` (the `enqueue(...)` call inside `request_blueprint_for_account`) and the status handling in `run_generate` (~line 87)
- Test: `tests/test_generate_no_quota_offer.py` or the generate handler test file (add a test)

- [ ] **Step 1: Write the failing test**

`request_blueprint_for_account` returns `(status, blueprint_id)`. Add a test that passes an `enqueue` callable which raises, and asserts the returned status is `"queue_failed"` and the credit is refunded:

```python
async def test_blueprint_enqueue_failure_refunds_and_reports(session, default_tenant):
    from quantuum.bot.handlers.generate import request_blueprint_for_account
    # ... seed account with natal profile + credits (reuse this file's setup) ...

    async def boom(_bid, _chat, _req):
        raise RuntimeError("redis down")

    status, _ = await request_blueprint_for_account(
        session, account=account, chat_id=123, enqueue=boom, lang="en"
    )
    assert status == "queue_failed"
    from quantuum.db.models import AccountBalance
    bal = await session.get(AccountBalance, account.id)
    await session.refresh(bal)
    assert bal.package_credits == STARTING_CREDITS  # refunded
```

Also add/extend a `run_generate` test asserting that a `queue_failed` status produces the `errors.queue_failed` message (mirror how the existing `no_quota`/`no_profile` branches are tested).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest <generate test file> -k enqueue_failure -v`
Expected: FAIL — current code calls `await enqueue(...)` directly; the exception propagates instead of returning `"queue_failed"`.

- [ ] **Step 3: Implement**

In `src/quantuum/bot/handlers/generate.py`, add the import:

```python
from quantuum.bot.handlers._guard import enqueue_or_refund
```

Replace line 63:

```python
    await enqueue(blueprint.id, chat_id, request.id)
    return "queued", blueprint.id
```

with:

```python
    if not await enqueue_or_refund(
        enqueue(blueprint.id, chat_id, request.id), request_id=request.id
    ):
        return "queue_failed", None
    return "queued", blueprint.id
```

Then in `run_generate`, add a branch for the new status alongside the existing `no_profile`/`no_quota` handling (match the existing style):

```python
    if status == "queue_failed":
        await message.answer(await i18n("errors.queue_failed"))
        return
```

NOTE for implementer: read `run_generate` (`generate.py:67`+) and place the `queue_failed` branch consistently with the other status branches. Check for any OTHER caller of `request_blueprint_for_account` (grep) and ensure each handles `"queue_failed"` (e.g. surface `errors.queue_failed`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest <generate test file> -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/generate.py <generate test file>
git commit -m "fix(generate): refund credit and report when blueprint enqueue fails"
```

---

### Task 7: Wire `divination.py`

**Files:**
- Modify: `src/quantuum/bot/handlers/divination.py:215` (the `enqueue_reading` call in `_perform_draw_and_enqueue`)
- Test: `tests/test_divination_handler.py` (add a test)

- [ ] **Step 1: Write the failing test**

`tests/test_divination_handler.py` already patches `quantuum.bot.handlers.divination.enqueue_reading` (see its existing tests). Add a test that patches it to raise and asserts: `errors.queue_failed` message shown, credit refunded, state cleared. Reuse the existing tarot/iching happy-path setup in this file.

```python
async def test_divination_enqueue_failure_refunds_credit(session, default_tenant, monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "quantuum.bot.handlers.divination.enqueue_reading",
        AsyncMock(side_effect=RuntimeError("redis down")),
    )
    # ... reuse this file's happy-path setup (profile, credits, state with kind=tarot, message) ...
    await _perform_draw_and_enqueue(...)  # use the file's actual call shape
    answers = [c.args[0] for c in message_for_reply.answer.await_args_list]
    assert any("errors.queue_failed" in a for a in answers)
    from quantuum.db.models import AccountBalance
    bal = await session.get(AccountBalance, account.id)
    await session.refresh(bal)
    assert bal.package_credits == STARTING_CREDITS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_divination_handler.py -k enqueue_failure -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `src/quantuum/bot/handlers/divination.py`, add the import:

```python
from quantuum.bot.handlers._guard import enqueue_or_refund
```

Replace lines 215-217:

```python
    await enqueue_reading(reading.id, chat_id, request.id)
    await message_for_reply.answer(await i18n("readings.queued"))
    await state.clear()
```

with:

```python
    if not await enqueue_or_refund(
        enqueue_reading(reading.id, chat_id, request.id), request_id=request.id
    ):
        await message_for_reply.answer(await i18n("errors.queue_failed"))
        await state.clear()
        return
    await message_for_reply.answer(await i18n("readings.queued"))
    await state.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_divination_handler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/bot/handlers/divination.py tests/test_divination_handler.py
git commit -m "fix(divination): refund credit when enqueue fails"
```

---

### Task 8: Stage regression — full suite

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: all green (the prior stage baseline was 2007 passed + the new tests from this plan). No regressions.

- [ ] **Step 2: If anything fails**

Investigate and fix. Do NOT weaken assertions to make tests pass. A real regression here means a handler now refunds when it shouldn't, or a test fixture seeds credits in a counter-only way that diverges from the ledger (seed via `grant_credits`/`adjust_package_credits`).

- [ ] **Step 3: No commit needed** unless a fix was made (then commit it with a descriptive message).

---

## Notes / scope

- This plan covers ONLY the enqueue boundary (the documented A-handlers gap). The narrower window where `create_request`/`create_<domain>` itself fails *after* `consume_quota` committed is far rarer (it implies the DB is failing mid-transaction, which would also have failed `consume_quota`) and is out of scope for this plan.
- `refund_quota` is idempotent (it sets `charged_against="none"` and short-circuits on a second call) and locks the `Request` row — established in Workstream A-domain. The guard relies on that.
- After this plan, update `docs/superpowers/specs/...` progress notes / the `audit-fix-sweep-progress` memory: A-handlers DONE.
