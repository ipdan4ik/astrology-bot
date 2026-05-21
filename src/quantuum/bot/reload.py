import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from aiogram import Bot

from quantuum.common.crypto import decrypt_token
from quantuum.domain.tenants import get_platform_tenant_id, list_active_tenant_bots
from quantuum.logging_setup import get_logger
from quantuum.redis_client import BOT_RELOAD_CHANNEL, get_redis

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


async def reload_signals(interval: float) -> AsyncIterator[None]:
    """Yield once per nudge OR per `interval` seconds, whichever comes first.

    Each yield should drive one reconcile, so a missed nudge is still corrected within
    `interval` (self-healing). Redundant nudges coalesce into harmless extra reconciles.
    """
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(BOT_RELOAD_CHANNEL)
    try:
        while True:
            await pubsub.get_message(ignore_subscribe_messages=True, timeout=interval)
            yield
    finally:
        await pubsub.unsubscribe(BOT_RELOAD_CHANNEL)
        await pubsub.aclose()


async def poll_one(dp, bot: Bot, allowed_updates: list[str]) -> None:
    """Long-poll a single bot, feeding updates into `dp`. Resilient to transient errors."""
    await bot.delete_webhook(drop_pending_updates=True)
    offset = None
    while True:
        try:
            updates = await bot.get_updates(
                offset=offset, timeout=30, allowed_updates=allowed_updates
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("poll_error", bot_id=getattr(bot, "id", None))
            await asyncio.sleep(3)
            continue
        for u in updates:
            offset = u.update_id + 1
            await dp.feed_update(bot, u)


class PollingSupervisor:
    """Keeps one long-poll task per active bot, reconciling against the DB on demand.

    Dispatchers are created once and reused, so in-progress FSM state survives reconciles
    and existing bots are never interrupted when others come or go.
    """

    def __init__(self, sessionmaker, customer_dp, master_dp, *, spawn=None) -> None:
        self.sessionmaker = sessionmaker
        self.customer_dp = customer_dp
        self.master_dp = master_dp
        self.live: dict[int, tuple[Bot, asyncio.Task]] = {}
        self._spawn = spawn or self._default_spawn

    def _default_spawn(self, spec: BotSpec) -> tuple[Bot, asyncio.Task]:
        bot = Bot(token=spec.token)
        dp = self.master_dp if spec.is_master else self.customer_dp
        allowed = dp.resolve_used_update_types()
        return bot, asyncio.create_task(poll_one(dp, bot, allowed))

    async def reconcile(self) -> None:
        async with self.sessionmaker() as session:
            desired = await load_active_bot_specs(session, "polling")
        to_add, to_remove = diff_specs(set(self.live), desired)
        for bot_id in to_add:
            self.live[bot_id] = self._spawn(desired[bot_id])
        for bot_id in to_remove:
            bot, task = self.live.pop(bot_id)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await bot.session.close()
        if to_add or to_remove:
            logger.info("polling_reconciled", added=len(to_add), removed=len(to_remove))
