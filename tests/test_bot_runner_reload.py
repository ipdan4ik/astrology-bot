from quantuum.bot.runner import WebhookConsumer
from quantuum.common.crypto import encrypt_token
from quantuum.db.models import Tenant, TenantBot

_TOKEN = "222222:CCDDeeFF-gghh_iijj"


async def _add_webhook_bot(session, tenant_id, bot_tg_id, status="active"):
    session.add(
        TenantBot(
            tenant_id=tenant_id,
            bot_telegram_id=bot_tg_id,
            bot_token_enc=encrypt_token(_TOKEN),
            transport="webhook",
            webhook_secret_path=f"wh-{bot_tg_id}",
            status=status,
        )
    )
    await session.commit()


def _maker(session):
    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *a):
            return False

    return _Maker()


async def test_webhook_reconcile_adds_then_removes(session, default_tenant):
    platform = Tenant(slug="platform", display_name="Platform", is_platform=True)
    session.add(platform)
    await session.commit()
    await session.refresh(platform)

    consumer = WebhookConsumer(
        customer_dp=None, master_dp=None,
        customer_pool={}, master_pool={},
        sessionmaker=_maker(session),
    )

    await _add_webhook_bot(session, default_tenant.id, 3001)  # customer
    await _add_webhook_bot(session, platform.id, 4002)  # master
    await consumer.reconcile()

    assert set(consumer.customer_pool) == {3001}
    assert set(consumer.master_pool) == {4002}

    # Deactivate the customer bot; reconcile drops it.
    tb = (await session.execute(
        __import__("sqlmodel").select(TenantBot).where(TenantBot.bot_telegram_id == 3001)
    )).scalar_one()
    tb.status = "paused"
    await session.commit()
    await consumer.reconcile()

    assert set(consumer.customer_pool) == set()
    assert set(consumer.master_pool) == {4002}
