from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.ui.callbacks import OwnerUserCb
from quantuum.db.models import Tenant
from quantuum.db.session import get_sessionmaker
from quantuum.domain.accounts import (
    CustomerCard,
    adjust_package_credits,
    clear_account_ban,
    count_tenant_customers,
    get_customer_card,
    is_tenant_staff,
    list_tenant_customers,
    set_account_ban,
)
from quantuum.domain.audit import record_audit
from quantuum.domain.owner_console import authorize_tenant_action
from quantuum.i18n import Translator

router = Router()
PAGE_SIZE = 8


class OwnerUserAdmin(StatesGroup):
    awaiting_credit_amount = State()
    awaiting_ban_reason = State()


@router.callback_query(OwnerUserCb.filter(F.action == "list"))
async def on_users_list(
    query: CallbackQuery, callback_data: OwnerUserCb, i18n: Translator
) -> None:
    tenant_id = callback_data.tenant_id
    page = callback_data.page
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(query.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        tenant = await session.get(Tenant, tenant_id)
        total = await count_tenant_customers(session, tenant_id)
        rows = await list_tenant_customers(
            session, tenant_id, limit=PAGE_SIZE, offset=page * PAGE_SIZE
        )
    if total == 0:
        await query.message.answer(await i18n("owner.users.empty"))
        await query.answer()
        return
    builder = InlineKeyboardBuilder()
    for row in rows:
        name = row.full_name or await i18n("owner.users.unnamed", id=row.account_id)
        label = await i18n("owner.users.row", name=name, credits=row.package_credits)
        if row.status == "disabled":
            label += " 🚫"
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=OwnerUserCb(
                    action="open", tenant_id=tenant_id, account_id=row.account_id
                ).pack(),
            )
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text=await i18n("owner.users.nav.prev"),
                callback_data=OwnerUserCb(action="list", tenant_id=tenant_id, page=page - 1).pack(),
            )
        )
    if (page + 1) * PAGE_SIZE < total:
        nav.append(
            InlineKeyboardButton(
                text=await i18n("owner.users.nav.next"),
                callback_data=OwnerUserCb(action="list", tenant_id=tenant_id, page=page + 1).pack(),
            )
        )
    if nav:
        builder.row(*nav)
    display_name = tenant.display_name if tenant is not None else ""
    await query.message.answer(
        await i18n("owner.users.header", display_name=display_name),
        reply_markup=builder.as_markup(),
    )
    await query.answer()


async def _card_text(card: CustomerCard, i18n: Translator) -> str:
    name = card.full_name or await i18n("owner.users.unnamed", id=card.account_id)
    subscription = (
        card.subscription_active_until.strftime("%Y-%m-%d")
        if card.subscription_active_until is not None
        else "—"
    )
    status = await i18n(
        "owner.user.status.banned" if card.status == "disabled" else "owner.user.status.active"
    )
    text = await i18n(
        "owner.user.card",
        name=name,
        tg_id=card.tg_user_id or "—",
        credits=card.package_credits,
        subscription=subscription,
        status=status,
    )
    if card.status == "disabled":
        text += "\n" + await i18n("owner.user.card.banned", reason=card.ban_reason or "—")
    return text


