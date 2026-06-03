from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.methods import GetManagedBotToken
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlmodel import select

from quantuum.bot.ui.callbacks import OwnerOnboardCb
from quantuum.db.models import Tenant
from quantuum.db.session import get_sessionmaker
from quantuum.domain.invites import get_invite_by_code, invite_is_usable
from quantuum.domain.provisioning import (
    BotAlreadyInUseError,
    create_tenant_from_onboarding,
    finalize_provisioning,
    validate_bot_token,
)
from quantuum.i18n import Translator
from quantuum.redis_client import publish_bot_reload
from quantuum.tasks.enqueue import enqueue_provision_tenant

router = Router()


class OwnerOnboarding(StatesGroup):
    slug = State()
    display_name = State()
    default_lang = State()
    confirm = State()


class ManualToken(StatesGroup):
    awaiting = State()


async def slug_is_available(session, slug: str) -> bool:
    result = await session.execute(select(Tenant.id).where(Tenant.slug == slug))
    return result.scalar_one_or_none() is None


async def master_cancel_kb(i18n: Translator):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=await i18n("master.kb.cancel"),
            callback_data=OwnerOnboardCb(action="cancel").pack(),
        )
    )
    return builder.as_markup()


async def get_invite_by_id(session, invite_id: int):
    from quantuum.db.models import TenantInvite

    return await session.get(TenantInvite, invite_id)


async def confirm_kb(i18n: Translator):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=await i18n("master.kb.create_bot"),
            callback_data=OwnerOnboardCb(action="confirm").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await i18n("master.kb.cancel"),
            callback_data=OwnerOnboardCb(action="cancel").pack(),
        )
    )
    return builder.as_markup()


@router.message(CommandStart(deep_link=True))
async def on_start_with_code(
    message: Message, command: CommandObject, state: FSMContext, i18n: Translator
) -> None:
    code = (command.args or "").strip()
    async with get_sessionmaker()() as session:
        invite = await get_invite_by_code(session, code)
    if invite is None or not invite_is_usable(invite):
        await message.answer(await i18n("master.onboard.invite_invalid"))
        return
    await state.set_state(OwnerOnboarding.slug)
    await state.update_data(invite_id=invite.id, default_lang=invite.preset_default_lang or "ru")
    prefill = (
        await i18n("master.onboard.slug_prefill", slug=invite.preset_slug)
        if invite.preset_slug
        else ""
    )
    await message.answer(
        await i18n("master.onboard.slug_prompt", prefill=prefill),
        reply_markup=await master_cancel_kb(i18n),
    )


@router.message(CommandStart(deep_link=False))
async def on_plain_start(message: Message, i18n: Translator) -> None:
    await message.answer(await i18n("master.onboard.plain_start"))


@router.message(OwnerOnboarding.slug)
async def on_slug(message: Message, state: FSMContext, i18n: Translator) -> None:
    slug = (message.text or "").strip().lower()
    if not slug or " " in slug:
        await message.answer(
            await i18n("master.onboard.slug_invalid"),
            reply_markup=await master_cancel_kb(i18n),
        )
        return
    async with get_sessionmaker()() as session:
        if not await slug_is_available(session, slug):
            await message.answer(
                await i18n("master.onboard.slug_taken"),
                reply_markup=await master_cancel_kb(i18n),
            )
            return
    await state.update_data(slug=slug)
    await state.set_state(OwnerOnboarding.display_name)
    await message.answer(
        await i18n("master.onboard.display_name_prompt"),
        reply_markup=await master_cancel_kb(i18n),
    )


@router.message(OwnerOnboarding.display_name)
async def on_display_name(message: Message, state: FSMContext, i18n: Translator) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(
            await i18n("master.onboard.display_name_empty"),
            reply_markup=await master_cancel_kb(i18n),
        )
        return
    await state.update_data(display_name=name)
    await state.set_state(OwnerOnboarding.default_lang)
    await message.answer(
        await i18n("master.onboard.lang_prompt"),
        reply_markup=await master_cancel_kb(i18n),
    )


