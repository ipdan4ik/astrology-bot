from zoneinfo import ZoneInfo

from aiogram import Bot

from quantuum.astrology.transits import compute_transits, render_daily_md
from quantuum.common.crypto import decrypt_token
from quantuum.common.datetime import utcnow
from quantuum.db.models import Account
from quantuum.domain.daily import (
    claim_horoscope,
    due_daily_account_ids,
    get_settings,
    get_tg_chat_id,
    is_subscriber,
    mark_sent,
    set_horoscope_status,
)
from quantuum.domain.llm_config import get_llm_config
from quantuum.tasks.enqueue import enqueue_daily
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.tenants import get_active_tenant_bot
from quantuum.domain.transits import resolve_natal
from quantuum.i18n import Translator, resolve_lang
from quantuum.llm.daily_horoscope import daily_horoscope
from quantuum.logging_setup import get_logger

logger = get_logger("task.daily")


async def deliver_daily(sessionmaker, *, tenant_id: int, chat_id: str, lang: str | None, text: str) -> None:
    """Send the horoscope via the user's tenant bot. Best-effort."""
    async with sessionmaker() as session:
        tb = await get_active_tenant_bot(session, tenant_id)
        if tb is None:
            return
        i18n = await Translator.build(
            session, tenant_id=tenant_id, preferred_lang=lang, tg_language_code=None
        )
        header = await i18n("daily.header")
    bot = Bot(token=decrypt_token(tb.bot_token_enc))
    try:
        await bot.send_message(int(chat_id), f"{header}\n\n{text}"[:4000])
    finally:
        await bot.session.close()


async def daily_generate(ctx, account_id: int) -> None:
    sessionmaker = ctx["sessionmaker"]
    deliver: tuple[int, str, str | None, str] | None = None

    async with sessionmaker() as session:
        account = await session.get(Account, account_id)
        if account is None:
            return
        if not await is_subscriber(session, account_id):
            return
        profile = await get_natal_profile(session, account_id)
        if profile is None:
            return
        settings = await get_settings(session, account_id)
        if settings is None or not settings.enabled:
            return

        local_date = utcnow().astimezone(ZoneInfo(profile.timezone)).date()
        lang = await resolve_lang(
            session,
            tenant_id=account.tenant_id,
            preferred_lang=account.preferred_lang,
            tg_language_code=None,
        )
        row = await claim_horoscope(
            session, tenant_id=account.tenant_id, account_id=account_id,
            natal_profile_id=profile.id, local_date=local_date, lang=lang,
        )
        if row is None:
            return  # already handled today

        try:
            inp, natal_md, _ = await resolve_natal(
                session, account_id=account_id, natal_profile_id=profile.id
            )
            report = compute_transits(inp, as_of=utcnow(), window_days=7)
            transit_md = render_daily_md(report, ahead_days=3)
            await set_horoscope_status(session, row.id, "generating", transit_md=transit_md)

            llm_client = ctx.get("llm_client")
            if llm_client is None:
                await set_horoscope_status(session, row.id, "failed", error="llm unavailable")
                await mark_sent(session, account_id, local_date)
                return

            cfg = await get_llm_config(session)
            result = await daily_horoscope(
                llm_client, natal_md, transit_md, lang=lang,
                model=cfg["model"], temperature=cfg["temperature"], max_tokens=cfg["max_tokens"],
            )
            await set_horoscope_status(
                session, row.id, "done",
                horoscope_md=result.text,
                llm_provider=cfg["provider"], llm_model=result.model,
                llm_tokens_in=result.tokens_in, llm_tokens_out=result.tokens_out,
            )
            await mark_sent(session, account_id, local_date)

            chat_id = await get_tg_chat_id(session, account_id)
            if chat_id is not None:
                deliver = (account.tenant_id, chat_id, lang, result.text)
        except Exception:
            logger.exception("daily_generation_failed", account_id=account_id)
            try:
                await set_horoscope_status(session, row.id, "failed", error="generation failed")
            except Exception:
                logger.exception("daily_set_failed_status_error", account_id=account_id)
            await mark_sent(session, account_id, local_date)
            return

    if deliver is not None:
        tenant_id, chat_id, lang, text = deliver
        try:
            await deliver_daily(sessionmaker, tenant_id=tenant_id, chat_id=chat_id, lang=lang, text=text)
        except Exception:
            logger.exception("daily_delivery_failed", account_id=account_id)

    logger.info("daily_generated", account_id=account_id)


async def daily_dispatch(ctx) -> None:
    """Hourly cron: enqueue a daily_generate job for every account due right now."""
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        account_ids = await due_daily_account_ids(session, now=utcnow())
    for account_id in account_ids:
        await enqueue_daily(account_id)
    logger.info("daily_dispatched", count=len(account_ids))
