import hashlib

import pytest

from quantuum.auth import jwt_tokens
from quantuum.common.exceptions import NotFoundError


def test_access_token_roundtrip():
    token = jwt_tokens.issue_access_token(account_id=7, tenant_id=3)
    claims = jwt_tokens.verify_access_token(token)
    assert claims["sub"] == "7"
    assert claims["tid"] == 3


async def test_refresh_token_consume(session, default_tenant):
    from quantuum.db.models import Account

    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    token = await jwt_tokens.issue_refresh_token(session, acc.id)
    consumed = await jwt_tokens.consume_refresh_token(session, token)
    assert consumed.id == acc.id


async def test_refresh_token_revoked(session, default_tenant):
    from quantuum.db.models import Account

    acc = Account(tenant_id=default_tenant.id)
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    token = await jwt_tokens.issue_refresh_token(session, acc.id)
    await jwt_tokens.revoke_refresh_token(session, token)
    with pytest.raises(NotFoundError):
        await jwt_tokens.consume_refresh_token(session, token)
