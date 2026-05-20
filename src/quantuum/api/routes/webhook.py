from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.api.deps import get_session
from quantuum.domain.tenants import get_tenant_bot_by_webhook_secret
from quantuum.redis_client import push_update

router = APIRouter(tags=["webhook"])


@router.post("/tg/{secret_path}")
async def telegram_webhook(
    secret_path: str, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    tenant_bot = await get_tenant_bot_by_webhook_secret(session, secret_path)
    if tenant_bot is None or tenant_bot.bot_telegram_id is None:
        raise HTTPException(status_code=404, detail="not found")
    update = await request.json()
    await push_update(tenant_bot.bot_telegram_id, update)
    return {"ok": True}
