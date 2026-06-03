from aiogram import Bot
from aiogram.types import BufferedInputFile

from quantuum.common.crypto import decrypt_token
from quantuum.domain.tenants import get_active_tenant_bot
from quantuum.logging_setup import get_logger

logger = get_logger("task.delivery")


async def deliver_via_tenant_bot(
    sessionmaker,
    *,
    tenant_id: int,
    chat_id: int,
    text: str,
    filename: str,
    preview_len: int,
    always_document: bool,
) -> None:
    """Deliver a generated reading to ``chat_id`` through the OWNING tenant's bot.

    Multi-tenant: each tenant has its own bot and a user typically only ever talks to that
    bot — the platform default bot cannot initiate a chat with them. So delivery must use the
    tenant's bot, resolved from the reading's ``tenant_id`` (not a single shared ctx bot).

    Sends ``text[:preview_len]`` as a message and attaches the full text as a document when
    ``always_document`` or the text exceeds ``preview_len``. Send errors propagate so the
    caller can log them as a best-effort delivery failure.
    """
    async with sessionmaker() as session:
        tb = await get_active_tenant_bot(session, tenant_id)
    if tb is None or not tb.bot_token_enc:
        logger.warning("delivery_no_tenant_bot", tenant_id=tenant_id, chat_id=chat_id)
        return
    bot = Bot(token=decrypt_token(tb.bot_token_enc))
    try:
        await bot.send_message(chat_id, text[:preview_len], parse_mode="Markdown")
        if always_document or len(text) > preview_len:
            await bot.send_document(
                chat_id, BufferedInputFile(text.encode(), filename=filename)
            )
    finally:
        await bot.session.close()
