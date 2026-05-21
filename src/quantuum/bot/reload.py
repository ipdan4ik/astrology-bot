from dataclasses import dataclass

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
