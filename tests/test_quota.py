import pytest

from quantuum.common.exceptions import InsufficientFundsError
from quantuum.domain.quota import consume_quota, refund_quota


async def _make_account(session, tenant_id):
    from quantuum.auth.identity import find_or_create_account_by_tg

    return await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="1")


async def test_first_blueprint_uses_trial(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "trial"


async def test_second_blueprint_blocked(session, default_tenant):
    acc = await _make_account(session, default_tenant.id)
    await consume_quota(session, acc.id, "blueprint")
    with pytest.raises(InsufficientFundsError):
        await consume_quota(session, acc.id, "blueprint")


async def test_refund_restores_trial(session, default_tenant):
    from quantuum.db.models import Request

    acc = await _make_account(session, default_tenant.id)
    await consume_quota(session, acc.id, "blueprint")
    req = Request(
        tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint", charged_against="trial"
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

    await refund_quota(session, req.id)

    # trial available again
    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "trial"
