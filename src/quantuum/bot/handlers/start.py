from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from quantuum.bot.handlers.menu import show_main_menu
from quantuum.bot.handlers.start_tokens import (
    GiftClaimResult,
    dispatch_start_token,
    parse_start_payload,
    resolve_start_token,
)
from quantuum.bot.ui.keyboards import language_picker_kb
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.i18n import Translator

router = Router()


@router.message(CommandStart())
async def on_start(
    message: Message, account: Account, tenant_id: int, i18n: Translator
) -> None:
    payload = parse_start_payload(message.text)
    dispatch_result = None
    if payload:
        async with get_sessionmaker()() as session:
            token = await resolve_start_token(session, code=payload, tenant_id=tenant_id)
            if token is None:
                await message.answer(await i18n("invite.unknown_code"))
            else:
                dispatch_result = await dispatch_start_token(
                    session, token=token, account_id=account.id
                )
            await session.commit()
    if isinstance(dispatch_result, GiftClaimResult):
        await message.answer(
            await i18n("gift.received", amount=dispatch_result.amount)
        )

    if account.preferred_lang is None:
        await message.answer(
            await i18n("lang.prompt"),
            reply_markup=await language_picker_kb(tenant_id, action="setup"),
        )
        return
    await message.answer(await i18n("start.welcome"))
    await show_main_menu(message, tenant_id, i18n)
