# API Security Hardening (Workstream E) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the HTTP API: drop duplicate/replayed webhook updates and verify Telegram's secret-token header, rotate refresh tokens with reuse-detection, and bound all user-supplied numeric inputs and list sizes.

**Architecture:** Webhooks arrive at `POST /tg/{secret_path}` (`api/routes/webhook.py`), resolve a `TenantBot`, and `push_update` to Redis (a separate consumer feeds the dispatcher). We add (1) a Redis `SETNX`-based dedup on `(bot_telegram_id, update_id)`, (2) a per-bot `webhook_secret_token` column whose presence gates verification of the `X-Telegram-Bot-Api-Secret-Token` header (backward-compatible: legacy NULL bots skip it). Refresh tokens are DB-backed (`AccountRefreshToken`); we make `/auth/refresh` rotate (revoke-old + issue-new) and revoke the whole chain on reuse of an already-consumed token. Input validation is Pydantic `Field(ge=, le=)` bounds plus `Query` pagination caps.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async, Redis (`redis.asyncio` via `quantuum.redis_client.get_redis`), Alembic, pytest + httpx `AsyncClient`/`ASGITransport`. Current alembic head: `a1c2e3f405d6`.

**Test command:** `uv run pytest <path> -v`. asyncio auto mode (no decorator). HTTP tests use the `client`/`auth_client` fixtures (httpx `AsyncClient` + `ASGITransport`, see `tests/conftest.py` / existing API tests). For each task READ the named existing test file first and mirror its client/token fixtures. Do NOT weaken assertions.

---

### Task 1: Webhook idempotency (drop duplicate update_id)

**Files:**
- Modify: `src/quantuum/redis_client.py` (add a dedup helper)
- Modify: `src/quantuum/api/routes/webhook.py` (call it before enqueueing)
- Test: `tests/test_api_webhook.py`

- [ ] **Step 1: Write the failing test**

Mirror `tests/test_api_webhook.py`'s setup (it builds a TenantBot with an active tenant and posts to `/tg/{secret_path}`). Post the SAME update twice and assert the Redis queue received it once.

```python
async def test_webhook_dedupes_repeated_update(client, session, default_tenant):
    from quantuum.db.models import TenantBot
    from quantuum.redis_client import get_redis, UPDATE_QUEUE_KEY
    bot = TenantBot(
        tenant_id=default_tenant.id, bot_telegram_id=700001, bot_token_enc=b"x",
        transport="webhook", webhook_secret_path="wh-dedupe", status="active",
    )
    session.add(bot)
    await session.commit()

    payload = {"update_id": 555, "message": {"text": "hi"}}
    r1 = await client.post("/tg/wh-dedupe", json=payload)
    r2 = await client.post("/tg/wh-dedupe", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200

    qlen = await get_redis().llen(UPDATE_QUEUE_KEY)
    assert qlen == 1  # second (duplicate) update was dropped
```

NOTE: confirm the webhook route prefix — the Explore map shows `POST /tg/{secret_path}`; if the router has a prefix, adjust the URL. `UPDATE_QUEUE_KEY` is exported from `quantuum.redis_client`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_webhook.py -k dedupes_repeated_update -v`
Expected: FAIL — `qlen == 2` (both enqueued).

- [ ] **Step 3: Implement the dedup helper**

In `src/quantuum/redis_client.py`, add:

```python
DEDUP_TTL_SECONDS = 3600


async def mark_update_seen(bot_id: int, update_id: int) -> bool:
    """Return True if this (bot_id, update_id) is NEW (claim it), False if already seen.

    Uses SETNX with a TTL so replayed/duplicate Telegram deliveries are dropped.
    A missing update_id (None) is always treated as new (cannot dedup).
    """
    if update_id is None:
        return True
    key = f"tg:dedup:{bot_id}:{update_id}"
    created = await get_redis().set(key, "1", nx=True, ex=DEDUP_TTL_SECONDS)
    return bool(created)
```

- [ ] **Step 4: Call it in the webhook route**

In `src/quantuum/api/routes/webhook.py`, after resolving `tenant_bot` and reading the update, dedup before enqueueing:

```python
    update = await request.json()
    if not await mark_update_seen(tenant_bot.bot_telegram_id, update.get("update_id")):
        return {"ok": True, "duplicate": True}
    await push_update(tenant_bot.bot_telegram_id, update)
    return {"ok": True}
