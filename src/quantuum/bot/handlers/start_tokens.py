from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.common.datetime import utcnow
from quantuum.db.models import StartToken, StartTokenUse
from quantuum.domain.audit import record_audit
from quantuum.domain.referrals import REFERRAL_KIND
from quantuum.logging_setup import get_logger

logger = get_logger(__name__)

_MAX_PAYLOAD_LEN = 64


def parse_start_payload(text: str | None) -> str | None:
    """Extract the deep-link payload from a `/start ...` message text.

    Returns None if no payload, empty payload, or payload exceeds Telegram's
    64-char cap (defensive guard).
    """
    if not text:
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None
    payload = parts[1].strip()
    if not payload or len(payload) > _MAX_PAYLOAD_LEN:
        return None
    return payload


async def resolve_start_token(
    session: AsyncSession, *, code: str, tenant_id: int
) -> StartToken | None:
    """Look up a start_token by code, scoped to tenant_id. Returns None if
    missing, wrong tenant, disabled, expired, or maxed-out.
    """
    token = await session.get(StartToken, code)
    if token is None or token.tenant_id != tenant_id:
        return None
    if token.status != "active":
        return None
    if token.expires_at is not None and token.expires_at <= utcnow():
        return None
    if token.max_uses is not None and token.used_count >= token.max_uses:
        return None
    return token


async def dispatch_start_token(
    session: AsyncSession, *, token: StartToken, account_id: int
) -> None:
    """Route a resolved token to its kind-specific handler. Unknown kinds
    log a warning and no-op so older bot builds never crash on future codes.
    """
    handler = _HANDLERS.get(token.kind)
    if handler is None:
        logger.warning("start_token.unknown_kind", kind=token.kind, code=token.code)
        return
    await handler(session, token=token, account_id=account_id)


async def handle_referral_token(
    session: AsyncSession, *, token: StartToken, account_id: int
) -> None:
    """Record a referral attribution. Silent no-op on self-referral and on
    accounts already attributed (UNIQUE constraint).
    """
    if token.owner_account_id == account_id:
        return
    existing = await session.execute(
        select(StartTokenUse).where(StartTokenUse.account_id == account_id)
    )
    if existing.scalars().one_or_none() is not None:
        return
    use = StartTokenUse(
        token_code=token.code,
        account_id=account_id,
        used_at=utcnow(),
    )
    session.add(use)
    await session.flush()
    token.used_count += 1
    session.add(token)
    await session.flush()
    await record_audit(
        session,
        tenant_id=token.tenant_id,
        actor_account_id=account_id,
        action="referral.attributed",
        entity_type="start_token_use",
        entity_id=use.id,
        payload={
            "referee_id": account_id,
            "referrer_id": token.owner_account_id,
            "code": token.code,
        },
    )


_HANDLERS = {
    REFERRAL_KIND: handle_referral_token,
}
