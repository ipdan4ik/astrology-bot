from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.invite import show_invite
from quantuum.db.models import StartToken, Tenant, TenantBot
from quantuum.domain.referrals import REFERRAL_KIND
from quantuum.domain.tenant_features import FEATURE_KEYS, set_feature_enabled
from quantuum.i18n import Translator


def test_referrals_feature_key_registered():
    assert "referrals" in FEATURE_KEYS


async def _tenant_bot(session: AsyncSession) -> tuple[Tenant, TenantBot]:
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    bot = TenantBot(
        tenant_id=t.id,
        bot_username="my_bot",
        bot_token_enc=b"enc",
        webhook_secret_path="wsp-t1",
    )
    session.add(bot)
    await session.flush()
    return t, bot


async def _seed_i18n(session: AsyncSession, tenant_id: int) -> None:
    from quantuum.db.bootstrap import ensure_base_strings, ensure_tenant_default_language

    await ensure_base_strings(session)
    await ensure_tenant_default_language(session, tenant_id)


async def test_show_invite_lazy_creates_referral_code(session: AsyncSession):
    t, _ = await _tenant_bot(session)
    await _seed_i18n(session, t.id)
    await session.commit()
    aid = (
        await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_user_id="1001"
        )
    ).id

    message = MagicMock()
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=t.id, lang="en")

    await show_invite(message, account_id=aid, tenant_id=t.id, i18n=i18n)

    token = (
        (
            await session.execute(
                select(StartToken).where(
                    StartToken.kind == REFERRAL_KIND,
                    StartToken.owner_account_id == aid,
                )
            )
        )
        .scalars()
        .first()
    )
    assert token is not None


async def test_show_invite_message_contains_link_and_stats(session: AsyncSession):
    t, _ = await _tenant_bot(session)
    await _seed_i18n(session, t.id)
    await session.commit()
    aid = (
        await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_user_id="1001"
        )
    ).id

    message = MagicMock()
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=t.id, lang="en")

    await show_invite(message, account_id=aid, tenant_id=t.id, i18n=i18n)

    args, kwargs = message.answer.call_args
    body = args[0] if args else kwargs.get("text", "")
    assert "my_bot" in body
    assert "?start=" in body
    assert "0" in body
    markup = kwargs.get("reply_markup")
    assert markup is not None


async def test_show_invite_disabled_when_feature_off(session: AsyncSession):
    t, _ = await _tenant_bot(session)
    await _seed_i18n(session, t.id)
    aid = (
        await find_or_create_account_by_tg(
            session, tenant_id=t.id, tg_user_id="1001"
        )
    ).id
    await set_feature_enabled(
        session, tenant_id=t.id, key="referrals", enabled=False, by_account_id=aid
    )
    # Commit so show_invite's internal session can see the disabled flag.
    await session.commit()

    message = MagicMock()
    message.answer = AsyncMock()
    i18n = Translator(tenant_id=t.id, lang="en")

    await show_invite(message, account_id=aid, tenant_id=t.id, i18n=i18n)

    token = (
        (
            await session.execute(
                select(StartToken).where(StartToken.owner_account_id == aid)
            )
        )
        .scalars()
        .first()
    )
    assert token is None
    args, kwargs = message.answer.call_args
    assert kwargs.get("reply_markup") is None