async def _card_markup(card: CustomerCard, tenant_id: int, i18n: Translator):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.user.kb.grant"),
            callback_data=OwnerUserCb(action="grant", tenant_id=tenant_id, account_id=card.account_id).pack(),
        )
    )
    if card.status == "disabled":
        builder.row(
            InlineKeyboardButton(
                text=await i18n("owner.user.kb.unban"),
                callback_data=OwnerUserCb(action="unban", tenant_id=tenant_id, account_id=card.account_id).pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=await i18n("owner.user.kb.ban"),
                callback_data=OwnerUserCb(action="ban", tenant_id=tenant_id, account_id=card.account_id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.user.kb.back"),
            callback_data=OwnerUserCb(action="list", tenant_id=tenant_id, page=0).pack(),
        )
    )
    return builder.as_markup()


@router.callback_query(OwnerUserCb.filter(F.action == "open"))
async def on_user_open(
    query: CallbackQuery, callback_data: OwnerUserCb, i18n: Translator
) -> None:
    tenant_id = callback_data.tenant_id
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(query.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        card = await get_customer_card(session, tenant_id, callback_data.account_id)
    if card is None:
        await query.answer(await i18n("owner.user.not_found"), show_alert=True)
        return
    await query.message.answer(
        await _card_text(card, i18n),
        reply_markup=await _card_markup(card, tenant_id, i18n),
    )
    await query.answer()


@router.callback_query(OwnerUserCb.filter(F.action == "grant"))
async def on_user_grant_start(
    query: CallbackQuery, callback_data: OwnerUserCb, state: FSMContext, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(query.from_user.id), tenant_id=callback_data.tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
    await state.set_state(OwnerUserAdmin.awaiting_credit_amount)
    await state.update_data(tenant_id=callback_data.tenant_id, account_id=callback_data.account_id)
    await query.message.answer(await i18n("owner.user.grant.prompt"))
    await query.answer()


@router.message(Command("cancel"), OwnerUserAdmin.awaiting_credit_amount)
async def on_grant_cancel(message: Message, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await message.answer(await i18n("owner.user.cancelled"))


@router.message(OwnerUserAdmin.awaiting_credit_amount)
async def on_user_grant_amount(message: Message, state: FSMContext, i18n: Translator) -> None:
    try:
        delta = int((message.text or "").strip())
    except ValueError:
        await message.answer(await i18n("owner.user.grant.invalid"))
        return
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    account_id = data["account_id"]
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await message.answer(await i18n("owner.no_rights"))
            await state.clear()
            return
        card = await get_customer_card(session, tenant_id, account_id)
        if card is None:
            await message.answer(await i18n("owner.user.not_found"))
            await state.clear()
            return
        before = card.package_credits
        after = await adjust_package_credits(session, account_id, delta)
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_account_id=actor,
            action="account.credits_adjust",
            entity_type="account",
            entity_id=account_id,
            payload={"delta": delta, "before": before, "after": after},
        )
        await session.commit()
    await state.clear()
    await message.answer(await i18n("owner.user.grant.done", credits=after))


@router.callback_query(OwnerUserCb.filter(F.action == "ban"))
async def on_user_ban_start(
    query: CallbackQuery, callback_data: OwnerUserCb, state: FSMContext, i18n: Translator
) -> None:
    tenant_id = callback_data.tenant_id
    account_id = callback_data.account_id
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(query.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        if await is_tenant_staff(session, tenant_id=tenant_id, account_id=account_id):
            await query.answer(await i18n("owner.user.ban.staff_blocked"), show_alert=True)
            return
    await state.set_state(OwnerUserAdmin.awaiting_ban_reason)
    await state.update_data(tenant_id=tenant_id, account_id=account_id)
    await query.message.answer(await i18n("owner.user.ban.prompt"))
    await query.answer()


@router.message(Command("cancel"), OwnerUserAdmin.awaiting_ban_reason)
async def on_ban_cancel(message: Message, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await message.answer(await i18n("owner.user.cancelled"))


@router.message(OwnerUserAdmin.awaiting_ban_reason)
async def on_user_ban_reason(message: Message, state: FSMContext, i18n: Translator) -> None:
    reason = (message.text or "").strip()
    if not reason:
        await message.answer(await i18n("owner.user.ban.invalid"))
        return
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    account_id = data["account_id"]
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await message.answer(await i18n("owner.no_rights"))
            await state.clear()
            return
        if await is_tenant_staff(session, tenant_id=tenant_id, account_id=account_id):
            await message.answer(await i18n("owner.user.ban.staff_blocked"))
            await state.clear()
            return
        await set_account_ban(session, account_id, reason=reason)
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_account_id=actor,
            action="account.ban",
            entity_type="account",
            entity_id=account_id,
            payload={"reason": reason},
        )
        await session.commit()
    await state.clear()
    await message.answer(await i18n("owner.user.ban.done"))


@router.callback_query(OwnerUserCb.filter(F.action == "unban"))
async def on_user_unban(
    query: CallbackQuery, callback_data: OwnerUserCb, i18n: Translator
) -> None:
    tenant_id = callback_data.tenant_id
    account_id = callback_data.account_id
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=str(query.from_user.id), tenant_id=tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        await clear_account_ban(session, account_id)
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_account_id=actor,
            action="account.unban",
            entity_type="account",
            entity_id=account_id,
        )
        await session.commit()
    await query.message.answer(await i18n("owner.user.unban.done"))
    await query.answer()
