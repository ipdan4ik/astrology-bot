from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware

from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import resolve_tenant_id_by_bot


class TenantMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        bot = data.get("bot")
        if bot is not None:
            async with get_sessionmaker()() as session:
                data["tenant_id"] = await resolve_tenant_id_by_bot(session, bot.id)
        return await handler(event, data)
