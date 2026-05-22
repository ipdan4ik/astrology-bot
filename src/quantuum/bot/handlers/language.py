from aiogram import Router
from aiogram.types import CallbackQuery

from quantuum.bot.handlers.menu import show_main_menu
from quantuum.bot.ui.callbacks import LangCb
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.i18n import Translator

router = Router()


@router.callback_query(LangCb.filter())
async def on_set_language(
    query: CallbackQuery, callback_data: LangCb, account: Account, i18n: Translator
) -> None:
    lang = callback_data.lang
    # Persist on a fresh session — the middleware-injected `account` is detached.
    async with get_sessionmaker()() as session:
        acc = await session.get(Account, account.id)
        if acc is not None:
            acc.preferred_lang = lang
            await session.commit()
    # The injected i18n still carries the old language; build one for the new lang.
    new_i18n = Translator(tenant_id=account.tenant_id, lang=lang)
    if callback_data.action == "setup":
        await query.message.answer(await new_i18n("start.welcome"))
    else:
        await query.message.answer(await new_i18n("lang.changed"))
    await show_main_menu(query.message, new_i18n)
    await query.answer()
