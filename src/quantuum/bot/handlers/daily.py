from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.handlers.generate import _buy_offer_kb
from quantuum.bot.ui.keyboards import profile_kb
from quantuum.bot.ui.callbacks import DailyCb
from quantuum.db.models import Account, DailySubscription
from quantuum.db.session import get_sessionmaker
from quantuum.domain.daily import get_settings, is_subscriber, upsert_settings
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.tenant_features import is_feature_enabled
from quantuum.i18n import Translator
from quantuum.logging_setup import get_logger

router = Router()
_log = get_logger("tenant_features.gate")


async def _safe_edit(query: CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    """Edit the message in place, ignoring Telegram's "not modified" when the view is unchanged
    (e.g. the user re-taps the already-selected hour)."""
    try:
        await query.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


async def _daily_view(
    i18n: Translator, settings: DailySubscription | None
) -> tuple[str, InlineKeyboardMarkup]:
    enabled = settings.enabled if settings else False
    hour = settings.send_hour if settings else 9
    text = await i18n("daily.status_on", hour=hour) if enabled else await i18n("daily.status_off")
    b = InlineKeyboardBuilder()
    toggle_key = "daily.kb.turn_off" if enabled else "daily.kb.turn_on"
    b.button(text=await i18n(toggle_key), callback_data=DailyCb(action="toggle"))
    for h in range(24):
        label = f"·{h}·" if h == hour else str(h)
        b.button(text=label, callback_data=DailyCb(action="set_hour", value=h))
    b.button(text=await i18n("daily.kb.close"), callback_data=DailyCb(action="close"))
    b.adjust(1, 6, 6, 6, 6, 1)
    return text, b.as_markup()


async def run_daily_settings(message: Message, account: Account, i18n: Translator) -> None:
    # Feature gate — before any DB read.
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, account.tenant_id, "daily"):
            _log.info(
                "feature.gate_blocked",
                tenant_id=account.tenant_id,
                account_id=account.id,
                key="daily",
                surface="daily.run_daily_settings",
            )
            await message.answer(await i18n("feature.disabled_generic"))
            return

    async with get_sessionmaker()() as session:
        if not await is_subscriber(session, account.id):
            await message.answer(
                await i18n("daily.not_subscriber"), reply_markup=await _buy_offer_kb(i18n)
            )
            return
        profile = await get_natal_profile(session, account.id)
        if profile is None:
            await message.answer(
                await i18n("daily.no_profile"),
                reply_markup=await profile_kb(has_profile=False, i18n=i18n),
            )
            return
        settings = await get_settings(session, account.id)
    text, kb = await _daily_view(i18n, settings)
    await message.answer(text, reply_markup=kb)


@router.message(Command("daily"))
async def on_daily(message: Message, account: Account, i18n: Translator) -> None:
    await run_daily_settings(message, account, i18n)


@router.callback_query(DailyCb.filter(F.action == "toggle"))
async def on_daily_toggle(query: CallbackQuery, account: Account, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if not await is_subscriber(session, account.id):
            await query.answer(await i18n("daily.not_subscriber"), show_alert=True)
            return
        current = await get_settings(session, account.id)
        new_enabled = not (current.enabled if current else False)
        hour = current.send_hour if current else 9
        settings = await upsert_settings(
            session, tenant_id=account.tenant_id, account_id=account.id,
            enabled=new_enabled, send_hour=hour,
        )
    text, kb = await _daily_view(i18n, settings)
    await _safe_edit(query, text, kb)
    await query.answer(await i18n("daily.enabled" if new_enabled else "daily.disabled"))


@router.callback_query(DailyCb.filter(F.action == "set_hour"))
async def on_daily_set_hour(
    query: CallbackQuery, callback_data: DailyCb, account: Account, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        if not await is_subscriber(session, account.id):
            await query.answer(await i18n("daily.not_subscriber"), show_alert=True)
            return
        current = await get_settings(session, account.id)
        enabled = current.enabled if current else False
        settings = await upsert_settings(
            session, tenant_id=account.tenant_id, account_id=account.id,
            enabled=enabled, send_hour=callback_data.value,
        )
    text, kb = await _daily_view(i18n, settings)
    await _safe_edit(query, text, kb)
    await query.answer(await i18n("daily.hour_set", hour=callback_data.value))


@router.callback_query(DailyCb.filter(F.action == "close"))
async def on_daily_close(query: CallbackQuery, i18n: Translator) -> None:
    await query.message.delete()
    await query.answer()
