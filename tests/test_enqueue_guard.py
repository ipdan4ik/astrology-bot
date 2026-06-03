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
