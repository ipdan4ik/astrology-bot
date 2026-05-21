from sqlmodel import select

from quantuum.db.models import PaymentProvider


async def get_active_provider(session, tenant_id: int) -> PaymentProvider | None:
    result = await session.execute(
        select(PaymentProvider)
        .where(
            PaymentProvider.tenant_id == tenant_id,
            PaymentProvider.kind == "tg_stars",
            PaymentProvider.active == True,  # noqa: E712
        )
        .order_by(PaymentProvider.id)
    )
    return result.scalars().first()


async def ensure_stars_provider(session, tenant_id: int) -> PaymentProvider:
    """Get-or-create the tenant's active Telegram Stars provider row (idempotent)."""
    existing = await get_active_provider(session, tenant_id)
    if existing is not None:
        return existing
    provider = PaymentProvider(tenant_id=tenant_id, kind="tg_stars")
    session.add(provider)
    await session.commit()
    await session.refresh(provider)
    return provider
