from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.ui.callbacks import BuyCb
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.billing import fulfill_payment, record_pending_payment
from quantuum.domain.plans import (
    get_package_plan,
    get_subscription_plan,
    list_package_plans,
    list_subscription_plans,
)
from quantuum.domain.providers import ensure_stars_provider

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


def _invoice_description(kind: str, plan) -> str:
    if kind == "subscription":
        return f"Подписка на {plan.period_days} дней"
    return f"Пакет: {plan.request_count} разборов"


@router.callback_query(BuyCb.filter(F.action == "pick"))
async def on_buy_pick(
    query: CallbackQuery, callback_data: BuyCb, bot: Bot, account: Account
) -> None:
    chat_id = query.message.chat.id
    async with get_sessionmaker()() as session:
        if callback_data.kind == "subscription":
            plan = await get_subscription_plan(session, callback_data.plan_id)
        else:
            plan = await get_package_plan(session, callback_data.plan_id)
        if plan is None:
            await query.answer("Этот план больше недоступен.", show_alert=True)
            return
        provider = await ensure_stars_provider(session, account.tenant_id)
        payment = await record_pending_payment(
            session,
            tenant_id=account.tenant_id,
            account_id=account.id,
            provider_id=provider.id,
            amount_cents=plan.price_cents,
            currency="XTR",
            metadata={"kind": callback_data.kind, "plan_id": plan.id},
        )
    await bot.send_invoice(
        chat_id=chat_id,
        title=plan.name,
        description=_invoice_description(callback_data.kind, plan),
        payload=str(payment.id),
        currency="XTR",
        prices=[LabeledPrice(label=plan.name, amount=plan.price_cents)],
    )
    await query.answer()


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    # Stars: nothing to reserve server-side; accept so Telegram charges the user.
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    sp = message.successful_payment
    payment_id = int(sp.invoice_payload)
    async with get_sessionmaker()() as session:
        credited = await fulfill_payment(
            session, payment_id=payment_id, external_id=sp.telegram_payment_charge_id
        )
    if credited:
        await message.answer("Оплата получена! Доступ активирован. ✨")
    else:
        await message.answer("Эта оплата уже была учтена ранее.")
