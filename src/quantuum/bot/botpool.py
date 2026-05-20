from aiogram import Bot

from quantuum.common.crypto import decrypt_token


def build_bots(tenant_bots: list) -> dict[int, Bot]:
    """Build aiogram Bot instances keyed by bot_telegram_id (rows without an id are skipped)."""
    pool: dict[int, Bot] = {}
    for tb in tenant_bots:
        if tb.bot_telegram_id is None:
            continue
        pool[tb.bot_telegram_id] = Bot(token=decrypt_token(tb.bot_token_enc))
    return pool
