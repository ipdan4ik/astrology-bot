from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import Account, AccountBalance, AccountIdentity


async def _ensure_balance(session, account_id: int) -> None:
    existing = await session.get(AccountBalance, account_id)
    if existing is None:
        session.add(AccountBalance(account_id=account_id))


async def _create_account(session, tenant_id: int) -> Account:
    account = Account(tenant_id=tenant_id)
    session.add(account)
    await session.flush()
    await _ensure_balance(session, account.id)
    return account


async def find_or_create_account_by_email(session, *, tenant_id: int, email: str) -> Account:
    result = await session.execute(
        select(AccountIdentity)
        .join(Account, Account.id == AccountIdentity.account_id)
        .where(
            AccountIdentity.provider == "magic_link",
            AccountIdentity.email == email,
            Account.tenant_id == tenant_id,
        )
    )
    identity = result.scalar_one_or_none()
    if identity is not None:
        return await session.get(Account, identity.account_id)

    account = await _create_account(session, tenant_id)
    session.add(
        AccountIdentity(
            account_id=account.id, provider="magic_link", email=email, verified_at=utcnow()
        )
    )
    await session.commit()
    await session.refresh(account)
    return account


async def find_or_create_account_by_tg(session, *, tenant_id: int, tg_user_id: str) -> Account:
    result = await session.execute(
        select(AccountIdentity)
        .join(Account, Account.id == AccountIdentity.account_id)
        .where(
            AccountIdentity.provider == "tg_chat",
            AccountIdentity.provider_user_id == tg_user_id,
            Account.tenant_id == tenant_id,
        )
    )
    identity = result.scalar_one_or_none()
    if identity is not None:
        return await session.get(Account, identity.account_id)

    account = await _create_account(session, tenant_id)
    session.add(
        AccountIdentity(
            account_id=account.id,
            provider="tg_chat",
            provider_user_id=tg_user_id,
            verified_at=utcnow(),
        )
    )
    await session.commit()
    await session.refresh(account)
    return account
