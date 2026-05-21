import asyncio

from aiogram import Bot, Dispatcher

from quantuum.bot.app import create_dispatcher
from quantuum.bot.reload import diff_specs, load_active_bot_specs, reload_signals
from quantuum.bot.master_app import create_master_dispatcher
from quantuum.db.bootstrap import (
    ensure_base_strings,
    ensure_default_tenant,
    ensure_default_tenant_bot,
    ensure_master_bot,
    ensure_platform_stars_provider,
    ensure_platform_tenant,
    ensure_tenant_default_language,
)
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import get_default_tenant_id
from quantuum.logging_setup import configure_logging, get_logger
from quantuum.redis_client import pop_update
from quantuum.settings import get_settings

logger = get_logger("bot.runner")


class WebhookConsumer:
    def __init__(
        self,
        *,
        customer_dp: Dispatcher,
        master_dp: Dispatcher,
        customer_pool: dict[int, Bot],
        master_pool: dict[int, Bot],
        sessionmaker=None,
    ) -> None:
        self.customer_dp = customer_dp
        self.master_dp = master_dp
        self.customer_pool = customer_pool
        self.master_pool = master_pool
        self.sessionmaker = sessionmaker

    async def reconcile(self) -> None:
        async with self.sessionmaker() as session:
            desired = await load_active_bot_specs(session, "webhook")
        live = set(self.customer_pool) | set(self.master_pool)
        to_add, to_remove = diff_specs(live, desired)
        for bot_id in to_add:
            spec = desired[bot_id]
            bot = Bot(token=spec.token)
            (self.master_pool if spec.is_master else self.customer_pool)[bot_id] = bot
        for bot_id in to_remove:
            bot = self.customer_pool.pop(bot_id, None) or self.master_pool.pop(bot_id, None)
            if bot is not None:
                await bot.session.close()
        if to_add or to_remove:
            logger.info("webhook_reconciled", added=len(to_add), removed=len(to_remove))

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
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        platform = await ensure_platform_tenant(session)
        await ensure_master_bot(session)
        await ensure_platform_stars_provider(session)
        await ensure_base_strings(session)
        default_tenant_id = await get_default_tenant_id(session)
        await ensure_tenant_default_language(session, default_tenant_id)
        await ensure_tenant_default_language(session, platform.id, default_lang="ru")

    consumer = WebhookConsumer(
        customer_dp=create_dispatcher(),
        master_dp=create_master_dispatcher(),
        customer_pool={},
        master_pool={},
        sessionmaker=sessionmaker,
    )
    await consumer.reconcile()
    logger.info(
        "bot_runner_started",
        customer_bots=len(consumer.customer_pool),
        master_bots=len(consumer.master_pool),
    )

    async def _reload_loop() -> None:
        interval = get_settings().bot_reload_interval_seconds
        while True:
            try:
                async for _ in reload_signals(interval):
                    try:
                        await consumer.reconcile()
                    except Exception:
                        logger.exception("webhook_reconcile_failed")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("reload_signals_failed_retrying")
                await asyncio.sleep(interval)

    reload_task = asyncio.create_task(_reload_loop())
    reload_task.add_done_callback(
        lambda t: t.cancelled() or logger.error("reload_loop_stopped", exc=t.exception())
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
