from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.api.deps import get_session
from quantuum.domain.tenants import get_tenant_bot_by_webhook_secret
from quantuum.redis_client import mark_update_seen, push_update

router = APIRouter(tags=["webhook"])


@router.post("/tg/{secret_path}")
async def telegram_webhook(
    secret_path: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant_bot = await get_tenant_bot_by_webhook_secret(session, secret_path)
    if tenant_bot is None or tenant_bot.bot_telegram_id is None:
        raise HTTPException(status_code=404, detail="not found")
    if (
        tenant_bot.webhook_secret_token is not None
        and x_telegram_bot_api_secret_token != tenant_bot.webhook_secret_token
    ):
        raise HTTPException(status_code=403, detail="bad secret token")
    update = await request.json()
    if not await mark_update_seen(tenant_bot.bot_telegram_id, update.get("update_id")):
        return {"ok": True, "duplicate": True}
    await push_update(tenant_bot.bot_telegram_id, update)
    return {"ok": True}
