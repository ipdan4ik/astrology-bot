from urllib.parse import quote

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from quantuum.bot.ui import text
from quantuum.bot.ui.callbacks import GiftCreateCb
from quantuum.db.models import Account, AccountBalance, TenantBot
from quantuum.db.session import get_sessionmaker
from quantuum.domain.gifts import (
    InsufficientCreditsError,
    MAX_GIFT_AMOUNT,
    MIN_GIFT_AMOUNT,
    create_gift,
    list_recent_gifts,
    sweep_expired_gifts,
)
from quantuum.domain.tenant_features import is_feature_enabled
from quantuum.i18n import Translator

router = Router()

_GIFT_LABELS = text.menu_button_labels("btn.gift")


class Gift(StatesGroup):
    awaiting_amount = State()


async def _tenant_bot_username(session, tenant_id: int) -> str | None:
    row = (
        await session.execute(select(TenantBot).where(TenantBot.tenant_id == tenant_id))
    ).scalars().first()
    return row.bot_username if row else None


async def _render_history_lines(session, *, account_id: int, i18n: Translator) -> list[str]:
    rows = await list_recent_gifts(session, sender_account_id=account_id)
    if not rows:
        return [await i18n("gift.history_empty")]
    out: list[str] = []
    for r in rows:
        status_label = await i18n(f"gift.status.{r.status}", default=r.status)
        out.append(await i18n(
            "gift.history_row",
            date=r.created_at.strftime("%d.%m"),
            amount=r.amount,
            status=status_label,
        ))
    return out


async def show_gift_screen(
    message: Message, *, account_id: int, tenant_id: int, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, tenant_id, "gifts"):
            await message.answer(await i18n("gift.disabled"))
            return

        await sweep_expired_gifts(session, sender_account_id=account_id)
        bal = await session.get(AccountBalance, account_id)
        balance = bal.package_credits if bal else 0
        history_lines = await _render_history_lines(
            session, account_id=account_id, i18n=i18n
        )
        await session.commit()

    body_parts = [
        await i18n("gift.title"),
        "",
        await i18n("gift.balance_line", balance=balance),
        "",
        await i18n("gift.history_title"),
        *history_lines,
    ]
    builder = InlineKeyboardBuilder()
    builder.button(
        text=await i18n("gift.btn.create_new"),
        callback_data=GiftCreateCb(action="start").pack(),
    )
    builder.adjust(1)
    await message.answer("\n".join(body_parts), reply_markup=builder.as_markup())


@router.message(Command("gift"))
async def on_gift_cmd(
    message: Message, account: Account, tenant_id: int, i18n: Translator
) -> None:
    await show_gift_screen(
        message, account_id=account.id, tenant_id=tenant_id, i18n=i18n
    )


@router.message(F.text.in_(_GIFT_LABELS))
async def on_gift_btn(
    message: Message, account: Account, tenant_id: int, i18n: Translator
) -> None:
    await show_gift_screen(
        message, account_id=account.id, tenant_id=tenant_id, i18n=i18n
    )


@router.callback_query(GiftCreateCb.filter(F.action == "start"))
async def on_gift_create(
    query: CallbackQuery,
    callback_data: GiftCreateCb,
    state: FSMContext,
    account: Account,
    tenant_id: int,
    i18n: Translator,
) -> None:
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, tenant_id, "gifts"):
            await query.answer(await i18n("gift.disabled"), show_alert=True)
            return
        bal = await session.get(AccountBalance, account.id)
        balance = bal.package_credits if bal else 0
    if balance < MIN_GIFT_AMOUNT:
        await query.message.answer(await i18n("gift.no_balance"))
        await query.answer()
        return
    max_amount = min(balance, MAX_GIFT_AMOUNT)
    await state.set_state(Gift.awaiting_amount)
    await state.update_data(
        account_id=account.id, tenant_id=tenant_id, max_amount=max_amount
    )
    await query.message.answer(
        await i18n("gift.amount_prompt", max=max_amount)
        + "\n"
        + await i18n("gift.cancel_hint")
    )
    await query.answer()


@router.message(Command("cancel"), Gift.awaiting_amount)
async def on_gift_cancel(
    message: Message, state: FSMContext, i18n: Translator
) -> None:
    await state.clear()
    await message.answer(await i18n("gift.cancel_hint"))


@router.message(Gift.awaiting_amount)
async def on_amount_received(
    message: Message,
    state: FSMContext,
    account: Account,
    tenant_id: int,
    i18n: Translator,
) -> None:
    data = await state.get_data()
    raw = (message.text or "").strip()
    try:
        amount = int(raw)
    except ValueError:
        await message.answer(await i18n("gift.not_a_number"))
        return

    if amount < MIN_GIFT_AMOUNT:
        await message.answer(await i18n("gift.too_small"))
        return
    max_amount = data.get("max_amount", MAX_GIFT_AMOUNT)
    if amount > max_amount:
        await message.answer(await i18n("gift.too_large", max=max_amount))
        return

    async with get_sessionmaker()() as session:
        try:
            token = await create_gift(
                session,
                sender_account_id=account.id,
                tenant_id=tenant_id,
                amount=amount,
            )
        except InsufficientCreditsError:
            await session.rollback()
            await message.answer(await i18n("gift.no_balance"))
            await state.clear()
            return
        username = await _tenant_bot_username(session, tenant_id)
        await session.commit()

    if not username:
        await message.answer(await i18n("gift.disabled"))
        await state.clear()
        return

    link = f"https://t.me/{username}?start={token.code}"
    share_text = await i18n("gift.share_text")
    share_url = (
        "https://t.me/share/url?"
        f"url={quote(link, safe='')}&text={quote(share_text, safe='')}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await i18n("gift.btn.create_new"), url=share_url)]
        ]
    )
    body = await i18n("gift.created", amount=amount, link=link)
    await message.answer(body, reply_markup=kb)
    await state.clear()
