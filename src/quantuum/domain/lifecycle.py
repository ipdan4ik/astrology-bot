from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import AccountIdentity, AccountSubscription
from quantuum.domain.billing import GRACE_DAYS, REMINDER_DAYS, recompute_account_balance


@dataclass
class DueReminder:
    sub_id: int
    account_id: int
    tenant_id: int
    chat_id: str | None


async def sweep_subscriptions(session, *, now: datetime | None = None) -> dict[str, int]:
    """Advance the subscription state machine. Returns counts of transitions.

    active -> grace  when now >= ends_at
    grace  -> expired when now >= ends_at + GRACE_DAYS
    Balances of affected accounts are recomputed so subscription_active_until stays correct.
    """
    now = now or utcnow()
    affected: set[int] = set()

    grace_q = await session.execute(
        select(AccountSubscription).where(
            AccountSubscription.status == "active",
            AccountSubscription.ends_at <= now,
        )
    )
    to_grace = list(grace_q.scalars().all())
    for sub in to_grace:
        sub.status = "grace"
        session.add(sub)
        affected.add(sub.account_id)

    expire_q = await session.execute(
        select(AccountSubscription).where(
            AccountSubscription.status == "grace",
            AccountSubscription.ends_at <= now - timedelta(days=GRACE_DAYS),
        )
    )
    to_expired = list(expire_q.scalars().all())
    for sub in to_expired:
        sub.status = "expired"
        session.add(sub)
        affected.add(sub.account_id)

    await session.commit()
    for account_id in affected:
        await recompute_account_balance(session, account_id)

    return {"to_grace": len(to_grace), "to_expired": len(to_expired)}


async def due_renewal_reminders(session, *, now: datetime | None = None) -> list[DueReminder]:
    """Active subscriptions entering the reminder window that have not been reminded yet."""
    now = now or utcnow()
    window_end = now + timedelta(days=REMINDER_DAYS)
    result = await session.execute(
        select(AccountSubscription, AccountIdentity.provider_user_id)
        .join(
            AccountIdentity,
            (AccountIdentity.account_id == AccountSubscription.account_id)
            & (AccountIdentity.provider == "tg_chat"),
            isouter=True,
        )
        .where(
            AccountSubscription.status == "active",
            AccountSubscription.reminder_sent_at.is_(None),
            AccountSubscription.ends_at > now,
            AccountSubscription.ends_at <= window_end,
        )
    )
    return [
        DueReminder(sub_id=sub.id, account_id=sub.account_id, tenant_id=sub.tenant_id, chat_id=chat)
        for sub, chat in result.all()
    ]


async def mark_reminder_sent(session, sub_id: int, *, now: datetime | None = None) -> None:
    sub = await session.get(AccountSubscription, sub_id)
    if sub is not None:
        sub.reminder_sent_at = now or utcnow()
        session.add(sub)
        await session.commit()
