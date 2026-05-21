from quantuum.common.datetime import utcnow
from quantuum.db.models import Payout, TenantLicense


async def test_payout_row(session, default_tenant):
    p = Payout(
        tenant_id=default_tenant.id, period_start=utcnow(), period_end=utcnow(),
        gross_amount_cents=1000, platform_fee_cents=300, net_amount_cents=700,
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert p.id is not None
    assert p.status == "calculated"
    assert p.currency == "XTR"


async def test_tenant_license_row(session, default_tenant):
    lic = TenantLicense(tenant_id=default_tenant.id, status="active", price_cents=5000)
    session.add(lic)
    await session.commit()
    await session.refresh(lic)
    assert lic.id is not None
    assert lic.currency == "XTR"
