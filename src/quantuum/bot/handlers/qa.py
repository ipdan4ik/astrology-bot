from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from quantuum.bot.handlers.generate import _buy_offer_kb
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.qa import create_qa
from quantuum.domain.quota import consume_quota
from quantuum.domain.requests import create_request
from quantuum.i18n import Translator
from quantuum.tasks.enqueue import enqueue_qa

router = Router()

MAX_QUESTION_LEN = 1000


class Ask(StatesGroup):
    awaiting_question = State()


async def start_ask(message: Message, state: FSMContext, i18n: Translator) -> None:
    """Begin the ask flow: wait for the user's free-text question."""
    await state.set_state(Ask.awaiting_question)
    await message.answer(await i18n("qa.ask_prompt"))


async def _submit(message: Message, raw: str, account: Account, i18n: Translator) -> None:
    q = (raw or "").strip()
    if not q:
        await message.answer(await i18n("qa.empty"))
        return
    if len(q) > MAX_QUESTION_LEN:
        await message.answer(await i18n("qa.too_long"))
        return

    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
        if profile is None:
            await message.answer(await i18n("qa.no_profile"))
            return
        try:
            charged = await consume_quota(session, account.id, "qa")
        except InsufficientFundsError:
            await message.answer(
                await i18n("qa.no_quota"), reply_markup=await _buy_offer_kb(i18n)
            )
            return
        request = await create_request(
            session,
            tenant_id=account.tenant_id,
            account_id=account.id,
            kind="qa",
            charged_against=charged,
        )
        qa = await create_qa(
            session,
            tenant_id=account.tenant_id,
            account_id=account.id,
            natal_profile_id=profile.id,
            question=q,
            lang=i18n.lang,
        )

    await enqueue_qa(qa.id, message.chat.id, request.id)
    await message.answer(await i18n("qa.thinking"))


@router.message(Command("ask"))
async def on_ask(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    account: Account,
    i18n: Translator,
) -> None:
    if command.args and command.args.strip():
        await _submit(message, command.args, account, i18n)
    else:
        await start_ask(message, state, i18n)


@router.message(Ask.awaiting_question)
async def on_ask_question(
    message: Message, state: FSMContext, account: Account, i18n: Translator
) -> None:
    await state.clear()
    await _submit(message, message.text or "", account, i18n)
