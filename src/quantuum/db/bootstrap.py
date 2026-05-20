from sqlmodel import select

from quantuum.db.models import Tenant
from quantuum.settings import get_settings


async def ensure_default_tenant(session) -> Tenant:
    settings = get_settings()
    result = await session.execute(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(slug=settings.default_tenant_slug, display_name=settings.default_tenant_name)
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
    return tenant
