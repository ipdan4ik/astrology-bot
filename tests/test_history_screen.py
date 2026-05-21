from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.domain.blueprints import create_blueprint
from quantuum.domain.natal_profiles import upsert_natal_profile
from quantuum.bot.handlers.history import PAGE_SIZE, fetch_history_window

from .conftest import build_translator


def _patch_sessionmaker(monkeypatch, module, session):
    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(module, "get_sessionmaker", lambda: _Maker())


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
    from quantuum.bot.handlers.history import on_open
    from quantuum.bot.ui.callbacks import HistoryCb
    from quantuum.domain.blueprints import create_blueprint, set_status

    i18n = await build_translator(session, default_tenant.id)
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
    await on_open(query, HistoryCb(action="open", bp_id=bp.id), attacker, i18n)
    query.answer.assert_awaited_with("Не найдено", show_alert=True)
    query.message.answer.assert_not_called()


async def test_history_download_rejects_other_account(session, default_tenant):
    from quantuum.bot.handlers.history import on_download
    from quantuum.bot.ui.callbacks import BlueprintCb
    from quantuum.domain.blueprints import create_blueprint, set_status

    i18n = await build_translator(session, default_tenant.id)
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
    await on_download(query, BlueprintCb(action="download", bp_id=bp.id), attacker, i18n)
    query.answer.assert_awaited_with("Недоступно", show_alert=True)
    query.message.answer_document.assert_not_called()


async def test_history_list_empty_localised(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import history as hist

    _patch_sessionmaker(monkeypatch, hist, session)
    i18n = await build_translator(session, default_tenant.id)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="700"
    )
    msg = SimpleNamespace(answer=AsyncMock())
    await hist.show_history(msg, acc, i18n)
    text = msg.answer.await_args.args[0]
    assert text == "Пока нет генераций. Нажми «🔮 Разбор», чтобы создать первую."


async def test_history_list_shows_localised_title_and_labels(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import history as hist
    from quantuum.domain.blueprints import set_status

    _patch_sessionmaker(monkeypatch, hist, session)
    i18n = await build_translator(session, default_tenant.id)
    acc, profile = await _acc(session, default_tenant.id)
    bp = await create_blueprint(
        session, tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id
    )
    await set_status(session, bp.id, "done", llm_md="X")

    msg = SimpleNamespace(answer=AsyncMock())
    await hist.show_history(msg, acc, i18n)
    text = msg.answer.await_args.args[0]
    assert text == "📜 История генераций:"
    kb = msg.answer.await_args.kwargs["reply_markup"]
    label = kb.inline_keyboard[0][0].text
    assert "готов" in label


async def test_history_open_renders_localised_detail(session, default_tenant, monkeypatch):
    from quantuum.bot.handlers import history as hist
    from quantuum.bot.ui.callbacks import HistoryCb
    from quantuum.domain.blueprints import set_status

    _patch_sessionmaker(monkeypatch, hist, session)
    i18n = await build_translator(session, default_tenant.id)
    acc, profile = await _acc(session, default_tenant.id)
    bp = await create_blueprint(
        session, tenant_id=default_tenant.id, account_id=acc.id, natal_profile_id=profile.id
    )
    await set_status(session, bp.id, "done", llm_md="X")

    query = AsyncMock()
    await hist.on_open(query, HistoryCb(action="open", bp_id=bp.id), acc, i18n)
    detail = query.message.answer.await_args.args[0]
    assert f"🔮 Разбор #{bp.id}" in detail
    assert "Статус: готов" in detail
    kb = query.message.answer.await_args.kwargs["reply_markup"]
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert "📥 Скачать .md" in labels
    assert "← Назад" in labels
