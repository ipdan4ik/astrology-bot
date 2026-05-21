import re

from aiogram.types import (
    KeyboardButton,
    KeyboardButtonRequestManagedBot,
    ReplyKeyboardMarkup,
)

from quantuum.db.models import Tenant
from quantuum.domain.provisioning import master_can_manage_bots
from quantuum.logging_setup import get_logger

logger = get_logger("tasks.provision")

_MANUAL_TOKEN_PROMPT = (
    "Автосоздание бота недоступно. Создай нового бота через @BotFather "
    "и пришли сюда его токен одним сообщением."
)
_MANAGED_PROMPT = (
    "Нажми кнопку ниже — Telegram создаст бота, а я подхвачу его автоматически. "
    "Имя пользователя можно поправить на экране создания."
)
_MANAGED_BUTTON = "🤖 Создать бота"


def _suggest_username(slug: str) -> str:
    """Telegram-safe suggested bot username (a-z0-9_, must end with 'bot')."""
    base = re.sub(r"[^a-z0-9_]", "", slug.lower()) or "quantuum"
    return base if base.endswith("bot") else f"{base}_bot"


def _managed_bot_keyboard(tenant: Tenant) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=_MANAGED_BUTTON,
                    request_managed_bot=KeyboardButtonRequestManagedBot(
                        request_id=tenant.id,
                        suggested_username=_suggest_username(tenant.slug),
                        suggested_name=tenant.display_name,
                    ),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def provision_tenant(ctx, tenant_id: int) -> None:
    sessionmaker = ctx["sessionmaker"]
    master_bot = ctx.get("master_bot")
    async with sessionmaker() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            logger.warning("provision_unknown_tenant", tenant_id=tenant_id)
            return

        can_manage = master_bot is not None and await master_can_manage_bots(master_bot)
        if can_manage:
            # Programmatic path (Bot API 9.6 Managed Bots): the owner taps one button,
            # Telegram creates the bot, and on_managed_bot_created fetches its token.
            tenant.status = "awaiting_managed_bot"
            session.add(tenant)
            await session.commit()
            if tenant.owner_chat_id:
                await master_bot.send_message(
                    int(tenant.owner_chat_id),
                    _MANAGED_PROMPT,
                    reply_markup=_managed_bot_keyboard(tenant),
                )
            logger.info("provision_awaiting_managed_bot", tenant_id=tenant_id)
            return

        # Fallback: master bot lacks Bot Management Mode -> owner pastes a BotFather token.
        tenant.status = "awaiting_manual_token"
        session.add(tenant)
        await session.commit()
        if master_bot is not None and tenant.owner_chat_id:
            await master_bot.send_message(int(tenant.owner_chat_id), _MANUAL_TOKEN_PROMPT)
        logger.info("provision_awaiting_manual_token", tenant_id=tenant_id)
