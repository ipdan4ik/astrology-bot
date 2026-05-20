from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.natal_profiles import get_natal_profile

router = Router()


@router.message(CommandStart())
async def on_start(message: Message, account: Account) -> None:
    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
    if profile is None:
        await message.answer(
            "Привет! Я построю твой астрологический разбор. "
            "Заполни профиль командой /profile."
        )
    else:
        await message.answer(
            "С возвращением! Команда /blueprint сгенерирует разбор по твоим данным, "
            "или /profile чтобы их изменить."
        )
