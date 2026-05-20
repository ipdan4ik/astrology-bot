from unittest.mock import AsyncMock, patch

from quantuum.bot import polling


async def test_run_calls_delete_webhook_and_start_polling():
    bot = AsyncMock()
    pool = {1: bot}
    dp = AsyncMock()

    with (
        patch("quantuum.bot.polling.get_sessionmaker"),
        patch("quantuum.bot.polling.ensure_default_tenant"),
        patch("quantuum.bot.polling.ensure_default_tenant_bot"),
        patch("quantuum.bot.polling.ensure_platform_tenant"),
        patch("quantuum.bot.polling.ensure_master_bot"),
        patch("quantuum.bot.polling.list_active_tenant_bots", return_value=[]),
        patch("quantuum.bot.polling.build_bots", return_value=pool),
        patch("quantuum.bot.polling.create_dispatcher", return_value=dp),
        patch("quantuum.bot.polling.configure_logging"),
    ):
        await polling.run()

    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=True)
    dp.start_polling.assert_awaited_once_with(bot)
