from urllib.parse import quote

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select

from quantuum.bot.ui import text
from quantuum.db.models import Account, TenantBot
from quantuum.db.session import get_sessionmaker
from quantuum.domain.referrals import (
    generate_referral_code,
    get_referral_stats,
    get_reward_credits,
)
from quantuum.domain.tenant_features import is_feature_enabled
from quantuum.i18n import Translator

router = Router()

_INVITE_LABELS = text.menu_button_labels("btn.invite")


async def _tenant_bot_username(session, tenant_id: int) -> str | None:
    row = (
        await session.execute(
            select(TenantBot).where(TenantBot.tenant_id == tenant_id)
        )
    ).scalars().first()
    return row.bot_username if row else None


async def show_invite(
    message: Message, *, account_id: int, tenant_id: int, i18n: Translator
) -> None:
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, tenant_id, "referrals"):
            await message.answer(await i18n("invite.disabled"))
            return

        code = await generate_referral_code(
            session, account_id=account_id, tenant_id=tenant_id
        )
        stats = await get_referral_stats(session, account_id=account_id)
        reward = await get_reward_credits(session, tenant_id=tenant_id)
        username = await _tenant_bot_username(session, tenant_id)
        await session.commit()

    if not username:
        # bot_username is set during tenant provisioning; guard the window
        # before the master-onboarding flow has resolved it.
        await message.answer(await i18n("invite.disabled"))
        return

    link = f"https://t.me/{username}?start={code}"
    # `earned` snapshots claimed * current reward; historical payouts at a
    # different rate are not reflected.
    body = (
        f"{await i18n('invite.title')}\n\n"
        f"{await i18n('invite.link_label')}: {link}\n"
        f"{await i18n('invite.earned', credits=stats['claimed'] * reward, friends=stats['claimed'])}"
    )

    share_text = await i18n("invite.share_text")
    share_url = (
        "https://t.me/share/url?"
        f"url={quote(link, safe='')}&text={quote(share_text, safe='')}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await i18n("btn.invite"), url=share_url)]
        ]
    )
    await message.answer(body, reply_markup=kb)


@router.message(Command("invite"))
async def on_invite_cmd(
    message: Message, account: Account, tenant_id: int, i18n: Translator
) -> None:
    await show_invite(message, account_id=account.id, tenant_id=tenant_id, i18n=i18n)


@router.message(F.text.in_(_INVITE_LABELS))
async def on_invite_btn(
    message: Message, account: Account, tenant_id: int, i18n: Translator
) -> None:
    await show_invite(message, account_id=account.id, tenant_id=tenant_id, i18n=i18n)
