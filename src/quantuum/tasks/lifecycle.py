from quantuum.bot.botpool import build_bots_by_tenant
from quantuum.domain.lifecycle import (
    due_renewal_reminders,
    mark_reminder_sent,
    sweep_subscriptions,
)
from quantuum.domain.tenants import list_active_tenant_bots
from quantuum.logging_setup import get_logger

logger = get_logger("tasks.lifecycle")

_REMINDER_TEXT = (
    "Твоя подписка скоро закончится. Продли её, чтобы не потерять доступ — "
    "нажми кнопку ниже и оплати звёздами Telegram ★."
)


def _renew_kb():
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    from quantuum.bot.ui.callbacks import BuyCb

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Продлить", callback_data=BuyCb(action="open").pack())
    )
    return builder.as_markup()


async def subscription_lifecycle(ctx) -> None:
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        counts = await sweep_subscriptions(session)
        due = await due_renewal_reminders(session)
        rows = await list_active_tenant_bots(session)
    logger.info("lifecycle_swept", **counts, due_reminders=len(due))
    if not due:
        return

    bots = build_bots_by_tenant(rows)
    kb = _renew_kb()
    try:
        for item in due:
            bot = bots.get(item.tenant_id)
            if bot is None or item.chat_id is None:
                continue
            try:
                await bot.send_message(int(item.chat_id), _REMINDER_TEXT, reply_markup=kb)
            except Exception:
                logger.exception("reminder_delivery_failed", sub_id=item.sub_id)
                continue
            async with sessionmaker() as session:
                await mark_reminder_sent(session, item.sub_id)
    finally:
        for bot in bots.values():
            await bot.session.close()
