from datetime import timedelta

from quantuum.common.datetime import utcnow
from quantuum.db.models import Account, AccountIdentity, TenantInvite


async def test_create_invite_row(session):
    inv = TenantInvite(code="abc123", tier="basic", max_uses=3, expires_at=utcnow() + timedelta(days=1))
    session.add(inv)
    await session.commit()
    await session.refresh(inv)
    assert inv.id is not None
    assert inv.used_count == 0
    assert inv.status == "active"


async def test_superadmin_account_has_null_tenant(session):
    acc = Account(tenant_id=None, is_superadmin=True)
    session.add(acc)
    await session.flush()
    session.add(AccountIdentity(account_id=acc.id, provider="magic_link", email="root@x.com"))
    await session.commit()
    await session.refresh(acc)
    assert acc.tenant_id is None
    assert acc.is_superadmin is True
