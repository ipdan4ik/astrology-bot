from datetime import timedelta

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.start_tokens import (
    dispatch_start_token,
    parse_start_payload,
    resolve_start_token,
)
from quantuum.common.datetime import utcnow
from quantuum.db.models import AuditLog, StartToken, StartTokenUse, Tenant
from quantuum.domain.referrals import generate_referral_code


async def _tenant(session) -> Tenant:
    t = Tenant(slug="t1", display_name="T1")
    session.add(t)
    await session.flush()
    return t


async def _account(session, tenant_id: int, tg_id: int) -> int:
    acct = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=str(tg_id)
    )
    return acct.id


def test_parse_start_payload_extracts_code():
    assert parse_start_payload("/start ABC23K7Q") == "ABC23K7Q"
    assert parse_start_payload("/start  ABC23K7Q  ") == "ABC23K7Q"
    assert parse_start_payload("/start") is None
    assert parse_start_payload("/start ") is None
    assert parse_start_payload("") is None
    assert parse_start_payload(None) is None


def test_parse_start_payload_rejects_oversize():
    long = "X" * 65
    assert parse_start_payload(f"/start {long}") is None


async def test_resolve_start_token_returns_active(session: AsyncSession):
    t = await _tenant(session)
    aid = await _account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    token = await resolve_start_token(session, code=code, tenant_id=t.id)
    assert token is not None
    assert token.code == code


async def test_resolve_start_token_unknown(session: AsyncSession):
    t = await _tenant(session)
    token = await resolve_start_token(session, code="NOPE0000", tenant_id=t.id)
    assert token is None


async def test_resolve_start_token_wrong_tenant(session: AsyncSession):
    t1 = await _tenant(session)
    t2 = Tenant(slug="t2", display_name="T2")
    session.add(t2)
    await session.flush()
    aid = await _account(session, t1.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t1.id)
    assert await resolve_start_token(session, code=code, tenant_id=t2.id) is None


async def test_resolve_start_token_disabled(session: AsyncSession):
    t = await _tenant(session)
    aid = await _account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    tok = await session.get(StartToken, code)
    tok.status = "disabled"
    await session.flush()
    assert await resolve_start_token(session, code=code, tenant_id=t.id) is None


async def test_resolve_start_token_expired(session: AsyncSession):
    t = await _tenant(session)
    aid = await _account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    tok = await session.get(StartToken, code)
    tok.expires_at = utcnow() - timedelta(seconds=1)
    await session.flush()
    assert await resolve_start_token(session, code=code, tenant_id=t.id) is None


async def test_resolve_start_token_maxed(session: AsyncSession):
    t = await _tenant(session)
    aid = await _account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    tok = await session.get(StartToken, code)
    tok.max_uses = 1
    tok.used_count = 1
    await session.flush()
    assert await resolve_start_token(session, code=code, tenant_id=t.id) is None


async def test_dispatch_referral_records_use(session: AsyncSession):
    t = await _tenant(session)
    referrer = await _account(session, t.id, 1001)
    referee = await _account(session, t.id, 2001)
    code = await generate_referral_code(session, account_id=referrer, tenant_id=t.id)
    token = await resolve_start_token(session, code=code, tenant_id=t.id)

    await dispatch_start_token(session, token=token, account_id=referee)

    use = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == referee)
        )
    ).scalars().one()
    assert use.token_code == code
    assert use.claimed_at is None

    tok = await session.get(StartToken, code)
    assert tok.used_count == 1

    audit = (
        await session.execute(select(AuditLog).where(AuditLog.action == "referral.attributed"))
    ).scalars().all()
    assert len(audit) == 1


async def test_dispatch_referral_self_referral_silent(session: AsyncSession):
    t = await _tenant(session)
    aid = await _account(session, t.id, 1001)
    code = await generate_referral_code(session, account_id=aid, tenant_id=t.id)
    token = await resolve_start_token(session, code=code, tenant_id=t.id)

    await dispatch_start_token(session, token=token, account_id=aid)

    uses = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == aid)
        )
    ).scalars().all()
    assert uses == []


async def test_dispatch_referral_already_attributed_silent(session: AsyncSession):
    t = await _tenant(session)
    r1 = await _account(session, t.id, 1001)
    r2 = await _account(session, t.id, 1002)
    referee = await _account(session, t.id, 2001)
    code1 = await generate_referral_code(session, account_id=r1, tenant_id=t.id)
    code2 = await generate_referral_code(session, account_id=r2, tenant_id=t.id)
    tok1 = await resolve_start_token(session, code=code1, tenant_id=t.id)
    tok2 = await resolve_start_token(session, code=code2, tenant_id=t.id)

    await dispatch_start_token(session, token=tok1, account_id=referee)
    await dispatch_start_token(session, token=tok2, account_id=referee)

    uses = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == referee)
        )
    ).scalars().all()
    assert len(uses) == 1
    assert uses[0].token_code == code1
