from collections.abc import AsyncIterator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.auth.jwt_tokens import verify_access_token
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import account_has_role


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


async def require_superadmin(account: Account = Depends(current_account)) -> Account:
    if not account.is_superadmin:
        raise HTTPException(status_code=403, detail="superadmin required")
    return account


def require_tenant_role(roles: tuple[str, ...] = ("owner", "admin")):
    """Dependency factory that authorizes tenant-scoped routes.

    Reads the route's ``tenant_id`` path parameter and verifies the current
    account holds at least one of *roles* for that tenant.  Superadmins bypass
    the check entirely.

    Usage::

        account: Account = Depends(require_tenant_role(("owner", "admin")))
    """

    async def _dep(
        tenant_id: int,
        account: Account = Depends(current_account),
        session: AsyncSession = Depends(get_session),
    ) -> Account:
        if account.is_superadmin:
            return account
        if account.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="forbidden")
        for role in roles:
            if await account_has_role(session, tenant_id=tenant_id, account_id=account.id, role=role):
                return account
        raise HTTPException(status_code=403, detail="insufficient role")

    return _dep
