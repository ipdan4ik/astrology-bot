from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from quantuum.bot.handlers.menu import show_main_menu
from quantuum.i18n import Translator

router = Router()


@router.message(CommandStart())
async def on_start(message: Message, i18n: Translator) -> None:
    await message.answer(await i18n("start.welcome"))
    await show_main_menu(message, i18n)
