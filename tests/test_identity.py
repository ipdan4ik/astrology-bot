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
    # New accounts are seeded with welcome credits (SIGNUP_CREDITS); the
    # trial flag is pre-marked used because the welcome bundle replaces it.
    from quantuum.auth.identity import SIGNUP_CREDITS
    assert bal.package_credits == SIGNUP_CREDITS
    assert bal.free_trial_used is True


async def test_find_superadmin_by_email(session):
    from quantuum.auth.identity import find_superadmin_by_email
    from quantuum.db.models import Account, AccountIdentity

    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    session.add(AccountIdentity(account_id=acc.id, provider="magic_link", email="sa@x.com"))
    await session.commit()

    found = await find_superadmin_by_email(session, "sa@x.com")
    assert found is not None and found.id == acc.id
    assert await find_superadmin_by_email(session, "nobody@x.com") is None
