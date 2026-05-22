from sqlmodel import select

from quantuum.db.models import Account


async def test_account_has_ban_reason_column(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id, status="disabled", ban_reason="spam")
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    row = (await session.execute(select(Account).where(Account.id == acc.id))).scalar_one()
    assert row.status == "disabled"
    assert row.ban_reason == "spam"


async def test_account_ban_reason_defaults_none(session, default_tenant):
    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    assert acc.status == "active"
    assert acc.ban_reason is None
