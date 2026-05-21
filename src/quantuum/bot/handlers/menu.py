from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from quantuum.bot.handlers.generate import run_generate
from quantuum.bot.handlers.history import show_history
from quantuum.bot.handlers.profile import show_profile
from quantuum.bot.ui import text
from quantuum.bot.ui.callbacks import OnboardCb
from quantuum.bot.ui.keyboards import main_menu_kb
from quantuum.db.models import Account
from quantuum.i18n import Translator

router = Router()

# Reply-menu button labels across every enabled language, so a button pressed
# in any language routes to the right handler.
_GENERATE_LABELS = text.menu_button_labels("btn.generate")
_PROFILE_LABELS = text.menu_button_labels("btn.profile")
_HISTORY_LABELS = text.menu_button_labels("btn.history")
_HELP_LABELS = text.menu_button_labels("btn.help")
LABELS = text.all_menu_labels()


async def show_main_menu(message: Message, i18n: Translator) -> None:
    await message.answer(await i18n("menu.title"), reply_markup=await main_menu_kb(i18n))


@router.message(F.text.in_(_GENERATE_LABELS))
async def on_generate_btn(message: Message, account: Account, chat_id: int) -> None:
    await run_generate(message, account, chat_id)


@router.message(F.text.in_(_PROFILE_LABELS))
async def on_profile_btn(message: Message, account: Account, i18n: Translator) -> None:
    await show_profile(message, account, i18n)


@router.message(F.text.in_(_HISTORY_LABELS))
async def on_history_btn(message: Message, account: Account) -> None:
    await show_history(message, account, page=0)


@router.message(F.text.in_(_HELP_LABELS))
async def on_help_btn(message: Message, i18n: Translator) -> None:
    await message.answer(await i18n("help.text"), reply_markup=await main_menu_kb(i18n))


@router.callback_query(OnboardCb.filter(F.action == "cancel"))
async def on_cancel(query: CallbackQuery, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await query.message.answer(
        await i18n("menu.cancelled"), reply_markup=await main_menu_kb(i18n)
    )
    await query.answer()
