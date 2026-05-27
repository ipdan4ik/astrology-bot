import secrets
import string

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Payment,
    StartToken,
    StartTokenUse,
    TenantConfig,
)
from quantuum.domain.accounts import adjust_package_credits
from quantuum.domain.audit import record_audit
from quantuum.logging_setup import get_logger

logger = get_logger(__name__)

REFERRAL_KIND = "referral"
REFERRAL_CODE_LENGTH = 8
REFERRAL_REWARD_CONFIG_KEY = "referral.reward_credits"
DEFAULT_REWARD_CREDITS = 10
MAX_REWARD_CREDITS = 1000

_CODE_ALPHABET = string.ascii_uppercase + string.digits
_GEN_MAX_RETRIES = 5


def _gen_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(REFERRAL_CODE_LENGTH))


async def generate_referral_code(
    session: AsyncSession, *, account_id: int, tenant_id: int
) -> str:
    """Return the referral code owned by ``account_id``, creating one if absent."""
    existing = (
        await session.execute(
            select(StartToken).where(
                StartToken.kind == REFERRAL_KIND,
                StartToken.owner_account_id == account_id,
            )
        )
    ).scalars().first()
    if existing is not None:
        return existing.code

    for _ in range(_GEN_MAX_RETRIES):
        code = _gen_code()
        if (await session.get(StartToken, code)) is None:
            token = StartToken(
                code=code,
                kind=REFERRAL_KIND,
                tenant_id=tenant_id,
                owner_account_id=account_id,
                status="active",
            )
            session.add(token)
            await session.flush()
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_account_id=account_id,
                action="referral.code_created",
                entity_type="start_token",
                entity_id=code,
                payload={"code": code},
            )
            return code
    logger.warning(
        "referral.code_collision_exhausted",
        account_id=account_id,
        tenant_id=tenant_id,
    )
    raise RuntimeError("could not generate unique referral code after retries")


async def get_referral_stats(
    session: AsyncSession, *, account_id: int
) -> dict[str, int | str | None]:
    """Return {code, claimed, pending} for the account's referral code."""
    token = (
        await session.execute(
            select(StartToken).where(
                StartToken.kind == REFERRAL_KIND,
                StartToken.owner_account_id == account_id,
            )
        )
    ).scalars().first()
    if token is None:
        return {"code": None, "claimed": 0, "pending": 0}

    rows = (
        await session.execute(
            select(StartTokenUse).where(StartTokenUse.token_code == token.code)
        )
    ).scalars().all()
    claimed = sum(1 for r in rows if r.claimed_at is not None)
    pending = sum(1 for r in rows if r.claimed_at is None)
    return {"code": token.code, "claimed": claimed, "pending": pending}


async def get_reward_credits(session: AsyncSession, *, tenant_id: int) -> int:
    row = await session.get(TenantConfig, (tenant_id, REFERRAL_REWARD_CONFIG_KEY))
    if row is None:
        return DEFAULT_REWARD_CREDITS
    value = row.value_jsonb.get("value")
    if not isinstance(value, int):
        return DEFAULT_REWARD_CREDITS
    return value


async def set_reward_credits(
    session: AsyncSession,
    *,
    tenant_id: int,
    value: int,
    by_account_id: int,
) -> None:
    if not isinstance(value, int) or value < 0 or value > MAX_REWARD_CREDITS:
        raise ValueError(f"value must be int in [0, {MAX_REWARD_CREDITS}], got {value!r}")
    old = await get_reward_credits(session, tenant_id=tenant_id)
    row = await session.get(TenantConfig, (tenant_id, REFERRAL_REWARD_CONFIG_KEY))
    if row is None:
        row = TenantConfig(
            tenant_id=tenant_id,
            key=REFERRAL_REWARD_CONFIG_KEY,
            value_jsonb={"value": value},
            updated_by_account_id=by_account_id,
        )
        session.add(row)
    else:
        row.value_jsonb = {"value": value}
        row.updated_by_account_id = by_account_id
        row.updated_at = utcnow()
    await session.flush()
    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=by_account_id,
        action="referral.config_set",
        entity_type="tenant_config",
        entity_id=REFERRAL_REWARD_CONFIG_KEY,
        payload={"old": old, "new": value},
    )


async def reset_reward_credits(
    session: AsyncSession, *, tenant_id: int, by_account_id: int
) -> None:
    row = await session.get(TenantConfig, (tenant_id, REFERRAL_REWARD_CONFIG_KEY))
    if row is None:
        return
    old = row.value_jsonb.get("value", DEFAULT_REWARD_CREDITS)
    await session.delete(row)
    await session.flush()
    await record_audit(
        session,
        tenant_id=tenant_id,
        actor_account_id=by_account_id,
        action="referral.config_set",
        entity_type="tenant_config",
        entity_id=REFERRAL_REWARD_CONFIG_KEY,
        payload={"old": old, "new": DEFAULT_REWARD_CREDITS, "reset": True},
    )


async def maybe_payout_referral(
    session: AsyncSession, *, referee_account_id: int
) -> bool:
    """Fire the referrer payout when referee has both a paid Payment and an
    unclaimed attribution. Returns True iff a use row was just closed.

    Caller must wrap in try/except — payout errors must not roll back the
    spend that triggered us.
    """
    use = (
        await session.execute(
            select(StartTokenUse).where(
                StartTokenUse.account_id == referee_account_id,
                StartTokenUse.claimed_at.is_(None),
            )
        )
    ).scalars().first()
    if use is None:
        return False

    token = await session.get(StartToken, use.token_code)
    if token is None or token.kind != REFERRAL_KIND or token.owner_account_id is None:
        return False

    has_paid = (
        await session.execute(
            select(
                exists().where(
                    Payment.account_id == referee_account_id,
                    Payment.status == "paid",
                )
            )
        )
    ).scalar()
    if not has_paid:
        return False

    amount = await get_reward_credits(session, tenant_id=token.tenant_id)
    if amount > 0:
        await adjust_package_credits(session, token.owner_account_id, amount)
    use.claimed_at = utcnow()
    session.add(use)
    await session.flush()
    await record_audit(
        session,
        tenant_id=token.tenant_id,
        actor_account_id=token.owner_account_id,
        action="referral.payout",
        entity_type="start_token_use",
        entity_id=use.id,
        payload={
            "referee_id": referee_account_id,
            "referrer_id": token.owner_account_id,
            "amount": amount,
            "code": token.code,
        },
    )
    return True
