from quantuum.common.datetime import utcnow
from quantuum.db.models import Account


async def touch_last_seen(session, account_id: int) -> None:
    account = await session.get(Account, account_id)
    if account is not None:
        account.last_seen_at = utcnow()
        session.add(account)
        await session.commit()
