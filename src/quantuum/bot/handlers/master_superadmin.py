from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.auth.identity import find_superadmin_by_tg
from quantuum.bot.ui.callbacks import SuperAdminCb
from quantuum.db.models import Tenant
from quantuum.db.session import get_sessionmaker
from quantuum.domain.audit import record_audit
from quantuum.domain.invites import create_invite, list_invites, revoke_invite
from quantuum.domain.stats import tenant_stats
from quantuum.domain.tenants import (
    archive_tenant,
    get_tenant_bot,
    list_all_tenants,
    set_tenant_status,
)
from quantuum.i18n import Translator
from quantuum.settings import get_settings

router = Router()


async def _menu_kb(i18n: Translator):
    b = InlineKeyboardBuilder()
    b.button(text=await i18n("admin.menu.kb.tenants"), callback_data=SuperAdminCb(action="tenants"))
    b.button(text=await i18n("admin.menu.kb.invites"), callback_data=SuperAdminCb(action="invites"))
    b.adjust(2)
    return b.as_markup()


@router.message(Command("admin"))
async def on_admin(message: Message, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(message.from_user.id))
    if sa is None:
        await message.answer(await i18n("admin.denied"))
        return
    await message.answer(await i18n("admin.menu.title"), reply_markup=await _menu_kb(i18n))


async def _tenants_kb(tenants, i18n: Translator):
    b = InlineKeyboardBuilder()
    for t in tenants:
        b.button(
            text=f"{t.display_name} · {t.status}",
            callback_data=SuperAdminCb(action="tenant", tenant_id=t.id),
        )
    b.button(text=await i18n("admin.kb.back"), callback_data=SuperAdminCb(action="menu"))
    b.adjust(1)
    return b.as_markup()


async def _tenant_manage_kb(tenant: Tenant, i18n: Translator):
    b = InlineKeyboardBuilder()
    b.button(text=await i18n("admin.tenant.kb.stats"), callback_data=SuperAdminCb(action="stats", tenant_id=tenant.id))
    if tenant.status == "active":
        b.button(text=await i18n("admin.tenant.kb.suspend"), callback_data=SuperAdminCb(action="suspend", tenant_id=tenant.id))
    else:
        b.button(text=await i18n("admin.tenant.kb.resume"), callback_data=SuperAdminCb(action="resume", tenant_id=tenant.id))
    b.button(text=await i18n("admin.tenant.kb.delete"), callback_data=SuperAdminCb(action="delete", tenant_id=tenant.id))
    b.button(text=await i18n("admin.kb.back"), callback_data=SuperAdminCb(action="tenants"))
    b.adjust(1)
    return b.as_markup()


@router.callback_query(SuperAdminCb.filter(F.action == "menu"))
async def on_menu(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if await find_superadmin_by_tg(session, str(query.from_user.id)) is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
    await query.message.answer(await i18n("admin.menu.title"), reply_markup=await _menu_kb(i18n))
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "tenants"))
async def on_tenants(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if await find_superadmin_by_tg(session, str(query.from_user.id)) is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        tenants = await list_all_tenants(session)
    if not tenants:
        await query.message.answer(await i18n("admin.tenants.empty"))
        await query.answer()
        return
    await query.message.answer(
        await i18n("admin.tenants.title"), reply_markup=await _tenants_kb(tenants, i18n)
    )
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "tenant"))
async def on_tenant(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if await find_superadmin_by_tg(session, str(query.from_user.id)) is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        tenant = await session.get(Tenant, callback_data.tenant_id)
        bot = await get_tenant_bot(session, callback_data.tenant_id) if tenant is not None else None
    if tenant is None:
        await query.answer(await i18n("admin.stale"), show_alert=True)
        return
    title = await i18n(
        "admin.tenant.title", display_name=tenant.display_name, slug=tenant.slug, status=tenant.status
    )
    if bot is not None and bot.bot_username:
        title = f"{title}\n@{bot.bot_username}"
    await query.message.answer(title, reply_markup=await _tenant_manage_kb(tenant, i18n))
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "stats"))
async def on_tenant_stats(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if await find_superadmin_by_tg(session, str(query.from_user.id)) is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        s = await tenant_stats(session, callback_data.tenant_id)
    await query.message.answer(
        await i18n(
            "owner.stats.text",
            period_days=s["period_days"], active_customers=s["active_customers"],
            paid_customers=s["paid_customers"], dau=s["dau"], wau=s["wau"], mau=s["mau"],
            revenue_cents=s["revenue_cents"], mrr_cents=s["mrr_cents"],
            requests_by_kind=s["requests_by_kind"],
        )
    )
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "suspend"))
async def on_tenant_suspend(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(query.from_user.id))
        if sa is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        tenant = await session.get(Tenant, callback_data.tenant_id)
        if tenant is not None and tenant.is_platform:
            await query.answer(await i18n("owner.pause.platform_blocked"), show_alert=True)
            return
        await set_tenant_status(session, callback_data.tenant_id, "suspended", "paused")
        await record_audit(
            session, tenant_id=callback_data.tenant_id, actor_account_id=sa.id,
            action="tenant.pause", entity_type="tenant", entity_id=callback_data.tenant_id,
        )
        await session.commit()
    await query.message.answer(await i18n("admin.tenant.suspended"))
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "resume"))
async def on_tenant_resume(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(query.from_user.id))
        if sa is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        await set_tenant_status(session, callback_data.tenant_id, "active", "active")
        await record_audit(
            session, tenant_id=callback_data.tenant_id, actor_account_id=sa.id,
            action="tenant.resume", entity_type="tenant", entity_id=callback_data.tenant_id,
        )
        await session.commit()
    await query.message.answer(await i18n("admin.tenant.resumed"))
    await query.answer()


