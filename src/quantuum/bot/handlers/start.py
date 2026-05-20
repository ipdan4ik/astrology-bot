from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from quantuum.bot.handlers.menu import show_main_menu

router = Router()


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer("Привет! Я построю твой астрологический разбор ✨")
    await show_main_menu(message)
