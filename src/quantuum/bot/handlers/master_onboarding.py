from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlmodel import select

from quantuum.bot.ui.callbacks import OwnerOnboardCb
from quantuum.bot.ui.keyboards import cancel_kb
from quantuum.db.models import Tenant
from quantuum.db.session import get_sessionmaker
from quantuum.domain.invites import get_invite_by_code, invite_is_usable
from quantuum.domain.provisioning import create_tenant_from_onboarding
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


async def get_invite_by_code_or_id(session, invite_id: int):
    from quantuum.db.models import TenantInvite

    return await session.get(TenantInvite, invite_id)


def confirm_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Создать бота", callback_data=OwnerOnboardCb(action="confirm").pack()))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data=OwnerOnboardCb(action="cancel").pack()))
    return builder.as_markup()


@router.message(CommandStart(deep_link=True))
async def on_start_with_code(message: Message, command: CommandObject, state: FSMContext) -> None:
    code = (command.args or "").strip()
    async with get_sessionmaker()() as session:
        invite = await get_invite_by_code(session, code)
    if invite is None or not invite_is_usable(invite):
        await message.answer("Приглашение недействительно или истекло.")
        return
    await state.set_state(OwnerOnboarding.slug)
    await state.update_data(invite_id=invite.id, default_lang=invite.preset_default_lang or "ru")
    prefill = f" (предложено: {invite.preset_slug})" if invite.preset_slug else ""
    await message.answer(
        f"Добро пожаловать! Давай создадим бота. Введи slug тенанта (латиница, без пробелов){prefill}:",
        reply_markup=cancel_kb(),
    )


@router.message(CommandStart(deep_link=False))
async def on_plain_start(message: Message) -> None:
    await message.answer("Это бот онбординга платформы. Открой ссылку-приглашение, чтобы создать своего бота.")


@router.message(OwnerOnboarding.slug)
async def on_slug(message: Message, state: FSMContext) -> None:
    slug = (message.text or "").strip().lower()
    if not slug or " " in slug:
        await message.answer("Slug не должен быть пустым или содержать пробелы. Попробуй ещё раз:")
        return
    async with get_sessionmaker()() as session:
        if not await slug_is_available(session, slug):
            await message.answer("Этот slug уже занят. Введи другой:")
            return
    await state.update_data(slug=slug)
    await state.set_state(OwnerOnboarding.display_name)
    await message.answer("Отображаемое имя продукта (например «Acme Astro»):")


@router.message(OwnerOnboarding.display_name)
async def on_display_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не должно быть пустым. Введи ещё раз:")
        return
    await state.update_data(display_name=name)
    await state.set_state(OwnerOnboarding.default_lang)
    await message.answer("Язык по умолчанию (двухбуквенный код, например ru или en):")


@router.message(OwnerOnboarding.default_lang)
async def on_default_lang(message: Message, state: FSMContext) -> None:
    lang = (message.text or "").strip().lower()
    if len(lang) != 2 or not lang.isalpha():
        await message.answer("Нужен двухбуквенный код языка, например ru. Введи ещё раз:")
        return
    await state.update_data(default_lang=lang)
    data = await state.get_data()
    await state.set_state(OwnerOnboarding.confirm)
    await message.answer(
        f"Проверь данные:\nslug: {data['slug']}\nназвание: {data['display_name']}\nязык: {lang}\n\n"
        "Создаём бота?",
        reply_markup=confirm_kb(),
    )


@router.callback_query(OwnerOnboardCb.filter(F.action == "confirm"), OwnerOnboarding.confirm)
async def on_confirm(
    query: CallbackQuery, callback_data: OwnerOnboardCb, state: FSMContext, chat_id: int | None = None
) -> None:
    data = await state.get_data()
    owner_tg_id = query.from_user.id
    owner_chat_id = chat_id if chat_id is not None else query.message.chat.id
    async with get_sessionmaker()() as session:
        invite = await get_invite_by_code_or_id(session, data["invite_id"])
        if invite is None or not invite_is_usable(invite):
            await query.message.answer("Приглашение больше недействительно.")
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
    await query.message.answer("Создаю тенанта… Проверяю возможность автосоздания бота.")
    await query.answer()


@router.callback_query(OwnerOnboardCb.filter(F.action == "cancel"))
async def on_cancel(query: CallbackQuery, callback_data: OwnerOnboardCb, state: FSMContext) -> None:
    await state.clear()
    await query.message.answer("Онбординг отменён.")
    await query.answer()
