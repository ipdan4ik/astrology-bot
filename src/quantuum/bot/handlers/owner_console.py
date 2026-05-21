from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.ui.callbacks import OwnerManageCb
from quantuum.db.session import get_sessionmaker
from quantuum.domain.owner_console import managed_tenants, resolve_managed_tenant_by_slug

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
