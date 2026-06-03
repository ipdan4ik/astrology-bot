from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlmodel import select

from quantuum.bot.ui.callbacks import (
    OwnerBrandingCb,
    OwnerFeatureCb,
    OwnerGiftsCb,
    OwnerManageCb,
    OwnerReferralsCb,
    OwnerUserCb,
)
from quantuum.db.models import Account, AccountIdentity, Tenant
from quantuum.db.session import get_sessionmaker
from quantuum.domain.audit import record_audit
from quantuum.domain.owner_console import (
    authorize_tenant_action,
    managed_tenants,
    resolve_managed_tenant_by_slug,
)
from quantuum.domain.stats import tenant_stats
from quantuum.domain.tenant_branding import (
    MAX_DISPLAY_NAME_LEN,
    MAX_HELP_LEN,
    MAX_SIGNATURE_LEN,
    MAX_WELCOME_LEN,
    get_branding_text,
    reset_branding_text,
    set_branding_text,
    set_display_name,
)
from quantuum.domain.referrals import (
    DEFAULT_REWARD_CREDITS,
    MAX_REWARD_CREDITS,
    get_reward_credits,
    reset_reward_credits,
    set_reward_credits,
)
from quantuum.domain.gifts import (
    MAX_EXPIRY_DAYS,
    MIN_EXPIRY_DAYS,
    get_expiry_days,
    reset_expiry_days,
    set_expiry_days,
)
from quantuum.domain.tenant_features import (
    list_feature_states,
    set_feature_enabled,
)
from quantuum.domain.tenants import archive_tenant, set_tenant_status, transfer_ownership
from quantuum.i18n import Translator
from quantuum.logging_setup import get_logger

