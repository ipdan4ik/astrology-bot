from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import Account, AccountBalance, AccountIdentity
from quantuum.domain.tenants import account_has_role


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
    """Add (or, for negative delta, deduct) package credits, clamped at zero.

    Creates the AccountBalance row if missing. Flushes; caller commits.
    Returns the new package_credits balance.
    """
    bal = await session.get(AccountBalance, account_id)
    if bal is None:
        bal = AccountBalance(account_id=account_id)
        session.add(bal)
        await session.flush()
    bal.package_credits = max(0, bal.package_credits + delta)
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