@router.message(OwnerOnboarding.default_lang)
async def on_default_lang(message: Message, state: FSMContext, i18n: Translator) -> None:
    lang = (message.text or "").strip().lower()
    if len(lang) != 2 or not lang.isalpha():
        await message.answer(await i18n("master.onboard.lang_invalid"))
        return
    await state.update_data(default_lang=lang)
    data = await state.get_data()
    await state.set_state(OwnerOnboarding.confirm)
    await message.answer(
        await i18n(
            "master.onboard.confirm",
            slug=data["slug"],
            display_name=data["display_name"],
            language=lang,  # NOT lang= — Translator reserves `lang` (resolution language)
        ),
        reply_markup=await confirm_kb(i18n),
    )


@router.callback_query(OwnerOnboardCb.filter(F.action == "confirm"), OwnerOnboarding.confirm)
async def on_confirm(
    query: CallbackQuery,
    callback_data: OwnerOnboardCb,
    state: FSMContext,
    i18n: Translator,
    chat_id: int | None = None,
) -> None:
    data = await state.get_data()
    owner_tg_id = query.from_user.id
    owner_chat_id = chat_id if chat_id is not None else query.message.chat.id
    async with get_sessionmaker()() as session:
        invite = await get_invite_by_id(session, data["invite_id"])
        if invite is None or not invite_is_usable(invite):
            await query.message.answer(await i18n("master.onboard.invite_gone"))
            await state.clear()
            await query.answer()
            return
        tenant = await create_tenant_from_onboarding(
            session,
            invite=invite,
            slug=data["slug"],
            display_name=data["display_name"],
            default_lang=data.get("default_lang", "ru"),
            owner_tg_id=owner_tg_id,
            owner_chat_id=owner_chat_id,
        )
    await enqueue_provision_tenant(tenant.id)
    await state.set_state(ManualToken.awaiting)
    await state.update_data(tenant_id=tenant.id)
    await query.message.answer(await i18n("master.onboard.creating"))
    await query.answer()


@router.callback_query(OwnerOnboardCb.filter(F.action == "cancel"))
async def on_cancel(
    query: CallbackQuery, callback_data: OwnerOnboardCb, state: FSMContext, i18n: Translator
) -> None:
    await state.clear()
    await query.message.answer(await i18n("master.onboard.cancelled"))
    await query.answer()


@router.message(ManualToken.awaiting, F.managed_bot_created)
async def on_managed_bot_created(
    message: Message, state: FSMContext, i18n: Translator, bot: Bot
) -> None:
    """Programmatic path (Bot API 9.6): the owner tapped the request_managed_bot button,
    Telegram created the bot, and we fetch its token to finalize provisioning."""
    created = message.managed_bot_created
    data = await state.get_data()
    tenant_id = data.get("tenant_id")
    if tenant_id is None:
        return
    token = await bot(GetManagedBotToken(user_id=created.bot_user.id))
    async with get_sessionmaker()() as session:
        try:
            tenant_bot = await finalize_provisioning(
                session,
                tenant_id=tenant_id,
                token=token,
                bot_telegram_id=created.bot_user.id,
                bot_username=created.bot_user.username,
                default_lang=data.get("default_lang", "ru"),
            )
        except BotAlreadyInUseError:
            await message.answer(await i18n("master.onboard.token_in_use"))
            return
    await publish_bot_reload()
    await state.clear()
    await message.answer(
        await i18n("master.onboard.done", username=tenant_bot.bot_username),
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(ManualToken.awaiting)
async def on_manual_token(message: Message, state: FSMContext, i18n: Translator) -> None:
    token = (message.text or "").strip()
    result = await validate_bot_token(token)
    if result is None:
        await message.answer(await i18n("master.onboard.token_invalid"))
        return
    bot_id, username = result
    data = await state.get_data()
    async with get_sessionmaker()() as session:
        try:
            tenant_bot = await finalize_provisioning(
                session,
                tenant_id=data["tenant_id"],
                token=token,
                bot_telegram_id=bot_id,
                bot_username=username,
                default_lang=data.get("default_lang", "ru"),
            )
        except BotAlreadyInUseError:
            await message.answer(await i18n("master.onboard.token_in_use"))
            return
    await publish_bot_reload()
    await state.clear()
    await message.answer(
        await i18n("master.onboard.done", username=tenant_bot.bot_username)
    )