```

Add the import: `from quantuum.redis_client import mark_update_seen, push_update` (merge with the existing `push_update` import).

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api_webhook.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/redis_client.py src/quantuum/api/routes/webhook.py tests/test_api_webhook.py
git commit -m "fix(webhook): drop duplicate update_id via Redis SETNX"
```

---

### Task 2: Webhook secret-token header verification (gated)

**Files:**
- Modify: `src/quantuum/db/models.py` (TenantBot — add `webhook_secret_token`)
- Create: `alembic/versions/<new_id>_tenant_bot_secret_token.py`
- Modify: `src/quantuum/domain/provisioning.py` (generate token at provisioning)
- Modify: `src/quantuum/api/routes/webhook.py` (verify header when token set)
- Test: `tests/test_api_webhook.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_webhook_rejects_wrong_secret_token(client, session, default_tenant):
    from quantuum.db.models import TenantBot
    bot = TenantBot(
        tenant_id=default_tenant.id, bot_telegram_id=700002, bot_token_enc=b"x",
        transport="webhook", webhook_secret_path="wh-sec",
        webhook_secret_token="expected-token", status="active",
    )
    session.add(bot); await session.commit()
    # missing header -> 403
    r = await client.post("/tg/wh-sec", json={"update_id": 1})
    assert r.status_code == 403
    # wrong header -> 403
    r = await client.post("/tg/wh-sec", json={"update_id": 2},
                          headers={"X-Telegram-Bot-Api-Secret-Token": "nope"})
    assert r.status_code == 403
    # correct header -> 200
    r = await client.post("/tg/wh-sec", json={"update_id": 3},
                          headers={"X-Telegram-Bot-Api-Secret-Token": "expected-token"})
    assert r.status_code == 200


async def test_webhook_legacy_null_token_skips_header_check(client, session, default_tenant):
    from quantuum.db.models import TenantBot
    bot = TenantBot(
        tenant_id=default_tenant.id, bot_telegram_id=700003, bot_token_enc=b"x",
        transport="webhook", webhook_secret_path="wh-legacy",
        webhook_secret_token=None, status="active",
    )
    session.add(bot); await session.commit()
    r = await client.post("/tg/wh-legacy", json={"update_id": 9})
    assert r.status_code == 200  # NULL token => no header required (backward compat)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_webhook.py -k "wrong_secret_token or legacy_null_token" -v`
Expected: FAIL — `webhook_secret_token` column doesn't exist yet / no header check.

- [ ] **Step 3: Add the column to the model**

In `src/quantuum/db/models.py`, in `TenantBot`, add (near `webhook_secret_path`):

```python
    webhook_secret_token: str | None = Field(default=None)
```

- [ ] **Step 4: Write the migration**

Confirm an unused revision id (`grep -rn "^revision" alembic/versions/`). Use e.g. `b2d3f4a5c607` (VERIFY unused). Create `alembic/versions/b2d3f4a5c607_tenant_bot_secret_token.py`:

```python
"""tenant_bots.webhook_secret_token

Revision ID: b2d3f4a5c607
Revises: a1c2e3f405d6
Create Date: 2026-06-03 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2d3f4a5c607"
down_revision: Union[str, Sequence[str], None] = "a1c2e3f405d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenant_bots",
        sa.Column("webhook_secret_token", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_bots", "webhook_secret_token")
```

- [ ] **Step 5: Generate the token at provisioning**

In `src/quantuum/domain/provisioning.py`, in `create_tenant_from_onboarding` where the new `TenantBot(...)` is built, add `webhook_secret_token=url_safe_token(16),` (`url_safe_token` is already imported).

- [ ] **Step 6: Verify the header in the route**

In `src/quantuum/api/routes/webhook.py`, read the header and verify it when the bot has a token. Add `Header` to the FastAPI imports and a parameter:

```python
from fastapi import APIRouter, Depends, Header, HTTPException, Request
```

