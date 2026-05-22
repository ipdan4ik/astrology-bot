"""Unit tests for the owner-console domain (Plan 5c, Task 1).

Resolve a Telegram user's managed tenants + authorize tenant actions.
A user has a separate Account per tenant but the SAME tg provider_user_id.
"""
import pytest

from quantuum.db.models import Account, AccountIdentity, Tenant
from quantuum.domain.owner_console import (
    account_id_for_role,
    authorize_tenant_action,
    managed_tenants,
    resolve_managed_tenant_by_slug,
)
from quantuum.domain.tenants import grant_role

pytestmark = pytest.mark.asyncio

TG = "111"


async def _make_tenant(session, slug: str, display_name: str) -> Tenant:
    t = Tenant(slug=slug, display_name=display_name)
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


async def _seed_account_with_role(session, *, tenant: Tenant, role: str | None, tg: str) -> Account:
    """Create an Account in *tenant*, link a tg identity, optionally grant *role*."""
    acc = Account(tenant_id=tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    session.add(
        AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=tg)
    )
    await session.commit()

    if role is not None:
        await grant_role(session, tenant_id=tenant.id, account_id=acc.id, role=role)
    return acc


@pytest.fixture
async def seeded(session):
    """Tenant T (tg owner), U (tg admin), V (tg has account but NO role)."""
    t = await _make_tenant(session, "t-slug", "Tenant T")
    u = await _make_tenant(session, "u-slug", "Tenant U")
    v = await _make_tenant(session, "v-slug", "Tenant V")

    owner_acct = await _seed_account_with_role(session, tenant=t, role="owner", tg=TG)
    admin_acct = await _seed_account_with_role(session, tenant=u, role="admin", tg=TG)
    no_role_acct = await _seed_account_with_role(session, tenant=v, role=None, tg=TG)

    return {
        "T": t,
        "U": u,
        "V": v,
        "owner_acct": owner_acct,
        "admin_acct": admin_acct,
        "no_role_acct": no_role_acct,
    }


# ── managed_tenants ──────────────────────────────────────────────────────────

async def test_managed_tenants_owner_and_admin(session, seeded):
    tenants = await managed_tenants(session, TG)
    assert [t.id for t in tenants] == [seeded["T"].id, seeded["U"].id]


async def test_managed_tenants_owner_only_filter(session, seeded):
    tenants = await managed_tenants(session, TG, roles=("owner",))
    assert [t.id for t in tenants] == [seeded["T"].id]


async def test_managed_tenants_unknown_user(session, seeded):
    assert await managed_tenants(session, "999") == []


# ── account_id_for_role ──────────────────────────────────────────────────────

async def test_account_id_for_role_owner(session, seeded):
    actor = await account_id_for_role(session, tg_user_id=TG, tenant_id=seeded["T"].id)
    assert actor == seeded["owner_acct"].id


# ── authorize_tenant_action ──────────────────────────────────────────────────

async def test_authorize_owner_tenant(session, seeded):
    actor = await authorize_tenant_action(session, tg_user_id=TG, tenant_id=seeded["T"].id)
    assert actor == seeded["owner_acct"].id


async def test_authorize_no_role_tenant_returns_none(session, seeded):
    actor = await authorize_tenant_action(session, tg_user_id=TG, tenant_id=seeded["V"].id)
    assert actor is None


async def test_authorize_owner_only_on_owner_tenant(session, seeded):
    actor = await authorize_tenant_action(
        session, tg_user_id=TG, tenant_id=seeded["T"].id, roles=("owner",)
    )
    assert actor == seeded["owner_acct"].id


async def test_authorize_owner_only_on_admin_tenant_returns_none(session, seeded):
    actor = await authorize_tenant_action(
        session, tg_user_id=TG, tenant_id=seeded["U"].id, roles=("owner",)
    )
    assert actor is None


# ── resolve_managed_tenant_by_slug ───────────────────────────────────────────

async def test_resolve_by_slug_owner(session, seeded):
    result = await resolve_managed_tenant_by_slug(session, tg_user_id=TG, slug=seeded["T"].slug)
    assert result is not None
    tenant, actor = result
    assert tenant.id == seeded["T"].id
    assert actor == seeded["owner_acct"].id


async def test_resolve_by_slug_unknown_slug(session, seeded):
    assert await resolve_managed_tenant_by_slug(session, tg_user_id=TG, slug="nope") is None


async def test_resolve_by_slug_no_role(session, seeded):
    assert (
        await resolve_managed_tenant_by_slug(session, tg_user_id=TG, slug=seeded["V"].slug) is None
    )


async def test_managed_tenants_excludes_archived(session):
    from quantuum.db.models import Account, AccountIdentity, Tenant
    from quantuum.domain.owner_console import managed_tenants
    from quantuum.domain.tenants import grant_role

    tg = "70700"
    # Two tenants owned by the same tg user: one active, one archived.
    active = Tenant(slug="keep", display_name="Keep", status="active")
    archived = Tenant(slug="gone__del1", display_name="Gone", status="archived")
    session.add(active)
    session.add(archived)
    await session.commit()
    await session.refresh(active)
    await session.refresh(archived)
    for t in (active, archived):
        acc = Account(tenant_id=t.id)
        session.add(acc)
        await session.commit()
        await session.refresh(acc)
        session.add(
            AccountIdentity(account_id=acc.id, provider="tg_chat", provider_user_id=tg)
        )
        await session.commit()
        await grant_role(session, tenant_id=t.id, account_id=acc.id, role="owner")

    rows = await managed_tenants(session, tg)
    slugs = {t.slug for t in rows}
    assert "keep" in slugs
    assert "gone__del1" not in slugs
