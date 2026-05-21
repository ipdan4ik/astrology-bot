from sqlmodel import select

from quantuum.db.models import AuditLog


async def record_audit(
    session,
    *,
    tenant_id,
    actor_account_id,
    action,
    entity_type=None,
    entity_id=None,
    payload=None,
    request_id=None,
    ip_address=None,
    user_agent=None,
) -> AuditLog:
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_account_id=actor_account_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        payload_jsonb=payload or {},
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(entry)
    await session.flush()
    return entry


async def list_audit(
    session, *, tenant_id=None, limit=100, offset=0
) -> list[AuditLog]:
    q = select(AuditLog)
    if tenant_id is not None:
        q = q.where(AuditLog.tenant_id == tenant_id)
    q = q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all())
