from quantuum.db.models import Tenant


async def test_list_all_tenants_excludes_archived_and_platform(session):
    from quantuum.domain.tenants import list_all_tenants

    active = Tenant(slug="a-co", display_name="A Co", status="active")
    paused = Tenant(slug="b-co", display_name="B Co", status="suspended")
    archived = Tenant(slug="c-co__del9", display_name="C Co", status="archived")
    platform = Tenant(slug="platform", display_name="Platform", is_platform=True)
    for t in (active, paused, archived, platform):
        session.add(t)
    await session.commit()

    rows = await list_all_tenants(session)
    slugs = [t.slug for t in rows]
    assert "a-co" in slugs
    assert "b-co" in slugs  # suspended is still shown (manageable)
    assert "c-co__del9" not in slugs  # archived hidden
    assert "platform" not in slugs  # platform hidden


def test_superadmin_cb_roundtrips():
    from quantuum.bot.ui.callbacks import SuperAdminCb

    packed = SuperAdminCb(action="tenant", tenant_id=42).pack()
    cb = SuperAdminCb.unpack(packed)
    assert cb.action == "tenant"
    assert cb.tenant_id == 42
    assert cb.invite_id == 0  # default
