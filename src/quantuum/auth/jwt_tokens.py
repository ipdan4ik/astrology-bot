import hashlib
from datetime import timedelta

import jwt
from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.common.exceptions import NotFoundError
from quantuum.common.ids import url_safe_token
from quantuum.db.models import Account, AccountRefreshToken
from quantuum.settings import get_settings

_ALG = "HS256"


def issue_access_token(account_id: int, tenant_id: int | None, is_superadmin: bool = False) -> str:
    settings = get_settings()
    now = utcnow()
    payload = {
        "sub": str(account_id),
        "tid": tenant_id,
        "sa": is_superadmin,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_access_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=_ALG)


def verify_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_signing_key, algorithms=[_ALG])


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_refresh_token(session, account_id: int) -> str:
    settings = get_settings()
    token = url_safe_token()
    row = AccountRefreshToken(
        account_id=account_id,
        token_hash=_hash(token),
        expires_at=utcnow() + timedelta(seconds=settings.jwt_refresh_ttl_seconds),
    )
    session.add(row)
    await session.commit()
    return token


async def _load_active(session, token: str) -> AccountRefreshToken:
    result = await session.execute(
        select(AccountRefreshToken).where(AccountRefreshToken.token_hash == _hash(token))
    )
    row = result.scalar_one_or_none()
    if row is None or row.revoked_at is not None or row.expires_at < utcnow():
        raise NotFoundError("refresh token invalid")
    return row


async def consume_refresh_token(session, token: str) -> Account:
    row = await _load_active(session, token)
    account = await session.get(Account, row.account_id)
    if account is None:
        raise NotFoundError("account not found")
    return account


async def _revoke_all_for_account(session, account_id: int) -> None:
    from sqlalchemy import update
    await session.execute(
        update(AccountRefreshToken)
        .where(
            AccountRefreshToken.account_id == account_id,
            AccountRefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )
    await session.commit()


async def rotate_refresh_token(session, token: str) -> tuple[Account, str]:
    """Validate a refresh token, revoke it, and issue a fresh one.

    Reuse of an already-consumed (revoked) token revokes the entire chain for
    that account and raises — a presented-but-revoked token signals theft.
    """
    result = await session.execute(
        select(AccountRefreshToken).where(AccountRefreshToken.token_hash == _hash(token))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError("refresh token invalid")
    if row.revoked_at is not None:
        await _revoke_all_for_account(session, row.account_id)
        raise NotFoundError("refresh token reuse detected")
    if row.expires_at < utcnow():
        raise NotFoundError("refresh token expired")
    account = await session.get(Account, row.account_id)
    if account is None:
        raise NotFoundError("account not found")
    row.revoked_at = utcnow()
    session.add(row)
    new_token = await issue_refresh_token(session, account.id)  # commits both rows
    return account, new_token


async def revoke_refresh_token(session, token: str) -> None:
    result = await session.execute(
        select(AccountRefreshToken).where(AccountRefreshToken.token_hash == _hash(token))
    )
    row = result.scalar_one_or_none()
    if row is not None:
        row.revoked_at = utcnow()
        session.add(row)
        await session.commit()
