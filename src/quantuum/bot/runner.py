import asyncio

from aiogram import Bot, Dispatcher

from quantuum.bot.app import create_dispatcher
from quantuum.bot.botpool import build_bots
from quantuum.bot.master_app import create_master_dispatcher
from quantuum.db.bootstrap import (
    ensure_default_tenant,
    ensure_default_tenant_bot,
    ensure_master_bot,
    ensure_platform_stars_provider,
    ensure_platform_tenant,
)
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import get_platform_tenant_id, list_active_tenant_bots
from quantuum.logging_setup import configure_logging, get_logger
from quantuum.redis_client import pop_update

logger = get_logger("bot.runner")


class WebhookConsumer:
    def __init__(
        self,
        *,
        customer_dp: Dispatcher,
        master_dp: Dispatcher,
        customer_pool: dict[int, Bot],
        master_pool: dict[int, Bot],
    ) -> None:
        self.customer_dp = customer_dp
        self.master_dp = master_dp
        self.customer_pool = customer_pool
        self.master_pool = master_pool

    async def process(self, envelope: dict) -> None:
        bot_id = envelope["bot_id"]
        if bot_id in self.master_pool:
            await self.master_dp.feed_raw_update(bot=self.master_pool[bot_id], update=envelope["update"])
            return
        bot = self.customer_pool.get(bot_id)
        if bot is None:
            logger.warning("update_for_unknown_bot", bot_id=bot_id)
            return
        await self.customer_dp.feed_raw_update(bot=bot, update=envelope["update"])


async def run() -> None:
    configure_logging()
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        await ensure_platform_tenant(session)
        await ensure_master_bot(session)
        await ensure_platform_stars_provider(session)
        rows = await list_active_tenant_bots(session, transport="webhook")
        platform_id = await get_platform_tenant_id(session)

    master_rows = [r for r in rows if r.tenant_id == platform_id]
    customer_rows = [r for r in rows if r.tenant_id != platform_id]
    consumer = WebhookConsumer(
        customer_dp=create_dispatcher(),
        master_dp=create_master_dispatcher(),
        customer_pool=build_bots(customer_rows),
        master_pool=build_bots(master_rows),
    )
    logger.info(
        "bot_runner_started",
        customer_bots=len(consumer.customer_pool),
        master_bots=len(consumer.master_pool),
    )
    while True:
        envelope = await pop_update(timeout=5)
        if envelope is None:
            continue
        try:
            await consumer.process(envelope)
        except Exception:
            logger.exception("update_processing_failed", bot_id=envelope.get("bot_id"))


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
