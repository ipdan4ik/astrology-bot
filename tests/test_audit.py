import pytest
from quantuum.domain.audit import list_audit, record_audit


@pytest.mark.asyncio
async def test_record_and_list_tenant_scoped(session, default_tenant):
    """record entries for tenant + platform (None); list_audit filters correctly."""
    tenant_entry = await record_audit(
        session,
        tenant_id=default_tenant.id,
        actor_account_id=None,
        action="test.action",
        entity_type="thing",
        entity_id="42",
        payload={"key": "value"},
    )
    await session.flush()

    platform_entry = await record_audit(
        session,
        tenant_id=None,
        actor_account_id=None,
        action="platform.action",
    )
    await session.commit()

    # tenant-scoped returns only the tenant entry
    tenant_results = await list_audit(session, tenant_id=default_tenant.id)
    assert len(tenant_results) == 1
    assert tenant_results[0].id == tenant_entry.id
    assert tenant_results[0].action == "test.action"

    # no filter returns both, newest first
    all_results = await list_audit(session)
    assert len(all_results) == 2
    # platform entry was inserted last (higher id), so it should come first
    ids = [r.id for r in all_results]
    assert platform_entry.id in ids
    assert tenant_entry.id in ids


@pytest.mark.asyncio
async def test_entity_id_stringified(session, default_tenant):
    """entity_id=int is stored as string."""
    await record_audit(
        session,
        tenant_id=default_tenant.id,
        actor_account_id=None,
        action="create.thing",
        entity_id=123,
    )
    await session.commit()

    results = await list_audit(session, tenant_id=default_tenant.id)
    assert len(results) == 1
    assert results[0].entity_id == "123"


@pytest.mark.asyncio
async def test_payload_roundtrip(session, default_tenant):
    """JSONB payload round-trips correctly."""
    payload = {"before": {"x": 1}, "after": {"x": 2}}
    await record_audit(
        session,
        tenant_id=default_tenant.id,
        actor_account_id=None,
        action="update.thing",
        payload=payload,
    )
    await session.commit()

    results = await list_audit(session, tenant_id=default_tenant.id)
    assert len(results) == 1
    assert results[0].payload_jsonb == payload
