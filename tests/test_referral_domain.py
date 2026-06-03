import pytest
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    AccountBalance,
    AuditLog,
    Payment,
    StartToken,
    StartTokenUse,
    Tenant,
)
from quantuum.domain.referrals import (
    DEFAULT_REWARD_CREDITS,
    MAX_REWARD_CREDITS,
    REFERRAL_CODE_LENGTH,
    REFERRAL_KIND,
    generate_referral_code,
    get_referral_stats,
    get_reward_credits,
    maybe_payout_referral,
    reset_reward_credits,
    set_reward_credits,
)


def test_models_importable():
    assert StartToken.__tablename__ == "start_tokens"
    assert StartTokenUse.__tablename__ == "start_token_uses"


def test_start_token_defaults():
    token = StartToken(code="ABC23K7Q", kind="referral", tenant_id=1)
    assert token.status == "active"
    assert token.used_count == 0
    assert token.payload == {}
    assert token.max_uses is None
    assert token.owner_account_id is None
    assert token.expires_at is None


def test_start_token_use_defaults():
    use = StartTokenUse(token_code="ABC23K7Q", account_id=42)
    assert use.claimed_at is None


async def _make_tenant(session) -> Tenant:
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    return t


async def _make_account(session, tenant_id: int, tg_id: int) -> int:
    acct = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=str(tg_id)
    )
    return acct.id


async def _zero_balance(session, account_id: int) -> None:
    """Reset package_credits to 0 on the account's existing AccountBalance row."""
    bal = await session.get(AccountBalance, account_id)
    if bal is None:
        session.add(AccountBalance(account_id=account_id, package_credits=0))
    else:
        bal.package_credits = 0
        session.add(bal)
    await session.flush()


async def _mark_paid(session, *, tenant_id: int, account_id: int) -> Payment:
    p = Payment(
        tenant_id=tenant_id,
        account_id=account_id,
        amount_cents=100,
        status="paid",
        paid_at=utcnow(),
    )
    session.add(p)
    await session.flush()
    return p


async def test_generate_referral_code_creates_token(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t.id)

    assert isinstance(code, str)
    assert len(code) == REFERRAL_CODE_LENGTH
    row = await session.get(StartToken, code)
    assert row is not None
    assert row.kind == REFERRAL_KIND
    assert row.owner_account_id == aid
    assert row.tenant_id == t.id
    assert row.max_uses is None
    assert row.expires_at is None
    assert row.status == "active"


async def test_generate_referral_code_idempotent(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 1001)
    code1 = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    code2 = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    assert code1 == code2


async def test_generate_referral_code_writes_audit(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 1001)
    await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    rows = (
        (await session.execute(select(AuditLog).where(AuditLog.action == "referral.code_created")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].tenant_id == t.id
    assert rows[0].actor_account_id == aid


async def test_get_referral_stats_zero(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 1001)
    stats = await get_referral_stats(session, account_id=aid)
    assert stats == {"code": None, "claimed": 0, "pending": 0}


async def test_get_referral_stats_counts(session: AsyncSession):
    t = await _make_tenant(session)
    referrer = await _make_account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)

    ref1 = await _make_account(session, t.id, 2001)
    ref2 = await _make_account(session, t.id, 2002)
    session.add(StartTokenUse(token_code=code, account_id=ref1, claimed_at=utcnow()))
    session.add(StartTokenUse(token_code=code, account_id=ref2))
    await session.flush()

    stats = await get_referral_stats(session, account_id=referrer)
    assert stats == {"code": code, "claimed": 1, "pending": 1}


async def test_get_reward_credits_default(session: AsyncSession):
    t = await _make_tenant(session)
    assert await get_reward_credits(session, tenant_id=t.id) == DEFAULT_REWARD_CREDITS


async def test_set_reward_credits_upsert(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 9001)
    await set_reward_credits(session, tenant_id=t.id, value=25, by_account_id=aid)
    assert await get_reward_credits(session, tenant_id=t.id) == 25
    await set_reward_credits(session, tenant_id=t.id, value=50, by_account_id=aid)
    assert await get_reward_credits(session, tenant_id=t.id) == 50


async def test_set_reward_credits_validates_range(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 9001)
    with pytest.raises(ValueError):
        await set_reward_credits(session, tenant_id=t.id, value=-1, by_account_id=aid)
    with pytest.raises(ValueError):
        await set_reward_credits(
            session, tenant_id=t.id, value=MAX_REWARD_CREDITS + 1, by_account_id=aid
        )


async def test_reset_reward_credits_idempotent(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 9001)
    await set_reward_credits(session, tenant_id=t.id, value=25, by_account_id=aid)
    await reset_reward_credits(session, tenant_id=t.id, by_account_id=aid)
    await reset_reward_credits(session, tenant_id=t.id, by_account_id=aid)
    assert await get_reward_credits(session, tenant_id=t.id) == DEFAULT_REWARD_CREDITS


async def test_maybe_payout_referral_no_use_row(session: AsyncSession):
    t = await _make_tenant(session)
    aid = await _make_account(session, t.id, 5001)
    fired = await maybe_payout_referral(session, referee_account_id=aid)
    assert fired is False


async def test_maybe_payout_referral_no_payment(session: AsyncSession):
    t = await _make_tenant(session)
    referrer = await _make_account(session, t.id, 1001)
    referee = await _make_account(session, t.id, 2001)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)
    session.add(StartTokenUse(token_code=code, account_id=referee))
    await session.flush()

    fired = await maybe_payout_referral(session, referee_account_id=referee)
    assert fired is False


