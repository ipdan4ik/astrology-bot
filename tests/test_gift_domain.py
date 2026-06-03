from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    AccountBalance,
    AuditLog,
    StartToken,
    Tenant,
    TenantConfig,
)
from quantuum.domain.gifts import (
    DEFAULT_EXPIRY_DAYS,
    GIFT_EXPIRY_CONFIG_KEY,
    GIFT_KIND,
    MAX_EXPIRY_DAYS,
    MAX_GIFT_AMOUNT,
    MIN_EXPIRY_DAYS,
    InsufficientCreditsError,
    create_gift,
    get_expiry_days,
    list_recent_gifts,
    reset_expiry_days,
    set_expiry_days,
    sweep_expired_gifts,
)


async def _tenant(session: AsyncSession) -> Tenant:
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    return t


async def _account_with_credits(session, tenant_id, tg, credits):
    from quantuum.domain.accounts import adjust_package_credits

    acc = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=tg
    )
    bal = await session.get(AccountBalance, acc.id)
    current = bal.package_credits if bal is not None else 0
    delta = credits - current
    if delta != 0:
        await adjust_package_credits(session, acc.id, delta)
    await session.flush()
    return acc


async def test_create_gift_happy_path(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 50)

    token = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=15
    )

    assert token.kind == GIFT_KIND
    assert token.owner_account_id == sender.id
    assert token.tenant_id == t.id
    assert token.payload == {"amount": 15}
    assert token.max_uses == 1
    assert token.status == "active"
    assert token.expires_at is not None and token.expires_at > utcnow()

    bal = await session.get(AccountBalance, sender.id)
    assert bal.package_credits == 35

    audit = (
        await session.execute(select(AuditLog).where(AuditLog.action == "gift.created"))
    ).scalars().one()
    assert audit.payload_jsonb["amount"] == 15
    assert audit.payload_jsonb["code"] == token.code


async def test_create_gift_uses_tenant_expiry(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 50)
    await set_expiry_days(
        session, tenant_id=t.id, days=7, by_account_id=sender.id
    )
    await session.flush()

    token = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=5
    )
    delta = (token.expires_at - utcnow()).total_seconds()
    assert 7 * 86400 - 60 < delta < 7 * 86400 + 60


@pytest.mark.parametrize("amount", [0, -1, MAX_GIFT_AMOUNT + 1, 5000])
async def test_create_gift_invalid_amount_raises(session: AsyncSession, amount):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 5000)
    with pytest.raises(ValueError):
        await create_gift(
            session, sender_account_id=sender.id, tenant_id=t.id, amount=amount
        )


async def test_create_gift_insufficient_credits(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 4)
    with pytest.raises(InsufficientCreditsError):
        await create_gift(
            session, sender_account_id=sender.id, tenant_id=t.id, amount=5
        )
    bal = await session.get(AccountBalance, sender.id)
    assert bal.package_credits == 4
    rows = (await session.execute(select(StartToken))).scalars().all()
    assert rows == []


async def test_list_recent_gifts_status_derivation(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 200)

    active = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=5
    )
    claimed = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=7
    )
    claimed.status = "claimed"
    refunded = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=9
    )
    refunded.status = "refunded"
    await session.flush()

    rows = await list_recent_gifts(
        session, sender_account_id=sender.id, limit=10
    )
    by_code = {r.code: r for r in rows}
    assert by_code[active.code].status == "active"
    assert by_code[claimed.code].status == "claimed"
    assert by_code[refunded.code].status == "refunded"


async def test_list_recent_gifts_orders_desc_and_limits(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 200)
    codes = []
    for _ in range(12):
        tok = await create_gift(
            session, sender_account_id=sender.id, tenant_id=t.id, amount=1
        )
        codes.append(tok.code)
    rows = await list_recent_gifts(
        session, sender_account_id=sender.id, limit=10
    )
    assert len(rows) == 10
    assert rows[0].code == codes[-1]


async def test_sweep_refunds_expired_unclaimed(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    tok1 = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=10
    )
    tok2 = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=15
    )
    tok1.expires_at = utcnow() - timedelta(seconds=1)
    await session.flush()

    bal_before = (await session.get(AccountBalance, sender.id)).package_credits
    n = await sweep_expired_gifts(session, sender_account_id=sender.id)
    assert n == 1

    bal_after = (await session.get(AccountBalance, sender.id)).package_credits
    assert bal_after == bal_before + 10

    reloaded1 = await session.get(StartToken, tok1.code)
    reloaded2 = await session.get(StartToken, tok2.code)
    assert reloaded1.status == "refunded"
    assert reloaded2.status == "active"

    audit = (
        await session.execute(select(AuditLog).where(AuditLog.action == "gift.refunded"))
    ).scalars().all()
    assert len(audit) == 1
    assert audit[0].payload_jsonb["reason"] == "expired"