```python
@router.post("/tg/{secret_path}")
async def telegram_webhook(
    secret_path: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant_bot = await get_tenant_bot_by_webhook_secret(session, secret_path)
    if tenant_bot is None or tenant_bot.bot_telegram_id is None:
        raise HTTPException(status_code=404, detail="not found")
    if (
        tenant_bot.webhook_secret_token is not None
        and x_telegram_bot_api_secret_token != tenant_bot.webhook_secret_token
    ):
        raise HTTPException(status_code=403, detail="bad secret token")
    update = await request.json()
    if not await mark_update_seen(tenant_bot.bot_telegram_id, update.get("update_id")):
        return {"ok": True, "duplicate": True}
    await push_update(tenant_bot.bot_telegram_id, update)
    return {"ok": True}
```

- [ ] **Step 7: Run tests + confirm single head**

Run: `uv run pytest tests/test_api_webhook.py -v` → PASS
Run: `uv run alembic heads` → single head `b2d3f4a5c607`.

- [ ] **Step 8: Commit**

```bash
git add src/quantuum/db/models.py alembic/versions/b2d3f4a5c607_tenant_bot_secret_token.py src/quantuum/domain/provisioning.py src/quantuum/api/routes/webhook.py tests/test_api_webhook.py
git commit -m "feat(webhook): verify X-Telegram-Bot-Api-Secret-Token when configured"
```

---

### Task 3: Refresh-token rotation with reuse-detection

**Files:**
- Modify: `src/quantuum/auth/jwt_tokens.py` (add `rotate_refresh_token` + chain-revoke)
- Modify: `src/quantuum/api/routes/auth.py` (`/refresh` returns the rotated token)
- Test: `tests/test_jwt_tokens.py` and/or `tests/test_api_auth.py`

- [ ] **Step 1: Write the failing tests**

Domain test in `tests/test_jwt_tokens.py` (mirror its setup for an account + `issue_refresh_token`):

```python
async def test_rotate_refresh_token_rotates_and_detects_reuse(session, default_tenant):
    from quantuum.auth import jwt_tokens
    from quantuum.common.exceptions import NotFoundError  # adapt to real import
    import pytest
    from quantuum.auth.identity import find_or_create_account_by_tg

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="rot1")
    r1 = await jwt_tokens.issue_refresh_token(session, acc.id)

    # rotate: returns a new token; r1 becomes invalid
    account, r2 = await jwt_tokens.rotate_refresh_token(session, r1)
    assert account.id == acc.id
    assert r2 != r1

    with pytest.raises(NotFoundError):
        await jwt_tokens.rotate_refresh_token(session, r1)  # reuse of consumed token

    # reuse detection revokes the whole chain: r2 is now also dead
    with pytest.raises(NotFoundError):
        await jwt_tokens.rotate_refresh_token(session, r2)
```

API test in `tests/test_api_auth.py` (mirror its refresh-flow test): POST `/auth/refresh` with a valid refresh token returns a DIFFERENT `refresh_token`, and re-POSTing the old token returns 401.

