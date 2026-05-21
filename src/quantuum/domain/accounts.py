from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import Account, AccountIdentity


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