async def test_sweep_skips_claimed_and_already_refunded(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    claimed = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=10
    )
    claimed.status = "claimed"
    claimed.expires_at = utcnow() - timedelta(days=1)
    refunded = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=10
    )
    refunded.status = "refunded"
    refunded.expires_at = utcnow() - timedelta(days=1)
    await session.flush()

    bal_before = (await session.get(AccountBalance, sender.id)).package_credits
    n = await sweep_expired_gifts(session, sender_account_id=sender.id)
    assert n == 0
    bal_after = (await session.get(AccountBalance, sender.id)).package_credits
    assert bal_after == bal_before


async def test_sweep_idempotent(session: AsyncSession):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    tok = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=10
    )
    tok.expires_at = utcnow() - timedelta(seconds=1)
    await session.flush()

    n1 = await sweep_expired_gifts(session, sender_account_id=sender.id)
    n2 = await sweep_expired_gifts(session, sender_account_id=sender.id)
    assert n1 == 1
    assert n2 == 0


async def test_sweep_refund_is_ledger_backed(session, default_tenant):
    from datetime import timedelta
    from sqlmodel import select

    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.common.datetime import utcnow
    from quantuum.db.models import AccountPackage, StartToken
    from quantuum.domain.gifts import sweep_expired_gifts

    sender = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="giftsender"
    )
    token = StartToken(
        code="expgift1", kind="gift", tenant_id=default_tenant.id,
        owner_account_id=sender.id, payload={"amount": 3}, status="active",
        expires_at=utcnow() - timedelta(days=1),
    )
    session.add(token)
    await session.commit()

    refunded = await sweep_expired_gifts(session, sender_account_id=sender.id)
    await session.commit()

    assert refunded == 1
    rows = (
        await session.execute(
            select(AccountPackage).where(AccountPackage.account_id == sender.id)
        )
    ).scalars().all()
    assert any(r.source == "gift" and r.requests_remaining == 3 for r in rows)


async def test_expiry_days_get_default(session: AsyncSession):
    t = await _tenant(session)
    assert await get_expiry_days(session, tenant_id=t.id) == DEFAULT_EXPIRY_DAYS


async def test_expiry_days_set_and_get(session: AsyncSession):
    t = await _tenant(session)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=t.id, tg_user_id="1001"
    )
    await set_expiry_days(session, tenant_id=t.id, days=14, by_account_id=acc.id)
    await session.flush()
    assert await get_expiry_days(session, tenant_id=t.id) == 14


@pytest.mark.parametrize("days", [0, -1, MAX_EXPIRY_DAYS + 1, MIN_EXPIRY_DAYS - 1])
async def test_expiry_days_set_rejects_out_of_range(session: AsyncSession, days):
    t = await _tenant(session)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=t.id, tg_user_id="1001"
    )
    with pytest.raises(ValueError):
        await set_expiry_days(
            session, tenant_id=t.id, days=days, by_account_id=acc.id
        )


async def test_create_gift_debit_survives_recompute(session, default_tenant):
    """Funding a gift must drain the ledger, not just the counter, so a later
    recompute does not refund the sender (credit duplication)."""
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import AccountBalance
    from quantuum.domain.billing import recompute_account_balance
    from quantuum.domain.gifts import create_gift

    sender = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="giftcreator"
    )
    start = (await session.get(AccountBalance, sender.id)).package_credits  # welcome credits

    await create_gift(session, sender_account_id=sender.id, tenant_id=default_tenant.id, amount=4)
    await session.commit()
    after_create = (await session.get(AccountBalance, sender.id)).package_credits
    assert after_create == start - 4

    await recompute_account_balance(session, sender.id)
    after_recompute = (await session.get(AccountBalance, sender.id)).package_credits
    assert after_recompute == start - 4  # NOT snapped back up


async def test_expiry_days_reset_removes_override(session: AsyncSession):
    t = await _tenant(session)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=t.id, tg_user_id="1001"
    )
    await set_expiry_days(session, tenant_id=t.id, days=90, by_account_id=acc.id)
    await session.flush()
    await reset_expiry_days(session, tenant_id=t.id, by_account_id=acc.id)
    await session.flush()
    row = await session.get(TenantConfig, (t.id, GIFT_EXPIRY_CONFIG_KEY))
    assert row is None
    assert await get_expiry_days(session, tenant_id=t.id) == DEFAULT_EXPIRY_DAYS
