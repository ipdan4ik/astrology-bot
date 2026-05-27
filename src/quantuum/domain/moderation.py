import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from quantuum.db.models import ModerationEvent
from quantuum.moderation.policy import Action, Category

_PREVIEW_MAX = 80


async def record_moderation_event(
    session: AsyncSession,
    *,
    account_id: int | None,
    tenant_id: int,
    lang: str | None,
    category: Category,
    action: Action,
    source: str,
    raw_text: str,
) -> ModerationEvent:
    """Persist a moderation event with sha256(raw) and an 80-char preview.

    Raw text is NOT stored. Caller controls commit boundary.
    """
    digest = hashlib.sha256(raw_text.encode("utf-8")).digest()
    preview = raw_text[:_PREVIEW_MAX]
    ev = ModerationEvent(
        account_id=account_id,
        tenant_id=tenant_id,
        lang=lang,
        category=category.value,
        action=action.value,
        source=source,
        text_sha256=digest,
        text_preview=preview,
    )
    session.add(ev)
    await session.flush()
    return ev