NOTE: confirm the exact import path of `NotFoundError` (the Explore map shows `consume_refresh_token` raises `NotFoundError`; grep its import in `jwt_tokens.py`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_jwt_tokens.py -k rotates_and_detects_reuse -v`
Expected: FAIL — `rotate_refresh_token` doesn't exist.

- [ ] **Step 3: Implement rotation**

In `src/quantuum/auth/jwt_tokens.py`, add `update` to the sqlalchemy imports if needed, then add:

```python
async def _revoke_all_for_account(session, account_id: int) -> None:
    from sqlalchemy import update
    await session.execute(
        update(AccountRefreshToken)
        .where(
            AccountRefreshToken.account_id == account_id,
            AccountRefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )
    await session.commit()


async def rotate_refresh_token(session, token: str) -> tuple[Account, str]:
    """Validate a refresh token, revoke it, and issue a fresh one.

    Reuse of an already-consumed (revoked) token revokes the entire chain for
    that account and raises — a presented-but-revoked token signals theft.
    """
    result = await session.execute(
        select(AccountRefreshToken).where(AccountRefreshToken.token_hash == _hash(token))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError("refresh token invalid")
    if row.revoked_at is not None:
        await _revoke_all_for_account(session, row.account_id)
        raise NotFoundError("refresh token reuse detected")
    if row.expires_at < utcnow():
        raise NotFoundError("refresh token expired")
    account = await session.get(Account, row.account_id)
    if account is None:
        raise NotFoundError("account not found")
    row.revoked_at = utcnow()
    session.add(row)
    new_token = await issue_refresh_token(session, account.id)  # commits both rows
    return account, new_token
```

- [ ] **Step 4: Switch the route to rotate**

In `src/quantuum/api/routes/auth.py`, change `/refresh`:

```python
@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    try:
        account, new_refresh = await jwt_tokens.rotate_refresh_token(session, body.refresh_token)
    except NotFoundError as exc:
        raise HTTPException(status_code=401, detail="invalid refresh token") from exc
    access = jwt_tokens.issue_access_token(account.id, account.tenant_id, account.is_superadmin)
    return TokenOut(access_token=access, refresh_token=new_refresh)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_jwt_tokens.py tests/test_api_auth.py -v`
Expected: PASS. If an existing test asserted the refresh endpoint echoes the same `refresh_token`, update it to assert it differs (intended rotation behavior — not a weakening).

- [ ] **Step 6: Commit**

```bash
git add src/quantuum/auth/jwt_tokens.py src/quantuum/api/routes/auth.py tests/test_jwt_tokens.py tests/test_api_auth.py
git commit -m "fix(auth): rotate refresh token and revoke chain on reuse"
```

---

### Task 4: Bound numeric inputs (Pydantic Field ge/le)

**Files:**
- Modify: `src/quantuum/api/schemas.py` — `NatalProfileIn`, `BalancePatchIn`, `SubscriptionPlanCreateIn`, `PackagePlanCreateIn`, `InviteCreateIn`, and any matching `*PatchIn`/`*UpdateIn` plan-edit models (grep `class .*Plan.*In` and `class BalancePatch` in schemas.py)
- Test: `tests/test_api_natal_profile.py`, `tests/test_api_tenant_plans_accounts.py`, `tests/test_api_admin_platform.py`

- [ ] **Step 1: Write the failing tests**

Add 422-rejection tests. Examples (adapt client/token fixtures + routes to each file):

```python
# natal profile: latitude out of range -> 422
async def test_natal_profile_rejects_out_of_range_latitude(auth_client, ...):
    resp = await auth_client.put("/v1/me/natal-profile", json={
        "full_name": "X", "birth_date": "1990-01-01", "birth_time": "12:00:00",
        "birth_place": "Y", "latitude": 200, "longitude": 0, "timezone": "UTC",
    })
    assert resp.status_code == 422

# balance: negative credits -> 422
async def test_balance_rejects_negative_credits(owner_client, ...):
    resp = await owner_client.patch(f"/{tenant_id}/accounts/{account_id}/balance",
                                    json={"package_credits": -5})
    assert resp.status_code == 422

# plan: negative price -> 422 ; invite: max_uses 0 -> 422
```

Confirm the exact field constructors and routes against each test file's existing happy-path tests.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_natal_profile.py tests/test_api_tenant_plans_accounts.py tests/test_api_admin_platform.py -k "rejects" -v`
Expected: FAIL — currently accepted (200/201).

- [ ] **Step 3: Implement bounds**

Add `from pydantic import Field` (if not already imported) in `schemas.py`, then add bounds:

- `NatalProfileIn`:
  ```python
      latitude: Decimal = Field(ge=-90, le=90)
      longitude: Decimal = Field(ge=-180, le=180)
  ```
- `BalancePatchIn`:
  ```python
      package_credits: int | None = Field(default=None, ge=0, le=1_000_000)
  ```
- `SubscriptionPlanCreateIn`:
  ```python
      period_days: int = Field(ge=1, le=3650)
      price_cents: int = Field(ge=0, le=100_000_000)
  ```
- `PackagePlanCreateIn`:
  ```python
      request_count: int = Field(ge=1, le=1_000_000)
      price_cents: int = Field(ge=0, le=100_000_000)
      expires_after_days: int | None = Field(default=None, ge=1, le=3650)
  ```
- `InviteCreateIn`:
  ```python
      max_uses: int = Field(default=1, ge=1, le=10_000)
  ```
- Any plan `*PatchIn`/`*UpdateIn` with optional `price_cents`/`period_days`/`request_count`: add the same bounds with `default=None`.

NOTE: keep existing defaults where present (e.g. `max_uses` default 1). Use `Field(default=..., ge=, le=)` form for fields that had a default.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_natal_profile.py tests/test_api_tenant_plans_accounts.py tests/test_api_admin_platform.py -v`
Expected: PASS (happy-path tests with in-range values still pass).

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/api/schemas.py tests/test_api_natal_profile.py tests/test_api_tenant_plans_accounts.py tests/test_api_admin_platform.py
git commit -m "fix(api): bound numeric inputs (lat/long, credits, pricing, max_uses)"
```

---

### Task 5: Pagination caps on /me list endpoints

**Files:**
- Modify: `src/quantuum/api/routes/me.py` — bound the existing `limit` params on `/qa` (:268), `/transits` (:352), `/daily/horoscopes` (:419); add bounded `limit`/`offset` to the currently-unbounded `/blueprints` (:151), `/subscriptions` (:475), `/payments` (:494).
- Test: `tests/test_api_me.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_qa_list_rejects_oversized_limit(auth_client):
    resp = await auth_client.get("/v1/me/qa?limit=10000")
    assert resp.status_code == 422

async def test_payments_list_accepts_limit(auth_client):
    resp = await auth_client.get("/v1/me/payments?limit=5")
    assert resp.status_code == 200
```

NOTE: confirm route prefixes from the file (the Explore map shows `/v1/me/...`). The first test fails today because `/qa` `limit` is an unbounded `int`; the second fails because `/payments` currently takes no `limit` param (FastAPI ignores unknown query params, so it'd 200 already — instead assert the limit is HONORED: create 3 payments, request `limit=2`, assert `len(body) == 2`). Adapt the second test to assert the cap is actually applied.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_me.py -k "oversized_limit or payments_list" -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add `from fastapi import Query` to `me.py` imports (if not present). For the three bounded endpoints, change `limit: int = 50` → `limit: int = Query(default=50, ge=1, le=200)` (use each endpoint's existing default: qa=50, transits=50, daily=30) and `offset: int = 0` → `offset: int = Query(default=0, ge=0)`.

For `/blueprints`, `/subscriptions`, `/payments`, add the params and apply them to the query:

```python
async def list_payments(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[PaymentOut]:
    ...
    # add .order_by(<stable col>.desc()).limit(limit).offset(offset) to the select
```

NOTE for implementer: READ each of the three unbounded handlers and add `.limit(limit).offset(offset)` to their existing `select(...)`, preserving any existing `order_by`. If a handler has no `order_by`, add a stable one (e.g. `.order_by(<Model>.id.desc())`) so pagination is deterministic.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_me.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantuum/api/routes/me.py tests/test_api_me.py
git commit -m "fix(api): bound and paginate /me list endpoints"
```

---

### Task 6: Stage regression — full suite

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: all green (prior baseline 2046 passed + this plan's new tests). Confirm `uv run alembic heads` is a single head.

- [ ] **Step 2: If anything fails**

Likely: (a) an existing auth test asserting the refresh endpoint echoes the same token — update to assert rotation (intended). (b) an existing webhook test that posts without the now-required header — only affected if its fixture set a `webhook_secret_token`; legacy NULL bots are unaffected, so most existing tests pass unchanged. (c) an existing input test that sent an out-of-range value expecting 200 — verify intent before changing. Do NOT weaken security assertions.

- [ ] **Step 3: Commit** any test updates with a clear message.

---

## Notes / scope

- **Webhook secret-token is gated**: enforced only when `TenantBot.webhook_secret_token` is set. New bots get one at provisioning; the external `setWebhook` caller must pass the same value to Telegram for the header to arrive. Legacy/NULL bots skip the check (no breakage). The actual `setWebhook` registration is outside this codebase (the runner only manages in-process Bot objects and a Redis-fed consumer), so wiring the token into a live `setWebhook` call is left to the operator/registration path; this task installs the verification + storage.
- Out of scope (per design spec follow-ups): JWT `iss`/`aud` binding, magic-link rate limiting / HTTPS enforcement.
- After this plan, update the `audit-fix-sweep-progress` memory: E DONE. Spec order next: F → G.
