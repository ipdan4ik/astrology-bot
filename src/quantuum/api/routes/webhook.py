from fastapi import APIRouter, HTTPException, Request

from quantuum.redis_client import push_update
from quantuum.settings import get_settings

router = APIRouter(tags=["webhook"])


@router.post("/tg/{secret_path}")
async def telegram_webhook(secret_path: str, request: Request) -> dict:
    if secret_path != get_settings().webhook_secret_path:
        raise HTTPException(status_code=404, detail="not found")
    update = await request.json()
    await push_update(update)
    return {"ok": True}
