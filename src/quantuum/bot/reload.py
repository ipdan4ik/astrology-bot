from dataclasses import dataclass

from quantuum.common.crypto import decrypt_token
from quantuum.domain.tenants import get_platform_tenant_id, list_active_tenant_bots
from quantuum.logging_setup import get_logger

logger = get_logger("bot.reload")


@dataclass(frozen=True)
class BotSpec:
    bot_telegram_id: int
    token: str  # decrypted bot token
    is_master: bool  # platform tenant => master dispatcher


def diff_specs(
    current_ids: set[int], desired: dict[int, BotSpec]
) -> tuple[set[int], set[int]]:
    """Return (to_add, to_remove) bot ids. Pure set math."""
    return set(desired) - current_ids, current_ids - set(desired)


async def load_active_bot_specs(session, transport: str) -> dict[int, BotSpec]:
    """All active tenant bots for `transport`, keyed by bot_telegram_id.

    Token is decrypted; is_master = the bot belongs to the platform tenant. Rows with a
    null bot_telegram_id or empty token are skipped.
    """
    platform_id = await get_platform_tenant_id(session)
    specs: dict[int, BotSpec] = {}
    for tb in await list_active_tenant_bots(session, transport):
        if tb.bot_telegram_id is None or not tb.bot_token_enc:
            continue
        specs[tb.bot_telegram_id] = BotSpec(
            bot_telegram_id=tb.bot_telegram_id,
            token=decrypt_token(tb.bot_token_enc),
            is_master=(tb.tenant_id == platform_id),
        )
    return specs
