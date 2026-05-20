from collections.abc import AsyncIterator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.auth.jwt_tokens import verify_access_token
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def current_account(
    authorization: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> Account:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = verify_access_token(token)
    except Exception as exc:  # jwt errors
        raise HTTPException(status_code=401, detail="invalid token") from exc
    account = await session.get(Account, int(claims["sub"]))
    if account is None or account.status != "active":
        raise HTTPException(status_code=401, detail="account not found")
    return account
