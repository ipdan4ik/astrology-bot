from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlmodel import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.ui.callbacks import LangCb
from quantuum.db.models import Account

from .conftest import build_translator


def _fake_query():
    msg = SimpleNamespace(answer=AsyncMock())
    return SimpleNamespace(message=msg, answer=AsyncMock()), msg


async def test_set_language_persists_and_welcomes(session, default_tenant):
    from quantuum.bot.handlers import language

    i18n = await build_translator(session, default_tenant.id)  # ru
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="900"
    )
    query, msg = _fake_query()

    await language.on_set_language(
        query, LangCb(action="setup", lang="en"), acc, i18n
    )

    # Persisted to the DB
    row = (
        await session.execute(select(Account).where(Account.id == acc.id))
    ).scalar_one()
    await session.refresh(row)
    assert row.preferred_lang == "en"

    # setup → English welcome, then the menu
    assert msg.answer.await_args_list[0].args[0] == "Hello! I will build your astrological reading ✨"
    assert query.answer.await_count == 1


async def test_set_language_menu_change_confirms(session, default_tenant):
    from quantuum.bot.handlers import language

    i18n = await build_translator(session, default_tenant.id)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="901"
    )
    query, msg = _fake_query()

    await language.on_set_language(
        query, LangCb(action="set", lang="en"), acc, i18n
    )

    # "set" → confirmation text (English), not the welcome
    assert msg.answer.await_args_list[0].args[0] == "Language updated."
