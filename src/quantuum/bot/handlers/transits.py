from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from quantuum.bot.handlers.generate import _buy_offer_kb
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.quota import consume_quota
from quantuum.domain.requests import create_request
from quantuum.domain.tenant_features import is_feature_enabled
from quantuum.domain.transits import create_transit
from quantuum.i18n import Translator
from quantuum.logging_setup import get_logger
from quantuum.tasks.enqueue import enqueue_transit

router = Router()
_log = get_logger("tenant_features.gate")


async def run_transits(
    message: Message, raw_arg: str | None, account: Account, i18n: Translator
) -> None:
    # Feature gate — before any DB read or quota charge.
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, account.tenant_id, "transits"):
            _log.info(
                "feature.gate_blocked",
                tenant_id=account.tenant_id,
                account_id=account.id,
                key="transits",
                surface="transits.run_transits",
            )
            await message.answer(await i18n("feature.disabled_generic"))
            return

    # raw_arg ("30", None, or junk) is normalized + clamped inside create_transit.
    window = raw_arg.strip() if raw_arg and raw_arg.strip() else None
    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
        if profile is None:
            await message.answer(await i18n("transit.no_profile"))
            return
        try:
            charged = await consume_quota(session, account.id, "transit")
        except InsufficientFundsError:
            await message.answer(
                await i18n("transit.no_quota"), reply_markup=await _buy_offer_kb(i18n)
            )
            return
        request = await create_request(
            session,
            tenant_id=account.tenant_id,
            account_id=account.id,
            kind="transit",
            charged_against=charged,
        )
        report = await create_transit(
            session,
            tenant_id=account.tenant_id,
            account_id=account.id,
            natal_profile_id=profile.id,
            window_days=window,
            lang=i18n.lang,
        )
    await enqueue_transit(report.id, message.chat.id, request.id)
    await message.answer(await i18n("transit.thinking"))


@router.message(Command("transits"))
async def on_transits(
    message: Message, command: CommandObject, account: Account, i18n: Translator
) -> None:
    await run_transits(message, command.args, account, i18n)
