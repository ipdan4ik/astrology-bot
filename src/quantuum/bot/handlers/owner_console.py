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
from quantuum.i18n import Translator

router = Router()


@router.message(Command("tenants"))
async def on_tenants(message: Message, i18n: Translator) -> None:
    tg_user_id = str(message.from_user.id)
    async with get_sessionmaker()() as session:
        tenants = await managed_tenants(session, tg_user_id)
    if not tenants:
        await message.answer(await i18n("owner.tenants.empty"))
        return
    lines = [await i18n("owner.tenants.header")]
    for t in tenants:
        lines.append(
            await i18n(
                "owner.tenants.line",
                display_name=t.display_name,
                slug=t.slug,
                status=t.status,
            )
        )
    lines.append(await i18n("owner.tenants.hint"))
    await message.answer("\n".join(lines))


@router.message(Command("manage"))
async def on_manage(message: Message, command: CommandObject, i18n: Translator) -> None:
    slug = (command.args or "").strip()
    if not slug:
        await message.answer(await i18n("owner.manage.usage"))
        return
    tg_user_id = str(message.from_user.id)
    async with get_sessionmaker()() as session:
        resolved = await resolve_managed_tenant_by_slug(session, tg_user_id=tg_user_id, slug=slug)
    if resolved is None:
        await message.answer(await i18n("owner.manage.not_found"))
        return
    tenant, _actor = resolved
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.manage.kb.stats"),
            callback_data=OwnerManageCb(action="stats", tenant_id=tenant.id).pack(),
        )
    )
    if tenant.status == "active":
        builder.row(
            InlineKeyboardButton(
                text=await i18n("owner.manage.kb.pause"),
                callback_data=OwnerManageCb(action="pause", tenant_id=tenant.id).pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=await i18n("owner.manage.kb.resume"),
                callback_data=OwnerManageCb(action="resume", tenant_id=tenant.id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.manage.kb.transfer"),
            callback_data=OwnerManageCb(action="transfer", tenant_id=tenant.id).pack(),
        )
    )
    await message.answer(
        await i18n(
            "owner.manage.title",
            display_name=tenant.display_name,
            slug=tenant.slug,
            status=tenant.status,
        ),
        reply_markup=builder.as_markup(),
    )


# ── Task 4: manage callbacks (stats / pause / resume) ───────────────────────────


@router.callback_query(OwnerManageCb.filter(F.action == "stats"))
async def on_manage_stats(
    query: CallbackQuery, callback_data: OwnerManageCb, i18n: Translator
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        s = await tenant_stats(session, callback_data.tenant_id)
    text = await i18n(
        "owner.stats.text",
        period_days=s["period_days"],
        active_customers=s["active_customers"],
        paid_customers=s["paid_customers"],
        dau=s["dau"],
        wau=s["wau"],
        mau=s["mau"],
        revenue_cents=s["revenue_cents"],
        mrr_cents=s["mrr_cents"],
        requests_by_kind=s["requests_by_kind"],
    )
    await query.message.answer(text)
    await query.answer()


@router.callback_query(OwnerManageCb.filter(F.action == "pause"))
async def on_manage_pause(
    query: CallbackQuery, callback_data: OwnerManageCb, i18n: Translator
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        tenant = await session.get(Tenant, callback_data.tenant_id)
        if tenant is not None and tenant.is_platform:
            await query.answer(
                await i18n("owner.pause.platform_blocked"), show_alert=True
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
    await query.message.answer(await i18n("owner.pause.done"))
    await query.answer()


@router.callback_query(OwnerManageCb.filter(F.action == "resume"))
async def on_manage_resume(
    query: CallbackQuery, callback_data: OwnerManageCb, i18n: Translator
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
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
    await query.message.answer(await i18n("owner.resume.done"))
    await query.answer()


# ── Task 5: /transfer FSM (owner-only) ──────────────────────────────────────────


class OwnerTransfer(StatesGroup):
    awaiting_target = State()


@router.message(Command("transfer"))
async def on_transfer_cmd(
    message: Message, command: CommandObject, state: FSMContext, i18n: Translator
) -> None:
    slug = (command.args or "").strip()
    if not slug:
        await message.answer(await i18n("owner.transfer.usage"))
        return
    tg_user_id = str(message.from_user.id)
    async with get_sessionmaker()() as session:
        resolved = await resolve_managed_tenant_by_slug(
            session, tg_user_id=tg_user_id, slug=slug, roles=("owner",)
        )
    if resolved is None:
        await message.answer(await i18n("owner.transfer.not_owner"))
        return
    tenant, actor = resolved
    await state.set_state(OwnerTransfer.awaiting_target)
    await state.update_data(tenant_id=tenant.id, actor_id=actor)
    await message.answer(await i18n("owner.transfer.prompt"))


@router.message(Command("cancel"), OwnerTransfer.awaiting_target)
async def on_transfer_cancel(message: Message, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await message.answer(await i18n("owner.transfer.cancelled"))


@router.message(OwnerTransfer.awaiting_target)
async def on_transfer_target(message: Message, state: FSMContext, i18n: Translator) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(await i18n("owner.transfer.target_invalid"))
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
            await message.answer(await i18n("owner.transfer.no_rights_anymore"))
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
            await message.answer(await i18n("owner.transfer.no_account"))
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
    await message.answer(await i18n("owner.transfer.done"))
