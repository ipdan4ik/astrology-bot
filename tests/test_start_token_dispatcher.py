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


async def test_dispatch_unknown_kind_is_silent(session: AsyncSession):
    t = await _tenant(session)
    aid = await _account(session, t.id, 1001)
    referee = await _account(session, t.id, 2001)
    token = StartToken(
        code="FUTUREXX",
        kind="future_kind",
        tenant_id=t.id,
        owner_account_id=aid,
        status="active",
    )
    session.add(token)
    await session.flush()

    await dispatch_start_token(session, token=token, account_id=referee)

    uses = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.account_id == referee)
        )
    ).scalars().all()
    assert uses == []


# ---------------------------------------------------------------------------
# Gift dispatcher tests
# ---------------------------------------------------------------------------
import pytest

from quantuum.bot.handlers.start_tokens import GiftClaimResult
from quantuum.db.models import AccountBalance, AuditLog
from quantuum.domain.gifts import GIFT_KIND, create_gift


async def _account_with_credits(session, tenant_id, tg, credits):
    from quantuum.auth.identity import find_or_create_account_by_tg
    acc = await find_or_create_account_by_tg(
        session, tenant_id=tenant_id, tg_user_id=tg
    )
    bal = await session.get(AccountBalance, acc.id)
    bal.package_credits = credits
    await session.flush()
    return acc


async def test_dispatch_gift_claim_credits_recipient(session):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    recipient = await _account_with_credits(session, t.id, "2001", 0)
    tok = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=20
    )
    resolved = await resolve_start_token(session, code=tok.code, tenant_id=t.id)

    result = await dispatch_start_token(
        session, token=resolved, account_id=recipient.id
    )

    assert isinstance(result, GiftClaimResult)
    assert result.amount == 20

    bal = await session.get(AccountBalance, recipient.id)
    assert bal.package_credits == 20

    reloaded = await session.get(StartToken, tok.code)
    assert reloaded.status == "claimed"
    assert reloaded.used_count == 1

    use = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.token_code == tok.code)
        )
    ).scalars().one()
    assert use.claimed_at is not None

    audit = (
        await session.execute(select(AuditLog).where(AuditLog.action == "gift.claimed"))
    ).scalars().one()
    assert audit.payload_jsonb["code"] == tok.code
    assert audit.payload_jsonb["amount"] == 20


async def test_dispatch_gift_self_claim_silent(session):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    tok = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=20
    )
    resolved = await resolve_start_token(session, code=tok.code, tenant_id=t.id)

    result = await dispatch_start_token(
        session, token=resolved, account_id=sender.id
    )

    assert result is None
    reloaded = await session.get(StartToken, tok.code)
    assert reloaded.status == "active"
    audit = (
        await session.execute(
            select(AuditLog).where(AuditLog.action == "gift.self_blocked")
        )
    ).scalars().one()
    assert audit.payload_jsonb["code"] == tok.code


async def test_dispatch_gift_malformed_payload_silent(session):
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    recipient = await _account_with_credits(session, t.id, "2001", 0)
    bad = StartToken(
        code="GIFTBAD1", kind=GIFT_KIND, tenant_id=t.id,
        owner_account_id=sender.id, payload={"amount": 0},
        status="active", max_uses=1,
    )
    session.add(bad)
    await session.flush()
    resolved = await resolve_start_token(session, code=bad.code, tenant_id=t.id)

    result = await dispatch_start_token(
        session, token=resolved, account_id=recipient.id
    )

    assert result is None
    bal = await session.get(AccountBalance, recipient.id)
    assert bal.package_credits == 0
    reloaded = await session.get(StartToken, bad.code)
    assert reloaded.status == "active"  # untouched


async def test_dispatch_gift_double_claim_aborts_second(session):
    """Sequential second claim sees status='claimed' and bails out."""
    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    r1 = await _account_with_credits(session, t.id, "2001", 0)
    r2 = await _account_with_credits(session, t.id, "3001", 0)
    tok = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=20
    )

    resolved1 = await resolve_start_token(session, code=tok.code, tenant_id=t.id)
    result1 = await dispatch_start_token(session, token=resolved1, account_id=r1.id)
    assert isinstance(result1, GiftClaimResult)

    stale = await session.get(StartToken, tok.code)
    stale.status = "active"
    result2 = await dispatch_start_token(session, token=stale, account_id=r2.id)
    assert result2 is None
    bal_r2 = await session.get(AccountBalance, r2.id)
    assert bal_r2.package_credits == 0


@pytest.mark.skip(reason="enabled after T5 adds gifts to FEATURE_KEYS")
async def test_dispatch_gift_feature_flag_off_silent(session):
    from quantuum.domain.tenant_features import set_feature_enabled

    t = await _tenant(session)
    sender = await _account_with_credits(session, t.id, "1001", 100)
    recipient = await _account_with_credits(session, t.id, "2001", 0)
    tok = await create_gift(
        session, sender_account_id=sender.id, tenant_id=t.id, amount=20
    )
    await set_feature_enabled(
        session,
        tenant_id=t.id,
        key="gifts",
        enabled=False,
        by_account_id=sender.id,
    )
    await session.flush()

    resolved = await resolve_start_token(session, code=tok.code, tenant_id=t.id)
    result = await dispatch_start_token(
        session, token=resolved, account_id=recipient.id
    )
    assert result is None
    bal = await session.get(AccountBalance, recipient.id)
    assert bal.package_credits == 0
