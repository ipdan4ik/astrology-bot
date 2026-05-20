from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import AccountBalance, Request


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
        return "subscription"

    if balance.package_credits >= 1:
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
        balance.updated_at = utcnow()
        session.add(balance)

    request.charged_against = "none"
    request.status = "refunded"
    session.add(request)
    await session.commit()
