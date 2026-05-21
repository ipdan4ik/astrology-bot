from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    AccountBalance,
    AccountIdentity,
    DailyHoroscope,
    DailySubscription,
    NatalProfile,
)

_TERMINAL = {"done", "failed"}


async def is_subscriber(session, account_id: int) -> bool:
    bal = await session.get(AccountBalance, account_id)
    return bal is not None and bal.subscription_active_until is not None and (
        bal.subscription_active_until > utcnow()
    )


async def get_settings(session, account_id: int) -> DailySubscription | None:
    return await session.get(DailySubscription, account_id)


async def upsert_settings(
    session, *, tenant_id: int, account_id: int, enabled: bool, send_hour: int
) -> DailySubscription:
    row = await session.get(DailySubscription, account_id)
    if row is None:
        row = DailySubscription(account_id=account_id, tenant_id=tenant_id)
    row.tenant_id = tenant_id
    row.enabled = enabled
    row.send_hour = send_hour
    row.updated_at = utcnow()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def mark_sent(session, account_id: int, local_date: date) -> None:
    row = await session.get(DailySubscription, account_id)
    if row is None:
        return
    row.last_sent_on = local_date
    row.updated_at = utcnow()
    session.add(row)
    await session.commit()


async def claim_horoscope(
    session, *, tenant_id: int, account_id: int, natal_profile_id: int,
    local_date: date, lang: str | None,
) -> DailyHoroscope | None:
    """Insert a generating row for (account_id, local_date). Returns None if one already exists."""
    row = DailyHoroscope(
        tenant_id=tenant_id, account_id=account_id, natal_profile_id=natal_profile_id,
        local_date=local_date, lang=lang, status="generating",
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return None
    await session.refresh(row)
    return row


async def set_horoscope_status(session, horoscope_id: int, status: str, **fields) -> None:
    row = await session.get(DailyHoroscope, horoscope_id)
    if row is None:
        return
    row.status = status
    for key, value in fields.items():
        setattr(row, key, value)
    if status in _TERMINAL:
        row.completed_at = utcnow()
    session.add(row)
    await session.commit()


async def list_horoscopes(
    session, *, account_id: int, limit: int = 30, offset: int = 0
) -> list[DailyHoroscope]:
    result = await session.execute(
        select(DailyHoroscope)
        .where(DailyHoroscope.account_id == account_id)
        .order_by(DailyHoroscope.created_at.desc(), DailyHoroscope.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_tg_chat_id(session, account_id: int) -> str | None:
    result = await session.execute(
        select(AccountIdentity.provider_user_id).where(
            AccountIdentity.account_id == account_id,
            AccountIdentity.provider == "tg_chat",
        )
    )
    return result.scalars().first()


async def due_daily_account_ids(session, *, now: datetime) -> list[int]:
    """Account ids whose daily horoscope is due at *now* (tz-aware UTC).

    Eligible: enabled, active subscription, has a natal profile (timezone), the
    user's current LOCAL hour equals send_hour, and not already sent today (local).
    """
    result = await session.execute(
        select(DailySubscription, NatalProfile.timezone)
        .join(NatalProfile, NatalProfile.account_id == DailySubscription.account_id)
        .join(AccountBalance, AccountBalance.account_id == DailySubscription.account_id)
        .where(
            DailySubscription.enabled == True,  # noqa: E712
            AccountBalance.subscription_active_until.is_not(None),
            AccountBalance.subscription_active_until > now,
        )
    )
    due: list[int] = []
    for sub, tz_name in result.all():
        try:
            local = now.astimezone(ZoneInfo(tz_name))
        except (ZoneInfoNotFoundError, KeyError):
            continue
        if local.hour != sub.send_hour:
            continue
        if sub.last_sent_on is not None and sub.last_sent_on >= local.date():
            continue
        due.append(sub.account_id)
    return due