_log = get_logger("tenant_features.console")

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
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.manage.kb.users"),
            callback_data=OwnerUserCb(action="list", tenant_id=tenant.id, page=0).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.features.btn"),
            callback_data=OwnerFeatureCb(
                action="open", tenant_id=tenant.id, key=""
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.branding.btn"),
            callback_data=OwnerBrandingCb(
                action="open", tenant_id=tenant.id, key=""
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.referrals.menu_button"),
            callback_data=OwnerReferralsCb(
                action="open", tenant_id=tenant.id
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.gifts.menu_button"),
            callback_data=OwnerGiftsCb(action="open", tenant_id=tenant.id).pack(),
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
    builder.row(
        InlineKeyboardButton(
            text=await i18n("owner.manage.kb.delete"),
            callback_data=OwnerManageCb(action="delete", tenant_id=tenant.id).pack(),
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
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id,
            roles=("owner",),
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
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id,
            roles=("owner",),
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
    tenant, _actor = resolved
    await state.set_state(OwnerTransfer.awaiting_target)
    await state.update_data(tenant_id=tenant.id)
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


# ── SP2: /manage → 🗑 Delete (type-the-slug confirm) ────────────────────────────


class OwnerDelete(StatesGroup):
    awaiting_confirm = State()


@router.callback_query(OwnerManageCb.filter(F.action == "delete"))
async def on_manage_delete(
    query: CallbackQuery, callback_data: OwnerManageCb, state: FSMContext, i18n: Translator
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id,
            roles=("owner",),
        )
        if actor is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        tenant = await session.get(Tenant, callback_data.tenant_id)
        if tenant is not None and tenant.is_platform:
            await query.answer(await i18n("owner.delete.platform_blocked"), show_alert=True)
            return
        slug = tenant.slug if tenant is not None else ""
    await state.set_state(OwnerDelete.awaiting_confirm)
    await state.update_data(tenant_id=callback_data.tenant_id, slug=slug)
    await query.message.answer(await i18n("owner.delete.prompt", slug=slug))
    await query.answer()


@router.message(Command("cancel"), OwnerDelete.awaiting_confirm)
async def on_delete_cancel(message: Message, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await message.answer(await i18n("owner.delete.cancelled"))


@router.message(OwnerDelete.awaiting_confirm)
async def on_delete_confirm(message: Message, state: FSMContext, i18n: Translator) -> None:
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    expected_slug = data["slug"]
    if (message.text or "").strip() != expected_slug:
        await message.answer(await i18n("owner.delete.mismatch", slug=expected_slug))
        return  # stay in state to retry
    async with get_sessionmaker()() as session:
        # Re-authorize at apply time (the role may have changed since the tap).
        actor = await authorize_tenant_action(
            session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id,
            roles=("owner",),
        )
        if actor is None:
            await message.answer(await i18n("owner.no_rights"))
            await state.clear()
            return
        await archive_tenant(session, tenant_id)
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_account_id=actor,
            action="tenant.delete",
            entity_type="tenant",
            entity_id=tenant_id,
        )
        await session.commit()
    await state.clear()
    await message.answer(await i18n("owner.delete.done"))


# ── Task 6: Features submenu + toggle ───────────────────────────────────────────


async def _features_keyboard(
    tenant_id: int, flags: dict[str, bool], i18n: Translator
):
    """12-toggle inline keyboard, 2 columns."""
    b = InlineKeyboardBuilder()

    def _mark(enabled: bool) -> str:
        return "✅" if enabled else "❌"

    top_level = [
        ("qa", "owner.features.label.qa"),
        ("blueprint", "owner.features.label.blueprint"),
        ("transits", "owner.features.label.transits"),
        ("daily", "owner.features.label.daily"),
    ]
    for key, label_key in top_level:
        text_label = f"{_mark(flags[key])} {await i18n(label_key)}"
        b.button(
            text=text_label,
            callback_data=OwnerFeatureCb(
                action="toggle", tenant_id=tenant_id, key=key
            ).pack(),
        )

    for kind in (
        "bazi", "numerology", "human_design", "astrology",
        "vedic", "gene_keys", "mayan", "aspects",
        "tarot", "iching",
    ):
        flag_key = f"reading.{kind}"
        text_label = f"{_mark(flags[flag_key])} {await i18n(f'readings.kind.{kind}')}"
        b.button(
            text=text_label,
            callback_data=OwnerFeatureCb(
                action="toggle", tenant_id=tenant_id, key=flag_key
            ).pack(),
        )

    b.adjust(2, 2, 2, 2, 2, 2, 2)
    return b.as_markup()


@router.callback_query(OwnerFeatureCb.filter(F.action == "open"))
async def on_features_open(
    query: CallbackQuery,
    callback_data: OwnerFeatureCb,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        flags = await list_feature_states(session, callback_data.tenant_id)
    kb = await _features_keyboard(callback_data.tenant_id, flags, i18n)
    await query.message.edit_text(
        await i18n("owner.features.title"),
        reply_markup=kb,
    )
    await query.answer()


@router.callback_query(OwnerFeatureCb.filter(F.action == "toggle"))
async def on_features_toggle(
    query: CallbackQuery,
    callback_data: OwnerFeatureCb,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    key = callback_data.key
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        flags = await list_feature_states(session, callback_data.tenant_id)
        new_state = not flags.get(key, True)
        await set_feature_enabled(
            session,
            tenant_id=callback_data.tenant_id,
            key=key,
            enabled=new_state,
            by_account_id=actor_id,
        )
        await session.commit()
        flags = await list_feature_states(session, callback_data.tenant_id)
    _log.info(
        "feature.toggled",
        tenant_id=callback_data.tenant_id,
        key=key,
        enabled=new_state,
        by_account_id=actor_id,
    )
    kb = await _features_keyboard(callback_data.tenant_id, flags, i18n)
    await query.message.edit_reply_markup(reply_markup=kb)
    await query.answer()


# ── SP3: Branding submenu + edit FSM ────────────────────────────────────────────

_branding_log = get_logger("tenant_branding.console")

_BRANDING_PREVIEW_LEN = 40

_BRANDING_LIMITS: dict[str, int] = {
    "display_name": MAX_DISPLAY_NAME_LEN,
    "start.welcome": MAX_WELCOME_LEN,
    "help.text": MAX_HELP_LEN,
    "brand.signature": MAX_SIGNATURE_LEN,
}

_BRANDING_LABEL_KEYS: dict[str, str] = {
    "display_name": "owner.branding.label.name",
    "start.welcome": "owner.branding.label.welcome",
    "help.text": "owner.branding.label.help",
    "brand.signature": "owner.branding.label.signature",
}


class OwnerBranding(StatesGroup):
    awaiting_value = State()


def _truncate(s: str) -> str:
    if len(s) <= _BRANDING_PREVIEW_LEN:
        return s
    return s[: _BRANDING_PREVIEW_LEN - 1] + "…"


async def _branding_current_value(
    session, *, tenant_id: int, key: str, lang: str
) -> str | None:
    """Resolve current value: Tenant.display_name for display_name; override
    text for the three i18n keys (None when no row)."""
    if key == "display_name":
        row = await session.get(Tenant, tenant_id)
        return row.display_name if row is not None else None
    return await get_branding_text(
        session, tenant_id=tenant_id, key=key, lang=lang
    )


async def _branding_keyboard(
    tenant_id: int, previews: dict[str, str], i18n: Translator
):
    b = InlineKeyboardBuilder()
    empty_marker = await i18n("owner.branding.preview_empty")
    for key in ("display_name", "start.welcome", "help.text", "brand.signature"):
        label = await i18n(_BRANDING_LABEL_KEYS[key])
        preview = previews.get(key) or ""
        preview = _truncate(preview) if preview else empty_marker
        b.button(
            text=f"{label}: {preview}",
            callback_data=OwnerBrandingCb(
                action="edit", tenant_id=tenant_id, key=key
            ).pack(),
        )
    b.adjust(1, 1, 1, 1)
    return b.as_markup()


@router.callback_query(OwnerBrandingCb.filter(F.action == "open"))
async def on_branding_open(
    query: CallbackQuery,
    callback_data: OwnerBrandingCb,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        previews = {}
        for key in ("display_name", "start.welcome", "help.text", "brand.signature"):
            previews[key] = await _branding_current_value(
                session, tenant_id=callback_data.tenant_id, key=key, lang=i18n.lang
            )
    kb = await _branding_keyboard(callback_data.tenant_id, previews, i18n)
    await query.message.edit_text(
        await i18n("owner.branding.title", language=i18n.lang),
        reply_markup=kb,
    )
    await query.answer()


@router.callback_query(OwnerBrandingCb.filter(F.action == "edit"))
async def on_branding_edit(
    query: CallbackQuery,
    callback_data: OwnerBrandingCb,
    state: FSMContext,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    key = callback_data.key
    if key not in _BRANDING_LIMITS:
        await query.answer(await i18n("owner.no_rights"), show_alert=True)
        return
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
    await state.set_state(OwnerBranding.awaiting_value)
    await state.update_data(
        tenant_id=callback_data.tenant_id,
        key=key,
        lang=i18n.lang,
    )
    label = await i18n(_BRANDING_LABEL_KEYS[key])
    await query.message.answer(
        await i18n("owner.branding.prompt", label=label, language=i18n.lang)
    )
    await query.answer()


@router.message(Command("cancel"), OwnerBranding.awaiting_value)
async def on_branding_cancel(message: Message, state: FSMContext, i18n: Translator) -> None:
    await state.clear()
    await message.answer(await i18n("owner.branding.cancelled"))


@router.message(OwnerBranding.awaiting_value)
async def on_branding_value(message: Message, state: FSMContext, i18n: Translator) -> None:
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    key = data["key"]
    lang = data["lang"]
    raw = message.text or ""

    if raw.strip() == "/reset":
        async with get_sessionmaker()() as session:
            actor_id = await authorize_tenant_action(
                session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id
            )
            if actor_id is None:
                await message.answer(await i18n("owner.no_rights"))
                await state.clear()
                return
            if key == "display_name":
                await message.answer(
                    await i18n("owner.branding.bad_format")
                )
                return
            await reset_branding_text(
                session, tenant_id=tenant_id, key=key, lang=lang
            )
            await session.commit()
        _branding_log.info(
            "branding.reset",
            tenant_id=tenant_id,
            key=key,
            lang=lang,
            by_account_id=actor_id,
        )
        await state.clear()
        await message.answer(await i18n("owner.branding.reset_done"))
        return

    if raw == "":
        await message.answer(await i18n("owner.branding.empty_value"))
        return

    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id
        )
        if actor_id is None:
            await message.answer(await i18n("owner.no_rights"))
            await state.clear()
            return
        try:
            if key == "display_name":
                await set_display_name(
                    session,
                    tenant_id=tenant_id,
                    display_name=raw,
                    by_account_id=actor_id,
                )
            else:
                await set_branding_text(
                    session,
                    tenant_id=tenant_id,
                    key=key,
                    lang=lang,
                    text=raw,
                    by_account_id=actor_id,
                )
            await session.commit()
        except ValueError as exc:
            err = str(exc)
            if "too long" in err:
                limit = _BRANDING_LIMITS[key]
                await message.answer(
                    await i18n(
                        "owner.branding.too_long",
                        actual=len(raw),
                        limit=limit,
                    )
                )
            elif "newline" in err:
                await message.answer(await i18n("owner.branding.bad_format"))
            elif "empty" in err:
                await message.answer(await i18n("owner.branding.empty_value"))
            else:
                await message.answer(await i18n("owner.branding.bad_format"))
            return

    _branding_log.info(
        "branding.updated",
        tenant_id=tenant_id,
        key=key,
        lang=None if key == "display_name" else lang,
        by_account_id=actor_id,
        length=len(raw),
    )
    await state.clear()
    await message.answer(await i18n("owner.branding.saved"))


# ── SP4: Referrals submenu + edit FSM ───────────────────────────────────────────


class OwnerReferrals(StatesGroup):
    awaiting_value = State()


async def _referrals_keyboard(i18n: Translator, tenant_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text=await i18n("owner.referrals.menu_button"),
        callback_data=OwnerReferralsCb(action="edit", tenant_id=tenant_id).pack(),
    )
    b.adjust(1)
    return b.as_markup()


@router.callback_query(OwnerReferralsCb.filter(F.action == "open"))
async def on_referrals_open(
    query: CallbackQuery,
    callback_data: OwnerReferralsCb,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        current = await get_reward_credits(session, tenant_id=callback_data.tenant_id)
    body = (
        f"{await i18n('owner.referrals.title')}\n\n"
        f"{await i18n('owner.referrals.current_value', value=current)}"
    )
    await query.message.answer(body, reply_markup=await _referrals_keyboard(i18n, callback_data.tenant_id))
    await query.answer()


@router.callback_query(OwnerReferralsCb.filter(F.action == "edit"))
async def on_referrals_edit(
    query: CallbackQuery,
    callback_data: OwnerReferralsCb,
    state: FSMContext,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
    await state.set_state(OwnerReferrals.awaiting_value)
    await state.update_data(tenant_id=callback_data.tenant_id)
    await query.message.answer(
        await i18n("owner.referrals.prompt", max=MAX_REWARD_CREDITS)
        + "\n"
        + await i18n("owner.referrals.cancel_hint"),
    )
    await query.answer()


@router.message(Command("cancel"), OwnerReferrals.awaiting_value)
async def on_referrals_cancel(
    message: Message, state: FSMContext, i18n: Translator
) -> None:
    await state.clear()
    await message.answer(await i18n("menu.cancelled"))


@router.message(OwnerReferrals.awaiting_value)
async def on_referrals_value(
    message: Message,
    state: FSMContext,
    i18n: Translator,
) -> None:
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    text_in = (message.text or "").strip()

    if text_in == "/reset":
        async with get_sessionmaker()() as session:
            actor_id = await authorize_tenant_action(
                session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id
            )
            if actor_id is None:
                await message.answer(await i18n("owner.no_rights"))
                await state.clear()
                return
            await reset_reward_credits(
                session, tenant_id=tenant_id, by_account_id=actor_id
            )
            await session.commit()
        await state.clear()
        await message.answer(
            await i18n("owner.referrals.reset", value=DEFAULT_REWARD_CREDITS)
        )
        return

    try:
        value = int(text_in)
    except (TypeError, ValueError):
        await message.answer(await i18n("owner.referrals.not_a_number"))
        return  # stay in state

    if value < 0 or value > MAX_REWARD_CREDITS:
        await message.answer(
            await i18n("owner.referrals.too_large", max=MAX_REWARD_CREDITS)
        )
        return  # stay in state

    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=str(message.from_user.id), tenant_id=tenant_id
        )
        if actor_id is None:
            await message.answer(await i18n("owner.no_rights"))
            await state.clear()
            return
        await set_reward_credits(
            session,
            tenant_id=tenant_id,
            value=value,
            by_account_id=actor_id,
        )
        await session.commit()

    await state.clear()
    await message.answer(await i18n("owner.referrals.saved", value=value))


# ── SP5: Gifts submenu + edit FSM ───────────────────────────────────────────


class OwnerGifts(StatesGroup):
    awaiting_value = State()


async def _gifts_keyboard(i18n: Translator, tenant_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text=await i18n("owner.gifts.menu_button"),
        callback_data=OwnerGiftsCb(action="edit", tenant_id=tenant_id).pack(),
    )
    b.button(
        text=await i18n("owner.gifts.reset"),
        callback_data=OwnerGiftsCb(action="reset", tenant_id=tenant_id).pack(),
    )
    b.adjust(1)
    return b.as_markup()


@router.callback_query(OwnerGiftsCb.filter(F.action == "open"))
async def on_gifts_open(
    query: CallbackQuery,
    callback_data: OwnerGiftsCb,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        current = await get_expiry_days(session, tenant_id=callback_data.tenant_id)
    body = (
        f"{await i18n('owner.gifts.title')}\n\n"
        f"{await i18n('owner.gifts.current_value', value=current)}"
    )
    await query.message.answer(
        body, reply_markup=await _gifts_keyboard(i18n, callback_data.tenant_id)
    )
    await query.answer()


@router.callback_query(OwnerGiftsCb.filter(F.action == "edit"))
async def on_gifts_edit(
    query: CallbackQuery,
    callback_data: OwnerGiftsCb,
    state: FSMContext,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
    await state.set_state(OwnerGifts.awaiting_value)
    await state.update_data(tenant_id=callback_data.tenant_id)
    await query.message.answer(
        await i18n("owner.gifts.prompt", min=MIN_EXPIRY_DAYS, max=MAX_EXPIRY_DAYS)
        + "\n"
        + await i18n("owner.gifts.cancel_hint"),
    )
    await query.answer()


@router.callback_query(OwnerGiftsCb.filter(F.action == "reset"))
async def on_gifts_reset(
    query: CallbackQuery,
    callback_data: OwnerGiftsCb,
    i18n: Translator,
) -> None:
    tg_user_id = str(query.from_user.id)
    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=callback_data.tenant_id
        )
        if actor_id is None:
            await query.answer(await i18n("owner.no_rights"), show_alert=True)
            return
        await reset_expiry_days(
            session, tenant_id=callback_data.tenant_id, by_account_id=actor_id
        )
        await session.commit()
    await query.message.answer(await i18n("owner.gifts.reset"))
    await query.answer()


@router.message(Command("cancel"), OwnerGifts.awaiting_value)
async def on_gifts_cancel(
    message: Message, state: FSMContext, i18n: Translator
) -> None:
    await state.clear()
    await message.answer(await i18n("menu.cancelled"))


@router.message(OwnerGifts.awaiting_value)
async def on_gifts_value(
    message: Message,
    state: FSMContext,
    i18n: Translator,
) -> None:
    data = await state.get_data()
    tenant_id = data["tenant_id"]
    tg_user_id = str(message.from_user.id)

    raw = (message.text or "").strip()
    try:
        days = int(raw)
    except ValueError:
        await message.answer(await i18n("owner.gifts.not_a_number"))
        return
    if days < MIN_EXPIRY_DAYS:
        await message.answer(await i18n("owner.gifts.too_small", min=MIN_EXPIRY_DAYS))
        return
    if days > MAX_EXPIRY_DAYS:
        await message.answer(await i18n("owner.gifts.too_large", max=MAX_EXPIRY_DAYS))
        return

    async with get_sessionmaker()() as session:
        actor_id = await authorize_tenant_action(
            session, tg_user_id=tg_user_id, tenant_id=tenant_id
        )
        if actor_id is None:
            await state.clear()
            await message.answer(await i18n("owner.no_rights"))
            return
        await set_expiry_days(
            session, tenant_id=tenant_id, days=days, by_account_id=actor_id
        )
        await session.commit()
    await state.clear()
    await message.answer(await i18n("owner.gifts.saved"))
