from sqlmodel import or_, select

from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import AccountBalance, AccountPackage, Request
from quantuum.domain.referrals import maybe_payout_referral
from quantuum.logging_setup import get_logger

logger = get_logger(__name__)


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


async def consume_quota(session, account_id: int, kind: str, *, cost_units: int = 1) -> str:
    if cost_units < 1:
        raise ValueError(f"cost_units must be >= 1, got {cost_units}")
    balance = await session.get(AccountBalance, account_id, with_for_update=True)
    if balance is None:
        balance = AccountBalance(account_id=account_id)
        session.add(balance)

    if balance.subscription_active_until and balance.subscription_active_until > utcnow():
        await session.commit()
        return "subscription"

    if balance.package_credits >= cost_units:
        # Drain `cost_units` from oldest-expiring packages FIFO. The balance
        # counter is the source of truth — if package rows are absent (legacy
        # rows that pre-date AccountPackage ledger, or test fixtures that set
        # the balance directly), we still consume from the balance.
        remaining = cost_units
        while remaining > 0:
            pkg = await _oldest_valid_package(session, account_id)
            if pkg is None:
                break
            take = min(remaining, pkg.requests_remaining)
            pkg.requests_remaining -= take
            session.add(pkg)
            remaining -= take
        balance.package_credits -= cost_units
        balance.updated_at = utcnow()
        session.add(balance)
        await session.commit()
        try:
            await maybe_payout_referral(session, referee_account_id=account_id)
            await session.commit()
        except Exception:
            logger.exception("referral_payout_failed", account_id=account_id)
            await session.rollback()
        return "package"

    raise InsufficientFundsError("no quota available")


async def refund_quota(session, request_id: int) -> None:
    request = await session.get(Request, request_id)
    if request is None or request.charged_against in (None, "none"):
        return

    units = max(request.cost_units or 1, 1)
    balance = await session.get(AccountBalance, request.account_id, with_for_update=True)
    if balance is not None:
        if request.charged_against == "trial":
            balance.free_trial_used = False
        elif request.charged_against == "package":
            balance.package_credits += units
            pkg = await _newest_valid_package(session, request.account_id)
            if pkg is not None:
                pkg.requests_remaining += units
                session.add(pkg)
        balance.updated_at = utcnow()
        session.add(balance)

    request.charged_against = "none"
    request.status = "refunded"
    session.add(request)
    await session.commit()
