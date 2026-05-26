import pytest
from sqlalchemy import select

from quantuum.db.models import ModerationEvent


@pytest.mark.asyncio
async def test_moderation_event_row_persists(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="42"
    )
    ev = ModerationEvent(
        account_id=acc.id,
        tenant_id=default_tenant.id,
        lang="ru",
        category="self_harm",
        action="soft_redirect",
        source="openai",
        text_sha256=b"\x00" * 32,
        text_preview="hello world",
    )
    session.add(ev)
    await session.commit()

    rows = (await session.execute(select(ModerationEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].category == "self_harm"
    assert rows[0].action == "soft_redirect"
    assert rows[0].source == "openai"
    assert rows[0].text_sha256 == b"\x00" * 32
    assert rows[0].text_preview == "hello world"
    assert rows[0].created_at is not None
