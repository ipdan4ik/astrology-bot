from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.auth.identity import find_superadmin_by_tg
from quantuum.bot.ui.callbacks import SuperAdminCb
from quantuum.db.session import get_sessionmaker
from quantuum.i18n import Translator

router = Router()


async def _menu_kb(i18n: Translator):
    b = InlineKeyboardBuilder()
    b.button(text=await i18n("admin.menu.kb.tenants"), callback_data=SuperAdminCb(action="tenants"))
    b.button(text=await i18n("admin.menu.kb.invites"), callback_data=SuperAdminCb(action="invites"))
    b.adjust(2)
    return b.as_markup()


@router.message(Command("admin"))
async def on_admin(message: Message, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(message.from_user.id))
    if sa is None:
        await message.answer(await i18n("admin.denied"))
        return
    await message.answer(await i18n("admin.menu.title"), reply_markup=await _menu_kb(i18n))
