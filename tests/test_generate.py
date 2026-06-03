from datetime import date, time
from decimal import Decimal
from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.generate import request_blueprint_for_account
from quantuum.domain.natal_profiles import upsert_natal_profile


async def test_request_blueprint_no_profile(session, default_tenant):
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="1")
    enqueue = AsyncMock()
    status, blueprint_id = await request_blueprint_for_account(
        session, account=acc, chat_id=10, enqueue=enqueue
    )
    assert status == "no_profile"
    enqueue.assert_not_awaited()


async def test_request_blueprint_trial(session, default_tenant):
    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="2")
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    enqueue = AsyncMock()
    status, blueprint_id = await request_blueprint_for_account(
        session, account=acc, chat_id=10, enqueue=enqueue
    )
    assert status == "queued"
    enqueue.assert_awaited_once()
    call_args = enqueue.await_args.args
    assert call_args[0] == blueprint_id
    assert call_args[1] == 10
    assert isinstance(call_args[2], int)  # request_id threaded through


async def test_request_blueprint_no_quota(session, default_tenant):
    from quantuum.db.models import AccountBalance

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="3")
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    # zero out welcome credits so there is only one attempt possible before quota runs out
    bal = await session.get(AccountBalance, acc.id)
    bal.package_credits = 0
    session.add(bal)
    await session.commit()
    enqueue = AsyncMock()
    await request_blueprint_for_account(session, account=acc, chat_id=10, enqueue=enqueue)
    status, _ = await request_blueprint_for_account(
        session, account=acc, chat_id=10, enqueue=enqueue
    )
    assert status == "no_quota"


async def test_blueprint_enqueue_failure_refunds_and_reports(session, default_tenant):
    from quantuum.db.models import AccountBalance

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="4")
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    bal = await session.get(AccountBalance, acc.id)
    starting = bal.package_credits  # 10 welcome credits

    async def boom(_bid, _chat, _req):
        raise RuntimeError("redis down")

    status, blueprint_id = await request_blueprint_for_account(
        session, account=acc, chat_id=123, enqueue=boom, lang="en"
    )
    assert status == "queue_failed"
    assert blueprint_id is None

    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.package_credits == starting  # refunded
