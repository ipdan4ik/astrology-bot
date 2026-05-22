from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.session import get_sessionmaker
from quantuum.domain.accounts import touch_last_seen
from quantuum.i18n import Translator


class AccountMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        chat = getattr(event, "chat", None)
        tenant_id = data.get("tenant_id")
        if from_user is None or tenant_id is None:
            return await handler(event, data)

        async with get_sessionmaker()() as session:
            account = await find_or_create_account_by_tg(
                session, tenant_id=tenant_id, tg_user_id=str(from_user.id)
            )
            await touch_last_seen(session, account.id)
            translator = await Translator.build(
                session,
                tenant_id=tenant_id,
                preferred_lang=account.preferred_lang,
                tg_language_code=getattr(from_user, "language_code", None),
            )

        if account.status == "disabled":
            notice = await translator("account.banned.notice", reason=account.ban_reason or "—")
            if isinstance(event, CallbackQuery):
                await event.answer(notice, show_alert=True)
            else:
                answer = getattr(event, "answer", None)
                if answer is not None:
                    await answer(notice)
            return

        data["account"] = account
        data["chat_id"] = chat.id if chat is not None else None
        data["lang"] = translator.lang
        data["i18n"] = translator
        return await handler(event, data)
