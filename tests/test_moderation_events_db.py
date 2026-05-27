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


@pytest.mark.asyncio
async def test_record_moderation_event_computes_hash_and_preview(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.domain.moderation import record_moderation_event
    from quantuum.moderation.policy import Action, Category

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="43"
    )
    raw = "x" * 200  # longer than the 80-char preview cap
    ev = await record_moderation_event(
        session,
        account_id=acc.id,
        tenant_id=default_tenant.id,
        lang="ru",
        category=Category.SELF_HARM,
        action=Action.SOFT_REDIRECT,
        source="openai",
        raw_text=raw,
    )
    await session.commit()
    assert ev.id is not None
    assert ev.category == "self_harm"
    assert ev.action == "soft_redirect"
    assert ev.source == "openai"
    assert len(ev.text_preview) == 80
    assert ev.text_preview == "x" * 80
    assert len(ev.text_sha256) == 32

    import hashlib
    assert ev.text_sha256 == hashlib.sha256(raw.encode("utf-8")).digest()


@pytest.mark.asyncio
async def test_record_moderation_event_short_text_not_padded(session, default_tenant):
    from quantuum.auth.identity import find_or_create_account_by_tg
    from quantuum.domain.moderation import record_moderation_event
    from quantuum.moderation.policy import Action, Category

    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="44"
    )
    ev = await record_moderation_event(
        session,
        account_id=acc.id,
        tenant_id=default_tenant.id,
        lang="ru",
        category=Category.MEDICAL_ADVICE,
        action=Action.SOFT_REDIRECT,
        source="mini_llm",
        raw_text="short text",
    )
    await session.commit()
    assert ev.text_preview == "short text"  # no padding
