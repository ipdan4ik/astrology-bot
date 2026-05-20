from quantuum.auth.identity import (
    find_or_create_account_by_email,
    find_or_create_account_by_tg,
)


async def test_email_identity_idempotent(session, default_tenant):
    a1 = await find_or_create_account_by_email(
        session, tenant_id=default_tenant.id, email="x@example.com"
    )
    a2 = await find_or_create_account_by_email(
        session, tenant_id=default_tenant.id, email="x@example.com"
    )
    assert a1.id == a2.id


async def test_tg_identity_creates_balance(session, default_tenant):
    from quantuum.db.models import AccountBalance

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="555"
    )
    bal = await session.get(AccountBalance, acc.id)
    assert bal is not None
    assert bal.free_trial_used is False
