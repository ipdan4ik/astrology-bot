from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from quantuum.bot.handlers.menu import show_main_menu
from quantuum.bot.ui.keyboards import language_picker_kb
from quantuum.db.models import Account
from quantuum.i18n import Translator

router = Router()


@router.message(CommandStart())
async def on_start(
    message: Message, account: Account, tenant_id: int, i18n: Translator
) -> None:
    if account.preferred_lang is None:
        await message.answer(
            await i18n("lang.prompt"),
            reply_markup=await language_picker_kb(tenant_id, action="setup"),
        )
        return
    await message.answer(await i18n("start.welcome"))
    await show_main_menu(message, i18n)