async def test_maybe_payout_referral_happy_path(session: AsyncSession):
    t = await _make_tenant(session)
    referrer = await _make_account(session, t.id, 1001)
    referee = await _make_account(session, t.id, 2001)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)
    session.add(StartTokenUse(token_code=code, account_id=referee))
    await _zero_balance(session, referrer)
    await _mark_paid(session, tenant_id=t.id, account_id=referee)
    await session.flush()

    fired = await maybe_payout_referral(session, referee_account_id=referee)
    assert fired is True

    bal = await session.get(AccountBalance, referrer)
    assert bal.package_credits == DEFAULT_REWARD_CREDITS

    use = (
        (await session.execute(select(StartTokenUse).where(StartTokenUse.account_id == referee)))
        .scalars()
        .one()
    )
    assert use.claimed_at is not None

    audit_rows = (
        (await session.execute(select(AuditLog).where(AuditLog.action == "referral.payout")))
        .scalars()
        .all()
    )
    assert len(audit_rows) == 1


async def test_maybe_payout_referral_one_shot(session: AsyncSession):
    t = await _make_tenant(session)
    referrer = await _make_account(session, t.id, 1001)
    referee = await _make_account(session, t.id, 2001)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)
    session.add(StartTokenUse(token_code=code, account_id=referee))
    await _zero_balance(session, referrer)
    await _mark_paid(session, tenant_id=t.id, account_id=referee)
    await session.flush()

    await maybe_payout_referral(session, referee_account_id=referee)
    await maybe_payout_referral(session, referee_account_id=referee)

    bal = await session.get(AccountBalance, referrer)
    assert bal.package_credits == DEFAULT_REWARD_CREDITS  # exactly one bump


async def test_maybe_payout_referral_zero_reward_closes_loop(session: AsyncSession):
    t = await _make_tenant(session)
    referrer = await _make_account(session, t.id, 1001)
    referee = await _make_account(session, t.id, 2001)
    by = await _make_account(session, t.id, 9001)
    await set_reward_credits(session, tenant_id=t.id, value=0, by_account_id=by)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)
    session.add(StartTokenUse(token_code=code, account_id=referee))
    await _zero_balance(session, referrer)
    await _mark_paid(session, tenant_id=t.id, account_id=referee)
    await session.flush()

    fired = await maybe_payout_referral(session, referee_account_id=referee)
    assert fired is True
    bal = await session.get(AccountBalance, referrer)
    assert bal.package_credits == 0
    use = (
        (await session.execute(select(StartTokenUse).where(StartTokenUse.account_id == referee)))
        .scalars()
        .one()
    )
    assert use.claimed_at is not None


async def test_referral_payout_is_ledger_backed(session, default_tenant):
    from sqlmodel import select

    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.db.models import (
        AccountPackage, Payment, StartToken, StartTokenUse,
    )
    from quantuum.domain.referrals import maybe_payout_referral

    referrer = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="ref_owner"
    )
    referee = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="ref_ee"
    )
    token = StartToken(
        code="refcode1", kind="referral", tenant_id=default_tenant.id,
        owner_account_id=referrer.id, status="active",
    )
    session.add(token)
    session.add(StartTokenUse(token_code="refcode1", account_id=referee.id))
    session.add(Payment(
        tenant_id=default_tenant.id, account_id=referee.id, provider_id=None,
        amount_cents=100, currency="XTR", status="paid",
    ))
    await session.commit()

    paid = await maybe_payout_referral(session, referee_account_id=referee.id)
    await session.commit()

    assert paid is True
    rows = (
        await session.execute(
            select(AccountPackage).where(AccountPackage.account_id == referrer.id)
        )
    ).scalars().all()
    assert any(r.source == "referral" and r.requests_remaining > 0 for r in rows)
