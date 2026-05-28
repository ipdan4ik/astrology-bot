import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    AccountBalance,
    StartToken,
    StartTokenUse,
    TenantConfig,
)
from quantuum.domain.audit import record_audit
from quantuum.logging_setup import get_logger

logger = get_logger(__name__)

GIFT_KIND = "gift"
GIFT_CODE_LENGTH = 8
MAX_GIFT_AMOUNT = 1000
MIN_GIFT_AMOUNT = 1

GIFT_EXPIRY_CONFIG_KEY = "gift.expiry_days"
DEFAULT_EXPIRY_DAYS = 30
MIN_EXPIRY_DAYS = 1
MAX_EXPIRY_DAYS = 365

_CODE_ALPHABET = string.ascii_uppercase + string.digits
_GEN_MAX_RETRIES = 5


class InsufficientCreditsError(Exception):
    """Sender does not have enough package_credits to create the gift."""


@dataclass
class GiftRow:
    code: str
    amount: int
    status: str  # active | claimed | refunded
    expires_at: datetime | None
    claimed_at: datetime | None
    created_at: datetime


def _gen_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(GIFT_CODE_LENGTH))


async def _generate_gift_code(session: AsyncSession) -> str:
    for _ in range(_GEN_MAX_RETRIES):
        code = _gen_code()
        if (await session.get(StartToken, code)) is None:
            return code
    logger.warning("gift.code_collision_exhausted")
    raise RuntimeError("could not generate unique gift code after retries")


async def get_expiry_days(session: AsyncSession, *, tenant_id: int) -> int:
    row = await session.get(TenantConfig, (tenant_id, GIFT_EXPIRY_CONFIG_KEY))
    if row is None:
        return DEFAULT_EXPIRY_DAYS
    value = row.value_jsonb.get("value")
    if not isinstance(value, int):
        return DEFAULT_EXPIRY_DAYS
    return value


async def set_expiry_days(
    session: AsyncSession,
    *,
    tenant_id: int,
    days: int,
    by_account_id: int,
) -> None:
    if not isinstance(days, int) or days < MIN_EXPIRY_DAYS or days > MAX_EXPIRY_DAYS:
        raise ValueError(
            f"days must be int in [{MIN_EXPIRY_DAYS}, {MAX_EXPIRY_DAYS}], got {days!r}"
        )
    old = await get_expiry_days(session, tenant_id=tenant_id)
    row = await session.get(TenantConfig, (tenant_id, GIFT_EXPIRY_CONFIG_KEY))
    if row is None:
        row = TenantConfig(
            tenant_id=tenant_id,
            key=GIFT_EXPIRY_CONFIG_KEY,
            value_jsonb={"value": days},
            updated_by_account_id=by_account_id,
        )
        session.add(row)
    else:
        row.value_jsonb = {"value": days}
        row.updated_by_account_id = by_account_id
        row.updated_at = utcnow()
    await session.flush()
    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=by_account_id,
        action="gift.config_set",
        entity_type="tenant_config",
        entity_id=GIFT_EXPIRY_CONFIG_KEY,
        payload={"old": old, "new": days},
    )


async def reset_expiry_days(
    session: AsyncSession, *, tenant_id: int, by_account_id: int
) -> None:
    row = await session.get(TenantConfig, (tenant_id, GIFT_EXPIRY_CONFIG_KEY))
    if row is None:
        return
    old = row.value_jsonb.get("value", DEFAULT_EXPIRY_DAYS)
    await session.delete(row)
    await session.flush()
    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=by_account_id,
        action="gift.config_set",
        entity_type="tenant_config",
        entity_id=GIFT_EXPIRY_CONFIG_KEY,
        payload={"old": old, "new": DEFAULT_EXPIRY_DAYS, "reset": True},
    )


async def create_gift(
    session: AsyncSession,
    *,
    sender_account_id: int,
    tenant_id: int,
    amount: int,
) -> StartToken:
    if not isinstance(amount, int) or amount < MIN_GIFT_AMOUNT or amount > MAX_GIFT_AMOUNT:
        raise ValueError(
            f"amount must be int in [{MIN_GIFT_AMOUNT}, {MAX_GIFT_AMOUNT}], got {amount!r}"
        )

    bal = await session.get(AccountBalance, sender_account_id)
    if bal is None or bal.package_credits < amount:
        raise InsufficientCreditsError(
            f"sender {sender_account_id} has "
            f"{0 if bal is None else bal.package_credits} credits, gift needs {amount}"
        )

    days = await get_expiry_days(session, tenant_id=tenant_id)
    code = await _generate_gift_code(session)

    bal.package_credits -= amount
    token = StartToken(
        code=code,
        kind=GIFT_KIND,
        tenant_id=tenant_id,
        owner_account_id=sender_account_id,
        payload={"amount": amount},
        status="active",
        max_uses=1,
        used_count=0,
        expires_at=utcnow() + timedelta(days=days),
    )
    session.add(token)
    await session.flush()
    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=sender_account_id,
        action="gift.created",
        entity_type="start_token",
        entity_id=code,
        payload={"code": code, "amount": amount, "tenant_id": tenant_id},
    )
    return token


async def list_recent_gifts(
    session: AsyncSession, *, sender_account_id: int, limit: int = 10
) -> list[GiftRow]:
    rows = (
        await session.execute(
            select(StartToken)
            .where(
                StartToken.kind == GIFT_KIND,
                StartToken.owner_account_id == sender_account_id,
            )
            .order_by(StartToken.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    claim_by_code: dict[str, datetime | None] = {}
    if rows:
        codes = [r.code for r in rows]
        for use in (
            await session.execute(
                select(StartTokenUse).where(StartTokenUse.token_code.in_(codes))
            )
        ).scalars().all():
            claim_by_code[use.token_code] = use.claimed_at

    out: list[GiftRow] = []
    for tok in rows:
        amount = int(tok.payload.get("amount", 0))
        out.append(
            GiftRow(
                code=tok.code,
                amount=amount,
                status=tok.status,
                expires_at=tok.expires_at,
                claimed_at=claim_by_code.get(tok.code),
                created_at=tok.created_at,
            )
        )
    return out


async def sweep_expired_gifts(
    session: AsyncSession, *, sender_account_id: int
) -> int:
    now = utcnow()
    candidates = (
        await session.execute(
            select(StartToken).where(
                StartToken.kind == GIFT_KIND,
                StartToken.owner_account_id == sender_account_id,
                StartToken.status == "active",
                StartToken.expires_at.is_not(None),
                StartToken.expires_at <= now,
            )
        )
    ).scalars().all()
    if not candidates:
        return 0

    bal = await session.get(AccountBalance, sender_account_id)
    refunded = 0
    for tok in candidates:
        amount = int(tok.payload.get("amount", 0))
        if amount <= 0:
            tok.status = "refunded"
            continue
        bal.package_credits += amount
        tok.status = "refunded"
        await record_audit(
            session,
            tenant_id=tok.tenant_id,
            actor_account_id=sender_account_id,
            action="gift.refunded",
            entity_type="start_token",
            entity_id=tok.code,
            payload={"code": tok.code, "amount": amount, "reason": "expired"},
        )
        refunded += 1
    await session.flush()
    return refunded
