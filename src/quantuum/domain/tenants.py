from sqlmodel import select

from quantuum.db.models import Tenant
from quantuum.settings import get_settings


async def get_default_tenant_id(session) -> int:
    settings = get_settings()
    result = await session.execute(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
    tenant = result.scalar_one()
    return tenant.id
