from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from quantuum.bot.handlers.generate import _buy_offer_kb
from quantuum.bot.ui.callbacks import ReadingCb
from quantuum.bot.ui.keyboards import readings_menu_kb
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.quota import consume_quota
from quantuum.domain.readings import create_reading
from quantuum.domain.requests import create_request
from quantuum.i18n import Translator
from quantuum.tasks.enqueue import enqueue_reading

router = Router()


async def show_readings_menu(message: Message, i18n: Translator) -> None:
    await message.answer(
        await i18n("readings.menu.title"),
        reply_markup=await readings_menu_kb(i18n),
    )


@router.callback_query(ReadingCb.filter(F.action == "generate"))
async def on_reading_choice(
    query: CallbackQuery, account: Account, i18n: Translator
) -> None:
    kind = ReadingCb.unpack(query.data).kind

    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
        if profile is None:
            await query.message.answer(await i18n("readings.no_profile"))
            await query.answer()
            return
        try:
            charged = await consume_quota(session, account.id, "reading", cost_units=1)
        except InsufficientFundsError:
            await query.message.answer(
                await i18n("readings.no_quota"),
                reply_markup=await _buy_offer_kb(i18n),
            )
            await query.answer()
            return
        reading = await create_reading(
            session,
            tenant_id=account.tenant_id,
            account_id=account.id,
            natal_profile_id=profile.id,
            kind=kind,
            lang=i18n.lang,
        )
        request = await create_request(
            session,
            tenant_id=account.tenant_id,
            account_id=account.id,
            kind="reading",
            charged_against=charged,
        )

    await enqueue_reading(reading.id, query.message.chat.id, request.id)
    await query.message.answer(await i18n("readings.queued"))
    await query.answer()
