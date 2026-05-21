from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.ui.callbacks import BuyCb
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.plans import list_package_plans, list_subscription_plans

router = Router()


async def build_buy_menu(session, *, tenant_id: int) -> tuple[str, InlineKeyboardMarkup]:
    subs = await list_subscription_plans(session, tenant_id=tenant_id)
    pkgs = await list_package_plans(session, tenant_id=tenant_id)
    builder = InlineKeyboardBuilder()
    for s in subs:
        builder.button(
            text=f"⭐ {s.name} — {s.price_cents}★",
            callback_data=BuyCb(action="pick", kind="subscription", plan_id=s.id),
        )
    for p in pkgs:
        builder.button(
            text=f"⭐ {p.name} · {p.request_count} разборов — {p.price_cents}★",
            callback_data=BuyCb(action="pick", kind="package", plan_id=p.id),
        )
    builder.adjust(1)
    text = "Выбери, что купить (оплата звёздами Telegram ★):"
    return text, builder.as_markup()


async def show_buy_menu(message: Message, tenant_id: int) -> None:
    async with get_sessionmaker()() as session:
        text, kb = await build_buy_menu(session, tenant_id=tenant_id)
    if not kb.inline_keyboard:
        await message.answer("Пока нет доступных планов. Загляни позже.")
        return
    await message.answer(text, reply_markup=kb)


@router.message(Command("buy"))
async def on_buy_command(message: Message, account: Account) -> None:
    await show_buy_menu(message, account.tenant_id)


@router.callback_query(BuyCb.filter(F.action == "open"))
async def on_buy_open(query: CallbackQuery, account: Account) -> None:
    await show_buy_menu(query.message, account.tenant_id)
    await query.answer()
