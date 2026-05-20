from unittest.mock import AsyncMock, patch

from quantuum.bot import polling


async def test_run_calls_delete_webhook_and_start_polling():
    bot = AsyncMock()
    customer_pool = {1: bot}
    master_pool = {}
    dp = AsyncMock()
    master_dp = AsyncMock()

    with (
        patch("quantuum.bot.polling.get_sessionmaker"),
        patch("quantuum.bot.polling.ensure_default_tenant"),
        patch("quantuum.bot.polling.ensure_default_tenant_bot"),
        patch("quantuum.bot.polling.ensure_platform_tenant"),
        patch("quantuum.bot.polling.ensure_master_bot"),
        patch("quantuum.bot.polling.list_active_tenant_bots", return_value=[]),
        patch(
            "quantuum.bot.polling.split_by_platform",
            new=AsyncMock(return_value=([], [])),
        ),
        patch(
            "quantuum.bot.polling.build_bots",
            side_effect=[customer_pool, master_pool],
        ),
        patch("quantuum.bot.polling.create_dispatcher", return_value=dp),
        patch("quantuum.bot.polling.create_master_dispatcher", return_value=master_dp),
        patch("quantuum.bot.polling.configure_logging"),
    ):
        await polling.run()

    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=True)
    dp.start_polling.assert_awaited_once_with(bot, handle_signals=False)
    master_dp.start_polling.assert_not_awaited()


async def test_split_polling_rows_by_platform(session, monkeypatch):
    from quantuum.bot.polling import split_by_platform
    from quantuum.db.models import Tenant, TenantBot

    platform = Tenant(slug="platform", display_name="P", is_platform=True)
    customer = Tenant(slug="cust", display_name="C")
    session.add(platform)
    session.add(customer)
    await session.flush()
    master = TenantBot(tenant_id=platform.id, bot_telegram_id=1, bot_token_enc=b"e", webhook_secret_path="m1")
    cust = TenantBot(tenant_id=customer.id, bot_telegram_id=2, bot_token_enc=b"e", webhook_secret_path="c1")
    session.add(master)
    session.add(cust)
    await session.commit()

    master_rows, customer_rows = await split_by_platform(session, [master, cust])
    assert [r.bot_telegram_id for r in master_rows] == [1]
    assert [r.bot_telegram_id for r in customer_rows] == [2]
