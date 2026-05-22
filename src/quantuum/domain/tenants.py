from sqlalchemy import func
from sqlmodel import select

from quantuum.db.models import Tenant, TenantBot, TenantRole
from quantuum.settings import get_settings


async def set_tenant_status(
    session, tenant_id: int, status: str, bot_status: str
) -> None:
    """Set tenant.status and update all its TenantBot rows to bot_status."""
    tenant = await session.get(Tenant, tenant_id)
    if tenant is not None:
        tenant.status = status
        session.add(tenant)

    result = await session.execute(
        select(TenantBot).where(TenantBot.tenant_id == tenant_id)
    )
    for bot in result.scalars().all():
        bot.status = bot_status
        session.add(bot)

    await session.flush()


async def archive_tenant(session, tenant_id: int) -> Tenant | None:
    """Soft-delete a tenant: archive it and tombstone its unique fields.

    Renames the slug (``{slug}__del{id}``) and nulls every bot's
    ``bot_telegram_id`` so the same slug and Telegram bot can be re-onboarded
    later without unique-constraint collisions. Idempotent: a no-op if the tenant
    is already archived. Returns the tenant, or None if not found. The caller
    records audit + commits (mirrors ``set_tenant_status`` usage).
    """
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        return None
    if tenant.status == "archived":
        return tenant
    tenant.status = "archived"
    tenant.slug = f"{tenant.slug}__del{tenant_id}"
    session.add(tenant)

    result = await session.execute(
        select(TenantBot).where(TenantBot.tenant_id == tenant_id)
    )
    for bot in result.scalars().all():
        bot.bot_telegram_id = None
        bot.status = "archived"
        session.add(bot)

    await session.flush()
    return tenant


async def list_all_tenants(session) -> list[Tenant]:
    """All non-archived, non-platform tenants, ordered by id (superadmin cabinet)."""
    result = await session.execute(
        select(Tenant)
        .where(Tenant.status != "archived", Tenant.is_platform == False)  # noqa: E712
        .order_by(Tenant.id)
    )
    return list(result.scalars().all())


async def get_default_tenant_id(session) -> int:
    settings = get_settings()
    result = await session.execute(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
    tenant = result.scalar_one()
    return tenant.id


async def resolve_tenant_id_by_bot(session, bot_telegram_id: int) -> int | None:
    result = await session.execute(
        select(TenantBot.tenant_id).where(
            TenantBot.bot_telegram_id == bot_telegram_id, TenantBot.status == "active"
        )
    )
    return result.scalar_one_or_none()


async def get_tenant_bot_by_webhook_secret(session, secret: str) -> TenantBot | None:
    result = await session.execute(
        select(TenantBot).where(
            TenantBot.webhook_secret_path == secret, TenantBot.status == "active"
        )
    )
    return result.scalar_one_or_none()


async def list_active_tenant_bots(session, transport: str | None = None) -> list[TenantBot]:
    query = select(TenantBot).where(TenantBot.status == "active")
    if transport is not None:
        query = query.where(TenantBot.transport == transport)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_active_tenant_bot(session, tenant_id: int) -> TenantBot | None:
    result = await session.execute(
        select(TenantBot).where(TenantBot.tenant_id == tenant_id, TenantBot.status == "active")
    )
    return result.scalars().first()


async def get_tenant_bot(session, tenant_id: int) -> TenantBot | None:
    """First TenantBot for a tenant, regardless of status (None if none).

    Unlike get_active_tenant_bot, this also returns paused/archived bots — used
    where the bot's metadata (e.g. @username) is shown for a non-active tenant.
    """
    result = await session.execute(
        select(TenantBot).where(TenantBot.tenant_id == tenant_id).limit(1)
    )
    return result.scalars().first()


async def grant_role(
    session, *, tenant_id: int, account_id: int, role: str, granted_by_account_id: int | None = None
) -> None:
    if await account_has_role(session, tenant_id=tenant_id, account_id=account_id, role=role):
        return
    session.add(
        TenantRole(
            tenant_id=tenant_id, account_id=account_id, role=role,
            granted_by_account_id=granted_by_account_id,
        )
    )
    await session.commit()


async def account_has_role(session, *, tenant_id: int, account_id: int, role: str) -> bool:
    result = await session.execute(
        select(TenantRole.id).where(
            TenantRole.tenant_id == tenant_id,
            TenantRole.account_id == account_id,
            TenantRole.role == role,
        )
    )
    return result.scalar_one_or_none() is not None


async def get_platform_tenant_id(session) -> int | None:
    result = await session.execute(select(Tenant.id).where(Tenant.is_platform == True))  # noqa: E712
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Role management helpers (Tasks 5 + 6)
# ---------------------------------------------------------------------------


async def list_roles(session, tenant_id: int) -> list[TenantRole]:
    """Return all TenantRole rows for a tenant."""
    result = await session.execute(
        select(TenantRole).where(TenantRole.tenant_id == tenant_id)
    )
    return list(result.scalars().all())


async def revoke_role(session, role_id: int) -> TenantRole | None:
    """Delete a TenantRole by id.  Returns the deleted row or None."""
    role = await session.get(TenantRole, role_id)
    if role is None:
        return None
    await session.delete(role)
    await session.flush()
    return role


async def count_owners(session, tenant_id: int) -> int:
    """Return the number of 'owner' roles for a tenant."""
    result = await session.execute(
        select(func.count()).where(
            TenantRole.tenant_id == tenant_id,
            TenantRole.role == "owner",
        )
    )
    return result.scalar_one()


async def transfer_ownership(
    session,
    *,
    tenant_id: int,
    new_owner_account_id: int,
    revoke_previous: bool = False,
    actor_id: int | None = None,
) -> Tenant:
    """Grant 'owner' to new_owner, update primary_owner_account_id.

    If *revoke_previous* is True and there was a distinct prior primary owner,
    that account's 'owner' role is revoked.

    The caller is responsible for validating the target account and committing.
    """
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError(f"tenant {tenant_id} not found")

    prior_primary = tenant.primary_owner_account_id

    # Grant owner role to new owner (idempotent — skip if already has it).
    if not await account_has_role(
        session, tenant_id=tenant_id, account_id=new_owner_account_id, role="owner"
    ):
        session.add(
            TenantRole(
                tenant_id=tenant_id,
                account_id=new_owner_account_id,
                role="owner",
                granted_by_account_id=actor_id,
            )
        )
        await session.flush()

    # Update primary owner pointer.
    tenant.primary_owner_account_id = new_owner_account_id
    session.add(tenant)
    await session.flush()

    # Optionally revoke previous primary owner's role.
    if revoke_previous and prior_primary is not None and prior_primary != new_owner_account_id:
        result = await session.execute(
            select(TenantRole).where(
                TenantRole.tenant_id == tenant_id,
                TenantRole.account_id == prior_primary,
                TenantRole.role == "owner",
            )
        )
        old_role = result.scalar_one_or_none()
        if old_role is not None:
            await session.delete(old_role)
            await session.flush()

    return tenant
