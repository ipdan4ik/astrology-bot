from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlmodel import select

from quantuum.bot.ui.callbacks import OwnerManageCb
from quantuum.db.models import Account, AccountIdentity, Tenant
from quantuum.db.session import get_sessionmaker
from quantuum.domain.audit import record_audit
from quantuum.domain.owner_console import (
    authorize_tenant_action,
    managed_tenants,
    resolve_managed_tenant_by_slug,
)
from quantuum.domain.stats import tenant_stats
from quantuum.domain.tenants import set_tenant_status, transfer_ownership

router = Router()


@router.message(Command("tenants"))
async def on_tenants(message: Message) -> None:
    tg_user_id = str(message.from_user.id)
    async with get_sessionmaker()() as session:
        tenants = await managed_tenants(session, tg_user_id)
    if not tenants:
        await message.answer("У тебя пока нет тенантов. Создай бота по ссылке-приглашению.")
        return
    lines = ["Твои тенанты:"]
    for t in tenants:
        lines.append(f"• {t.display_name} (/{t.slug}) — {t.status}")
    lines.append("\nУправление: /manage <slug>")
    await message.answer("\n".join(lines))


@router.message(Command("manage"))
async def on_manage(message: Message, command: CommandObject) -> None:
    slug = (command.args or "").strip()
    if not slug:
        await message.answer("Использование: /manage <slug>")
        return
    tg_user_id = str(message.from_user.id)
    async with get_sessionmaker()() as session:
        resolved = await resolve_managed_tenant_by_slug(session, tg_user_id=tg_user_id, slug=slug)
    if resolved is None:
        await message.answer("Тенант не найден или у тебя нет прав.")
        return
    tenant, _actor = resolved
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📊 Статистика",
            callback_data=OwnerManageCb(action="stats", tenant_id=tenant.id).pack(),
        )
    )
    if tenant.status == "active":
        builder.row(
            InlineKeyboardButton(
                text="⏸ Пауза",
                callback_data=OwnerManageCb(action="pause", tenant_id=tenant.id).pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="▶️ Возобновить",
                callback_data=OwnerManageCb(action="resume", tenant_id=tenant.id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🔁 Передать владение",
            callback_data=OwnerManageCb(action="transfer", tenant_id=tenant.id).pack(),
        )
    )
    await message.answer(
        f"Управление: {tenant.display_name} (/{tenant.slug}) — {tenant.status}",
        reply_markup=builder.as_markup(),
    )


# ── Task 4: manage callbacks (stats / pause / resume) ───────────────────────────


@router.callback_query(OwnerManageCb.filter(F.action == "stats"))
async def on_manage_stats(query: CallbackQuery, callback_data: OwnerManageCb) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor is None:
            await query.answer("Нет прав", show_alert=True)
            return
        s = await tenant_stats(session, callback_data.tenant_id)
    text = (
        f"📊 Статистика (за {s['period_days']} дн.)\n"
        f"Активные: {s['active_customers']}, платящие: {s['paid_customers']}\n"
        f"DAU/WAU/MAU: {s['dau']}/{s['wau']}/{s['mau']}\n"
        f"Выручка: {s['revenue_cents']}, MRR: {s['mrr_cents']}\n"
        f"Запросы: {s['requests_by_kind']}"
    )
    await query.message.answer(text)
    await query.answer()


@router.callback_query(OwnerManageCb.filter(F.action == "pause"))
async def on_manage_pause(query: CallbackQuery, callback_data: OwnerManageCb) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor is None:
            await query.answer("Нет прав", show_alert=True)
            return
        tenant = await session.get(Tenant, callback_data.tenant_id)
        if tenant is not None and tenant.is_platform:
            await query.answer(
                "Нельзя поставить на паузу платформенный тенант", show_alert=True
            )
            return
        await set_tenant_status(session, callback_data.tenant_id, "suspended", "paused")
        await record_audit(
            session,
            tenant_id=callback_data.tenant_id,
            actor_account_id=actor,
            action="tenant.pause",
            entity_type="tenant",
            entity_id=callback_data.tenant_id,
        )
        await session.commit()
    await query.message.answer("⏸ Поставлено на паузу.")
    await query.answer()


@router.callback_query(OwnerManageCb.filter(F.action == "resume"))
async def on_manage_resume(query: CallbackQuery, callback_data: OwnerManageCb) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor is None:
            await query.answer("Нет прав", show_alert=True)
            return
        await set_tenant_status(session, callback_data.tenant_id, "active", "active")
        await record_audit(
            session,
            tenant_id=callback_data.tenant_id,
            actor_account_id=actor,
            action="tenant.resume",
            entity_type="tenant",
            entity_id=callback_data.tenant_id,
        )
        await session.commit()
    await query.message.answer("▶️ Возобновлено.")
    await query.answer()


# ── Task 5: /transfer FSM (owner-only) ──────────────────────────────────────────


class OwnerTransfer(StatesGroup):
    awaiting_target = State()


@router.message(Command("transfer"))
async def on_transfer_cmd(
    message: Message, command: CommandObject, state: FSMContext
) -> None:
    slug = (command.args or "").strip()
    if not slug:
        await message.answer("Использование: /transfer <slug>")
        return
    tg_user_id = str(message.from_user.id)
    async with get_sessionmaker()() as session:
        resolved = await resolve_managed_tenant_by_slug(
            session, tg_user_id=tg_user_id, slug=slug, roles=("owner",)
        )
    if resolved is None:
        await message.answer("Тенант не найден или ты не владелец.")
        return
    tenant, actor = resolved
    await state.set_state(OwnerTransfer.awaiting_target)
    await state.update_data(tenant_id=tenant.id, actor_id=actor)
    await message.answer(
        "Перешли Telegram ID нового владельца (число). "
        "Он должен уже иметь аккаунт в этом тенанте (запустить твоего бота)."
    )


@router.message(Command("cancel"), OwnerTransfer.awaiting_target)
async def on_transfer_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.")


@router.message(OwnerTransfer.awaiting_target)
async def on_transfer_target(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Нужен числовой Telegram ID. Попробуй ещё раз или /cancel.")
        return
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    async with get_sessionmaker()() as session:
        # Re-authorize at apply time: the owner's role may have changed since
        # /transfer was issued.
        actor_id = await authorize_tenant_action(
            session,
            tg_user_id=str(message.from_user.id),
            tenant_id=tenant_id,
            roles=("owner",),
        )
        if actor_id is None:
            await message.answer("Больше нет прав на передачу.")
            await state.clear()
            return
        # find the new owner's account IN THIS tenant via tg_chat identity
        q = (
            select(Account.id)
            .join(AccountIdentity, AccountIdentity.account_id == Account.id)
            .where(
                Account.tenant_id == tenant_id,
                AccountIdentity.provider == "tg_chat",
                AccountIdentity.provider_user_id == raw,
            )
            .limit(1)
        )
        new_owner_account_id = (await session.execute(q)).scalar_one_or_none()
        if new_owner_account_id is None:
            await message.answer(
                "У этого пользователя нет аккаунта в тенанте. "
                "Он должен сначала запустить твоего бота."
            )
            return  # stay in state so they can retry
        tenant = await session.get(Tenant, tenant_id)
        before = tenant.primary_owner_account_id
        await transfer_ownership(
            session,
            tenant_id=tenant_id,
            new_owner_account_id=new_owner_account_id,
            actor_id=actor_id,
        )
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_account_id=actor_id,
            action="tenant.transfer",
            entity_type="tenant",
            entity_id=tenant_id,
            payload={"before": before, "after": new_owner_account_id},
        )
        await session.commit()
    await state.clear()
    await message.answer("✅ Готово. Владение передано.")
