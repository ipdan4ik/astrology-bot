"""Owner-console domain (Plan 5c, Task 1).

Resolve which tenants a Telegram user manages and authorize tenant-scoped
actions. Telegram identity is linked via
``AccountIdentity(provider="tg_chat", provider_user_id=str(tg_user_id))``.
A user has a separate ``Account`` per tenant, all sharing the same
``provider_user_id``; ``TenantRole`` grants ``owner``/``admin`` within a tenant.
"""
from sqlmodel import select

from quantuum.db.models import AccountIdentity, Tenant, TenantRole


async def managed_tenants(
    session, tg_user_id: str, *, roles=("owner", "admin")
) -> list[Tenant]:
    """Tenants where *tg_user_id* holds one of *roles*, ordered by id."""
    q = (
        select(Tenant)
        .join(TenantRole, TenantRole.tenant_id == Tenant.id)
        .join(AccountIdentity, AccountIdentity.account_id == TenantRole.account_id)
        .where(
            TenantRole.role.in_(roles),
            AccountIdentity.provider == "tg_chat",
            AccountIdentity.provider_user_id == str(tg_user_id),
        )
        .distinct()
        .order_by(Tenant.id)
    )
    result = await session.execute(q)
    return list(result.scalars().all())


async def account_id_for_role(
    session, *, tg_user_id, tenant_id, roles=("owner", "admin")
) -> int | None:
    """Account id of *tg_user_id* in *tenant_id* if it holds one of *roles*."""
    q = (
        select(TenantRole.account_id)
        .join(AccountIdentity, AccountIdentity.account_id == TenantRole.account_id)
        .where(
            TenantRole.tenant_id == tenant_id,
            TenantRole.role.in_(roles),
            AccountIdentity.provider == "tg_chat",
            AccountIdentity.provider_user_id == str(tg_user_id),
        )
        .limit(1)
    )
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def authorize_tenant_action(
    session, *, tg_user_id, tenant_id, roles=("owner", "admin")
) -> int | None:
    """Return the actor account id if *tg_user_id* may act on *tenant_id*, else None."""
    return await account_id_for_role(
        session, tg_user_id=tg_user_id, tenant_id=tenant_id, roles=roles
    )


async def resolve_managed_tenant_by_slug(
    session, *, tg_user_id, slug, roles=("owner", "admin")
) -> tuple[Tenant, int] | None:
    """Resolve a tenant by *slug* and authorize *tg_user_id*.

    Returns ``(tenant, actor_account_id)`` or None if the slug is unknown or the
    user lacks one of *roles* in that tenant.
    """
    result = await session.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return None
    actor = await account_id_for_role(
        session, tg_user_id=tg_user_id, tenant_id=tenant.id, roles=roles
    )
    if actor is None:
        return None
    return tenant, actor
