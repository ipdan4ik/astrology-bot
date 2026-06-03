from collections.abc import Awaitable, Callable

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.handlers._guard import enqueue_or_refund
from quantuum.bot.ui.callbacks import BuyCb
from quantuum.bot.ui.keyboards import profile_kb
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.blueprints import create_blueprint
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.quota import consume_quota
from quantuum.domain.requests import create_request
from quantuum.domain.tenant_features import is_feature_enabled
from quantuum.i18n import Translator
from quantuum.logging_setup import get_logger
from quantuum.tasks.enqueue import enqueue_blueprint

router = Router()
_log = get_logger("tenant_features.gate")


async def _buy_offer_kb(i18n: Translator):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=await i18n("buy.kb.open"), callback_data=BuyCb(action="open").pack()
        )
    )
    return builder.as_markup()


async def request_blueprint_for_account(
    session,
    *,
    account: Account,
    chat_id: int,
    enqueue: Callable[[int, int | None, int | None], Awaitable[None]],
    lang: str | None = None,
) -> tuple[str, int | None]:
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        return "no_profile", None
    try:
        charged = await consume_quota(session, account.id, "blueprint")
    except InsufficientFundsError:
        return "no_quota", None

    blueprint = await create_blueprint(
        session, tenant_id=account.tenant_id, account_id=account.id, natal_profile_id=profile.id,
        lang=lang,
    )
    request = await create_request(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        kind="blueprint",
        charged_against=charged,
    )
    if not await enqueue_or_refund(
        enqueue(blueprint.id, chat_id, request.id), request_id=request.id
    ):
        return "queue_failed", None
    return "queued", blueprint.id


async def run_generate(
    message: Message, account: Account, chat_id: int, i18n: Translator
) -> None:
    # Feature gate — before any DB read or quota charge.
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, account.tenant_id, "blueprint"):
            _log.info(
                "feature.gate_blocked",
                tenant_id=account.tenant_id,
                account_id=account.id,
                key="blueprint",
                surface="generate.run_generate",
            )
            await message.answer(await i18n("feature.disabled_generic"))
            return

    async with get_sessionmaker()() as session:
        status, _ = await request_blueprint_for_account(
            session, account=account, chat_id=chat_id, enqueue=enqueue_blueprint, lang=i18n.lang
        )
    if status == "no_profile":
        await message.answer(
            await i18n("generate.no_profile"),
            reply_markup=await profile_kb(has_profile=False, i18n=i18n),
        )
    elif status == "no_quota":
        await message.answer(
            await i18n("generate.no_quota"),
            reply_markup=await _buy_offer_kb(i18n),
        )
    elif status == "queue_failed":
        await message.answer(await i18n("errors.queue_failed"))
    else:
        await message.answer(await i18n("generate.queued"))


@router.message(Command("blueprint"))
async def on_blueprint(
    message: Message, account: Account, chat_id: int, i18n: Translator
) -> None:
    await run_generate(message, account, chat_id, i18n)
