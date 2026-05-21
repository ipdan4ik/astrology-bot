from sqlmodel import or_, select

from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import AccountBalance, AccountPackage, Request


async def _oldest_valid_package(session, account_id: int) -> AccountPackage | None:
    now = utcnow()
    result = await session.execute(
        select(AccountPackage)
        .where(
            AccountPackage.account_id == account_id,
            AccountPackage.requests_remaining > 0,
            or_(AccountPackage.expires_at.is_(None), AccountPackage.expires_at > now),
        )
        .order_by(AccountPackage.expires_at.is_(None), AccountPackage.expires_at, AccountPackage.purchased_at)
    )
    return result.scalars().first()


async def _newest_valid_package(session, account_id: int) -> AccountPackage | None:
    now = utcnow()
    result = await session.execute(
        select(AccountPackage)
        .where(
            AccountPackage.account_id == account_id,
            or_(AccountPackage.expires_at.is_(None), AccountPackage.expires_at > now),
        )
        .order_by(AccountPackage.purchased_at.desc())
    )
    return result.scalars().first()


async def consume_quota(session, account_id: int, kind: str) -> str:
    balance = await session.get(AccountBalance, account_id, with_for_update=True)
    if balance is None:
        balance = AccountBalance(account_id=account_id)
        session.add(balance)

    if not balance.free_trial_used and kind == "blueprint":
        balance.free_trial_used = True
        balance.updated_at = utcnow()
        session.add(balance)
        await session.commit()
        return "trial"

    if balance.subscription_active_until and balance.subscription_active_until > utcnow():
        await session.commit()
        return "subscription"

    if balance.package_credits >= 1:
        # Decrement the oldest-expiring package ledger row to mirror the credit spend.
        pkg = await _oldest_valid_package(session, account_id)
        if pkg is not None:
            pkg.requests_remaining -= 1
            session.add(pkg)
        balance.package_credits -= 1
        balance.updated_at = utcnow()
        session.add(balance)
        await session.commit()
        return "package"

    raise InsufficientFundsError("no quota available")


async def refund_quota(session, request_id: int) -> None:
    request = await session.get(Request, request_id)
    if request is None or request.charged_against in (None, "none"):
        return

    balance = await session.get(AccountBalance, request.account_id, with_for_update=True)
    if balance is not None:
        if request.charged_against == "trial":
            balance.free_trial_used = False
        elif request.charged_against == "package":
            balance.package_credits += 1
            pkg = await _newest_valid_package(session, request.account_id)
            if pkg is not None:
                pkg.requests_remaining += 1
                session.add(pkg)
        balance.updated_at = utcnow()
        session.add(balance)

    request.charged_against = "none"
    request.status = "refunded"
    session.add(request)
    await session.commit()
