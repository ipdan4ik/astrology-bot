from datetime import date, time
from decimal import Decimal

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.domain.blueprints import create_blueprint
from quantuum.domain.natal_profiles import upsert_natal_profile
from quantuum.bot.handlers.history import PAGE_SIZE, fetch_history_window


async def _acc(session, tenant_id):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="88")
    profile = await upsert_natal_profile(
        session, tenant_id=tenant_id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="M",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    return acc, profile


async def test_fetch_history_window_overfetches_for_has_next(session, default_tenant):
    acc, profile = await _acc(session, default_tenant.id)
    for _ in range(PAGE_SIZE + 2):
        await create_blueprint(
            session, tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id
        )
    window = await fetch_history_window(session, account_id=acc.id, page=0)
    assert len(window) == PAGE_SIZE + 1  # over-fetch by one


async def test_fetch_history_window_orders_desc(session, default_tenant):
    acc, profile = await _acc(session, default_tenant.id)
    first = await create_blueprint(
        session, tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id
    )
    second = await create_blueprint(
        session, tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id
    )
    window = await fetch_history_window(session, account_id=acc.id, page=0)
    assert window[0].id == second.id  # newest first
    assert window[1].id == first.id


async def test_history_open_rejects_other_account(session, default_tenant):
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers.history import on_open
    from quantuum.bot.ui.callbacks import HistoryCb
    from quantuum.domain.blueprints import create_blueprint, set_status

    owner, profile = await _acc(session, default_tenant.id)
    bp = await create_blueprint(
        session, tenant_id=default_tenant.id, account_id=owner.id, natal_profile_id=profile.id
    )
    await set_status(session, bp.id, "done", llm_md="SECRET-CONTENT")

    from quantuum.auth.identity import find_or_create_account_by_tg

    attacker = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="999"
    )
    query = AsyncMock()
    await on_open(query, HistoryCb(action="open", bp_id=bp.id), attacker)
    query.answer.assert_awaited_with("Не найдено", show_alert=True)
    query.message.answer.assert_not_called()


async def test_history_download_rejects_other_account(session, default_tenant):
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers.history import on_download
    from quantuum.bot.ui.callbacks import BlueprintCb
    from quantuum.domain.blueprints import create_blueprint, set_status

    owner, profile = await _acc(session, default_tenant.id)
    bp = await create_blueprint(
        session, tenant_id=default_tenant.id, account_id=owner.id, natal_profile_id=profile.id
    )
    await set_status(session, bp.id, "done", llm_md="SECRET-CONTENT")

    from quantuum.auth.identity import find_or_create_account_by_tg

    attacker = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="998"
    )
    query = AsyncMock()
    await on_download(query, BlueprintCb(action="download", bp_id=bp.id), attacker)
    query.answer.assert_awaited_with("Недоступно", show_alert=True)
    query.message.answer_document.assert_not_called()
