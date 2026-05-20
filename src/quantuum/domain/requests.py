from quantuum.common.datetime import utcnow
from quantuum.db.models import Request


async def create_request(
    session, *, tenant_id: int, account_id: int, kind: str, charged_against: str
) -> Request:
    request = Request(
        tenant_id=tenant_id,
        account_id=account_id,
        kind=kind,
        charged_against=charged_against,
        status="pending",
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return request


async def complete_request(session, request_id: int, *, reference_id: int, reference_type: str) -> None:
    request = await session.get(Request, request_id)
    if request is not None:
        request.status = "done"
        request.reference_id = reference_id
        request.reference_type = reference_type
        request.completed_at = utcnow()
        session.add(request)
        await session.commit()


async def fail_request(session, request_id: int) -> None:
    request = await session.get(Request, request_id)
    if request is not None:
        request.status = "failed"
        request.completed_at = utcnow()
        session.add(request)
        await session.commit()
