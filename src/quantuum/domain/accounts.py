from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountBalance,
    AccountIdentity,
    NatalProfile,
)
from quantuum.domain.tenants import account_has_role


@dataclass
class CustomerRow:
    account_id: int
    full_name: str | None
    tg_user_id: str | None
    package_credits: int
    status: str


@dataclass
class CustomerCard:
    account_id: int
    full_name: str | None
    tg_user_id: str | None
    package_credits: int
    subscription_active_until: datetime | None
    free_trial_used: bool
    status: str
    ban_reason: str | None
    last_seen_at: datetime | None


async def touch_last_seen(session, account_id: int) -> None:
    account = await session.get(Account, account_id)
    if account is not None:
        account.last_seen_at = utcnow()
        session.add(account)
        await session.commit()


async def get_tg_chat_id(session, account_id: int) -> str | None:
    """Return the account's Telegram chat id (== tg_chat provider_user_id) or None."""
    result = await session.execute(
        select(AccountIdentity.provider_user_id).where(
            AccountIdentity.account_id == account_id,
            AccountIdentity.provider == "tg_chat",
        )
    )
    return result.scalars().first()


async def adjust_package_credits(session, account_id: int, delta: int) -> int:
    """Add (positive) or deduct (negative) package credits via the ledger.

    Positive delta inserts a 'manual' ledger row. Negative delta drains valid
    ledger rows oldest-expiring first, clamped at zero. The package_credits
    counter is kept equal to the valid ledger sum. Flushes; caller commits.
    Returns the new package_credits balance.
    """
    from quantuum.domain.billing import _sum_valid_packages, grant_credits
    from quantuum.domain.quota import _oldest_valid_package

    bal = await session.get(AccountBalance, account_id)
    if bal is None:
        bal = AccountBalance(account_id=account_id)
        session.add(bal)
        await session.flush()

    if delta > 0:
        acc = await session.get(Account, account_id)
        await grant_credits(
            session,
            account_id=account_id,
            tenant_id=acc.tenant_id,
            amount=delta,
            source="manual",
        )
        await session.refresh(bal)
        return bal.package_credits

    remaining = -delta
    while remaining > 0:
        pkg = await _oldest_valid_package(session, account_id)
        if pkg is None:
            break
        take = min(remaining, pkg.requests_remaining)
        pkg.requests_remaining -= take
        session.add(pkg)
        remaining -= take
    bal.package_credits = await _sum_valid_packages(session, account_id)
    bal.updated_at = utcnow()
    session.add(bal)
    await session.flush()
    return bal.package_credits


async def set_account_ban(session, account_id: int, *, reason: str) -> None:
    """Disable an account and record the ban reason. Flushes; caller commits."""
    acc = await session.get(Account, account_id)
    if acc is not None:
        acc.status = "disabled"
        acc.ban_reason = reason
        session.add(acc)
        await session.flush()


async def clear_account_ban(session, account_id: int) -> None:
    """Re-enable an account and clear the ban reason. Flushes; caller commits."""
    acc = await session.get(Account, account_id)
    if acc is not None:
        acc.status = "active"
        acc.ban_reason = None
        session.add(acc)
        await session.flush()


async def is_tenant_staff(session, *, tenant_id: int, account_id: int) -> bool:
    """True if the account holds owner or admin in the tenant (protects staff/self)."""
    return await account_has_role(
        session, tenant_id=tenant_id, account_id=account_id, role="owner"
    ) or await account_has_role(
        session, tenant_id=tenant_id, account_id=account_id, role="admin"
    )


async def count_tenant_customers(session, tenant_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(Account).where(Account.tenant_id == tenant_id)
    )
    return int(result.scalar_one())


async def list_tenant_customers(
    session, tenant_id: int, *, limit: int, offset: int
) -> list[CustomerRow]:
    """One page of a tenant's accounts, ordered by id, with name / tg id / credits.

    Left-joins so accounts without a balance, profile, or tg identity still appear.
    The provider filter sits in the JOIN ``ON`` (not WHERE) to keep those rows.
    """
    result = await session.execute(
        select(
            Account.id,
            Account.status,
            NatalProfile.full_name,
            AccountBalance.package_credits,
            AccountIdentity.provider_user_id,
        )
        .outerjoin(AccountBalance, AccountBalance.account_id == Account.id)
        .outerjoin(NatalProfile, NatalProfile.account_id == Account.id)
        .outerjoin(
            AccountIdentity,
            (AccountIdentity.account_id == Account.id)
            & (AccountIdentity.provider == "tg_chat"),
        )
        .where(Account.tenant_id == tenant_id)
        .order_by(Account.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        CustomerRow(
            account_id=row[0],
            status=row[1],
            full_name=row[2],
            package_credits=row[3] or 0,
            tg_user_id=row[4],
        )
        for row in result.all()
    ]


async def get_customer_card(
    session, tenant_id: int, account_id: int
) -> CustomerCard | None:
    acc = await session.get(Account, account_id)
    if acc is None or acc.tenant_id != tenant_id:
        return None
    bal = await session.get(AccountBalance, account_id)
    full_name = (
        await session.execute(
            select(NatalProfile.full_name).where(NatalProfile.account_id == account_id)
        )
    ).scalars().first()
    tg_user_id = (
        await session.execute(
            select(AccountIdentity.provider_user_id).where(
                AccountIdentity.account_id == account_id,
                AccountIdentity.provider == "tg_chat",
            )
        )
    ).scalars().first()
    return CustomerCard(
        account_id=acc.id,
        full_name=full_name,
        tg_user_id=tg_user_id,
        package_credits=bal.package_credits if bal is not None else 0,
        subscription_active_until=bal.subscription_active_until if bal is not None else None,
        free_trial_used=bal.free_trial_used if bal is not None else False,
        status=acc.status,
        ban_reason=acc.ban_reason,
        last_seen_at=acc.last_seen_at,
    )
