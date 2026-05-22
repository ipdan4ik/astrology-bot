from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.auth.identity import find_superadmin_by_tg
from quantuum.bot.ui.callbacks import SuperAdminCb
from quantuum.db.models import Tenant
from quantuum.db.session import get_sessionmaker
from quantuum.domain.audit import record_audit
from quantuum.domain.stats import tenant_stats
from quantuum.domain.tenants import list_all_tenants, set_tenant_status
from quantuum.i18n import Translator

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
    if tenant is None:
        await query.answer(await i18n("admin.stale"), show_alert=True)
        return
    await query.message.answer(
        await i18n("admin.tenant.title", display_name=tenant.display_name, slug=tenant.slug, status=tenant.status),
        reply_markup=await _tenant_manage_kb(tenant, i18n),
    )
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
