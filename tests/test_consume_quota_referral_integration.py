from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    AccountBalance,
    Payment,
    StartTokenUse,
    Tenant,
)
from quantuum.domain.quota import consume_quota
from quantuum.domain.referrals import (
    DEFAULT_REWARD_CREDITS,
    generate_referral_code,
)


async def _setup(session: AsyncSession):
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    referrer = (
        await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_user_id="1001"
        )
    ).id
    referee = (
        await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_user_id="2001"
        )
    ).id
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)
    session.add(StartTokenUse(token_code=code, account_id=referee))

    # find_or_create_account_by_tg seeds AccountBalance with welcome credits.
    # Reset referrer to 0, ensure referee has enough credits to spend.
    bal_referrer = await session.get(AccountBalance, referrer)
    bal_referrer.package_credits = 0
    bal_referee = await session.get(AccountBalance, referee)
    bal_referee.package_credits = 10
    await session.flush()
    return t, referrer, referee


async def test_consume_quota_fires_payout_when_paid(session: AsyncSession):
    t, referrer, referee = await _setup(session)
    session.add(
        Payment(
            tenant_id=t.id, account_id=referee, amount_cents=100,
            status="paid", paid_at=utcnow(),
        )
    )
    await session.flush()

    charged = await consume_quota(session, referee, kind="qa")
    assert charged == "package"

    bal = await session.get(AccountBalance, referrer)
    assert bal.package_credits == DEFAULT_REWARD_CREDITS

    use = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == referee)
        )
    ).scalars().one()
    assert use.claimed_at is not None


async def test_consume_quota_no_payout_without_payment(session: AsyncSession):
    t, referrer, referee = await _setup(session)
    charged = await consume_quota(session, referee, kind="qa")
    assert charged == "package"

    bal = await session.get(AccountBalance, referrer)
    assert bal.package_credits == 0
    use = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == referee)
        )
    ).scalars().one()
    assert use.claimed_at is None


async def test_consume_quota_no_double_payout(session: AsyncSession):
    t, referrer, referee = await _setup(session)
    session.add(
        Payment(
            tenant_id=t.id, account_id=referee, amount_cents=100,
            status="paid", paid_at=utcnow(),
        )
    )
    bal_referee = await session.get(AccountBalance, referee)
    bal_referee.package_credits = 10
    await session.flush()

    await consume_quota(session, referee, kind="qa")
    await consume_quota(session, referee, kind="qa")

    bal = await session.get(AccountBalance, referrer)
    assert bal.package_credits == DEFAULT_REWARD_CREDITS


async def test_consume_quota_payout_failure_does_not_block_spend(
    session: AsyncSession, monkeypatch
):
    t, referrer, referee = await _setup(session)
    session.add(
        Payment(
            tenant_id=t.id, account_id=referee, amount_cents=100,
            status="paid", paid_at=utcnow(),
        )
    )
    await session.flush()

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated payout failure")

    import quantuum.domain.quota as quota_mod
    monkeypatch.setattr(quota_mod, "maybe_payout_referral", _boom)

    charged = await consume_quota(session, referee, kind="qa")
    assert charged == "package"

    bal_referee = await session.get(AccountBalance, referee)
    assert bal_referee.package_credits == 9  # spend went through
