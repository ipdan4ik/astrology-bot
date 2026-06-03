import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from quantuum import redis_client
from quantuum.api.app import create_app
from quantuum.db.models import TenantBot


@pytest_asyncio.fixture
async def client(engine, session, default_tenant):
    await redis_client.get_redis().flushdb()
    session.add(TenantBot(
        tenant_id=default_tenant.id, bot_telegram_id=4242, bot_token_enc=b"e",
        webhook_secret_path="hook-4242", transport="webhook",
    ))
    await session.commit()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await redis_client.get_redis().flushdb()


async def test_webhook_unknown_secret_404(client):
    r = await client.post("/tg/nope", json={"update_id": 1})
    assert r.status_code == 404


async def test_webhook_pushes_update_with_bot_id(client):
    r = await client.post("/tg/hook-4242", json={"update_id": 9, "message": {"text": "hi"}})
    assert r.status_code == 200
    item = await redis_client.pop_update(timeout=2)
    assert item["bot_id"] == 4242
    assert item["update"]["update_id"] == 9


async def test_webhook_dedupes_repeated_update(client, session, default_tenant):
    from quantuum.db.models import TenantBot
    from quantuum.redis_client import get_redis, UPDATE_QUEUE_KEY
    bot = TenantBot(
        tenant_id=default_tenant.id, bot_telegram_id=700001, bot_token_enc=b"x",
        transport="webhook", webhook_secret_path="wh-dedupe", status="active",
    )
    session.add(bot)
    await session.commit()

    payload = {"update_id": 555, "message": {"text": "hi"}}
    r1 = await client.post("/tg/wh-dedupe", json=payload)
    r2 = await client.post("/tg/wh-dedupe", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200

    qlen = await get_redis().llen(UPDATE_QUEUE_KEY)
    assert qlen == 1  # second (duplicate) update was dropped