async def _invites_kb(invites, i18n: Translator):
    b = InlineKeyboardBuilder()
    for inv in invites:
        b.button(
            text=f"{inv.code} · {inv.tier} · {inv.used_count}/{inv.max_uses}",
            callback_data=SuperAdminCb(action="revoke", invite_id=inv.id),
        )
    b.button(text=await i18n("admin.invites.kb.new"), callback_data=SuperAdminCb(action="newinvite"))
    b.button(text=await i18n("admin.kb.back"), callback_data=SuperAdminCb(action="menu"))
    b.adjust(1)
    return b.as_markup()


def _invite_deeplink(code: str) -> str:
    return f"https://t.me/{get_settings().master_bot_username}?start={code}"


@router.callback_query(SuperAdminCb.filter(F.action == "invites"))
async def on_invites(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        if await find_superadmin_by_tg(session, str(query.from_user.id)) is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        invites = [i for i in await list_invites(session) if i.status == "active"]
    if not invites:
        await query.message.answer(
            await i18n("admin.invites.empty"), reply_markup=await _invites_kb([], i18n)
        )
        await query.answer()
        return
    await query.message.answer(
        await i18n("admin.invites.title"), reply_markup=await _invites_kb(invites, i18n)
    )
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "newinvite"))
async def on_new_invite(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(query.from_user.id))
        if sa is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        invite = await create_invite(session, created_by_account_id=sa.id)
        code = invite.code
        inv_id = invite.id
        await record_audit(
            session, tenant_id=None, actor_account_id=sa.id,
            action="platform.invite.create", entity_type="tenant_invite", entity_id=inv_id,
        )
        await session.commit()
    await query.message.answer(
        await i18n("admin.invite.created", link=_invite_deeplink(code))
    )
    await query.answer()


@router.callback_query(SuperAdminCb.filter(F.action == "revoke"))
async def on_revoke_invite(query: CallbackQuery, callback_data: SuperAdminCb, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(query.from_user.id))
        if sa is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        revoked = await revoke_invite(session, callback_data.invite_id)
        if revoked is None:
            await query.answer(await i18n("admin.stale"), show_alert=True)
            return
        await record_audit(
            session, tenant_id=None, actor_account_id=sa.id,
            action="platform.invite.revoke", entity_type="tenant_invite", entity_id=callback_data.invite_id,
        )
        await session.commit()
    await query.message.answer(await i18n("admin.invite.revoked"))
    await query.answer()


class SuperAdminDelete(StatesGroup):
    awaiting_confirm = State()


@router.callback_query(SuperAdminCb.filter(F.action == "delete"))
async def on_tenant_delete(
    query: CallbackQuery, callback_data: SuperAdminCb, state: FSMContext, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        if await find_superadmin_by_tg(session, str(query.from_user.id)) is None:
            await query.answer(await i18n("admin.denied"), show_alert=True)
            return
        tenant = await session.get(Tenant, callback_data.tenant_id)
    if tenant is None:
        await query.answer(await i18n("admin.stale"), show_alert=True)
        return
    if tenant.is_platform:
        await query.answer(await i18n("owner.delete.platform_blocked"), show_alert=True)
        return
    await state.set_state(SuperAdminDelete.awaiting_confirm)
    await state.update_data(tenant_id=callback_data.tenant_id, slug=tenant.slug)
    await query.message.answer(await i18n("owner.delete.prompt", slug=tenant.slug))
    await query.answer()


@router.message(Command("cancel"), SuperAdminDelete.awaiting_confirm)
async def on_delete_cancel(message: Message, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await message.answer(await i18n("owner.delete.cancelled"))


@router.message(SuperAdminDelete.awaiting_confirm)
async def on_delete_confirm(message: Message, state: FSMContext, i18n: Translator) -> None:
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    expected_slug = data["slug"]
    if (message.text or "").strip() != expected_slug:
        await message.answer(await i18n("owner.delete.mismatch", slug=expected_slug))
        return  # stay in state to retry
    async with get_sessionmaker()() as session:
        sa = await find_superadmin_by_tg(session, str(message.from_user.id))
        if sa is None:
            await message.answer(await i18n("admin.denied"))
            await state.clear()
            return
        await archive_tenant(session, tenant_id)
        await record_audit(
            session, tenant_id=tenant_id, actor_account_id=sa.id,
            action="tenant.delete", entity_type="tenant", entity_id=tenant_id,
        )
        await session.commit()
    await state.clear()
    await message.answer(await i18n("owner.delete.done"))
