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

router = Router()

LABELS = {text.BTN_GENERATE, text.BTN_PROFILE, text.BTN_HISTORY, text.BTN_HELP}


async def show_main_menu(message: Message) -> None:
    await message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.message(F.text == text.BTN_GENERATE)
async def on_generate_btn(message: Message, account: Account, chat_id: int) -> None:
    await run_generate(message, account, chat_id)


@router.message(F.text == text.BTN_PROFILE)
async def on_profile_btn(message: Message, account: Account) -> None:
    await show_profile(message, account)


@router.message(F.text == text.BTN_HISTORY)
async def on_history_btn(message: Message, account: Account) -> None:
    await show_history(message, account, page=0)


@router.message(F.text == text.BTN_HELP)
async def on_help_btn(message: Message) -> None:
    await message.answer(text.HELP_TEXT, reply_markup=main_menu_kb())


@router.callback_query(OnboardCb.filter(F.action == "cancel"))
async def on_cancel(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await query.message.answer("Отменено.", reply_markup=main_menu_kb())
    await query.answer()
