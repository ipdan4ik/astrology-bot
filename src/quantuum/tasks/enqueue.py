from arq import create_pool
from arq.connections import RedisSettings

from quantuum.settings import get_settings

_pool = None


async def _get_pool():
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue_blueprint(blueprint_id: int, chat_id: int | None = None, request_id: int | None = None) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("blueprint_generate", blueprint_id, chat_id, request_id)


async def enqueue_qa(qa_id: int, chat_id: int | None = None, request_id: int | None = None) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("qa_generate", qa_id, chat_id, request_id)


async def enqueue_provision_tenant(tenant_id: int) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("provision_tenant", tenant_id)
