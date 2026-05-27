import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import ModerationEvent, QaAnswer, Reading, Request
from quantuum.domain.natal_profiles import upsert_natal_profile
from quantuum.domain.tenant_features import set_feature_enabled
from tests.conftest import build_translator


async def _setup_account(session, tenant_id, *, tg="ft1"):
    from datetime import date, time
    from decimal import Decimal

    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg)
    await upsert_natal_profile(
        session, tenant_id=tenant_id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    await session.commit()
    return acc


async def _disable(session, tenant_id, key, *, by):
    await set_feature_enabled(
        session,
        tenant_id=tenant_id,
        key=key,
        enabled=False,
        by_account_id=by,
    )
    await session.commit()


def _make_message():
    msg = MagicMock()
    msg.answer = AsyncMock()
    msg.chat.id = 12345
    return msg


# ---------- QA ----------


async def test_qa_disabled_short_circuits(session, default_tenant, monkeypatch):
    acc = await _setup_account(session, default_tenant.id, tg="qa_off")
    await _disable(session, default_tenant.id, "qa", by=acc.id)

    from quantuum.bot.handlers import qa as qa_handler

    # Force moderation off — we're testing the feature gate runs FIRST.
    monkeypatch.setattr(
        qa_handler,
        "get_settings",
        lambda: SimpleNamespace(
            moderation_enabled=False,
            moderation_fail_open=True,
            llm_api_key="",
            llm_provider="openai",
        ),
    )
    monkeypatch.setattr(qa_handler, "enqueue_qa", AsyncMock())

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()
    await qa_handler._submit(msg, "any question", acc, i18n)

    qa_rows = (await session.execute(select(QaAnswer))).scalars().all()
    me_rows = (await session.execute(select(ModerationEvent))).scalars().all()
    req_rows = (await session.execute(select(Request))).scalars().all()
    assert qa_rows == []
    assert me_rows == []
    assert req_rows == []
    msg.answer.assert_awaited_once()
    sent = msg.answer.await_args.args[0]
    # i18n key feature.disabled_generic resolves to RU "Эта функция отключена в этом боте."
    assert "отключена" in sent.lower() or "available" in sent.lower()


# ---------- Blueprint / generate ----------


async def test_blueprint_disabled_short_circuits(session, default_tenant, monkeypatch):
    acc = await _setup_account(session, default_tenant.id, tg="bp_off")
    await _disable(session, default_tenant.id, "blueprint", by=acc.id)

    from quantuum.bot.handlers import generate as gen_handler

    monkeypatch.setattr(gen_handler, "enqueue_blueprint", AsyncMock())

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()
    await gen_handler.run_generate(msg, acc, 12345, i18n)

    req_rows = (await session.execute(select(Request))).scalars().all()
    assert req_rows == []
    msg.answer.assert_awaited_once()
    sent = msg.answer.await_args.args[0]
    assert "отключена" in sent.lower() or "available" in sent.lower()


# ---------- Transits ----------


async def test_transits_disabled_short_circuits(session, default_tenant, monkeypatch):
    acc = await _setup_account(session, default_tenant.id, tg="tr_off")
    await _disable(session, default_tenant.id, "transits", by=acc.id)

    from quantuum.bot.handlers import transits as tr_handler

    monkeypatch.setattr(tr_handler, "enqueue_transit", AsyncMock())

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()
    await tr_handler.run_transits(msg, None, acc, i18n)

    req_rows = (await session.execute(select(Request))).scalars().all()
    assert req_rows == []
    msg.answer.assert_awaited_once()
    sent = msg.answer.await_args.args[0]
    assert "отключена" in sent.lower() or "available" in sent.lower()


# ---------- Daily ----------


async def test_daily_disabled_short_circuits(session, default_tenant, monkeypatch):
    acc = await _setup_account(session, default_tenant.id, tg="d_off")
    await _disable(session, default_tenant.id, "daily", by=acc.id)

    from quantuum.bot.handlers import daily as d_handler

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()
    await d_handler.run_daily_settings(msg, acc, i18n)

    msg.answer.assert_awaited_once()
    sent = msg.answer.await_args.args[0]
    assert "отключена" in sent.lower() or "available" in sent.lower()


# ---------- Positive-path (gate must NOT block) ----------


async def test_qa_enabled_does_not_block(session, default_tenant, monkeypatch):
    # All features default ON — gate must not short-circuit.
    acc = await _setup_account(session, default_tenant.id, tg="qa_on_positive")

    from quantuum.bot.handlers import qa as qa_handler

    monkeypatch.setattr(
        qa_handler,
        "get_settings",
        lambda: SimpleNamespace(
            moderation_enabled=False,  # moderation off, isolate the gate
            moderation_fail_open=True,
            llm_api_key="",
            llm_provider="openai",
        ),
    )
    monkeypatch.setattr(qa_handler, "enqueue_qa", AsyncMock())

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()
    await qa_handler._submit(msg, "what does my chart say?", acc, i18n)

    # The disabled message MUST NOT have been sent.
    for call in msg.answer.await_args_list:
        text = call.args[0] if call.args else ""
        assert "отключена" not in text.lower(), f"Gate falsely blocked: {text!r}"


async def test_blueprint_enabled_does_not_block(session, default_tenant, monkeypatch):
    # All features default ON — gate must not short-circuit.
    acc = await _setup_account(session, default_tenant.id, tg="bp_on_positive")

    from quantuum.bot.handlers import generate as gen_handler

    monkeypatch.setattr(gen_handler, "enqueue_blueprint", AsyncMock())

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()
    await gen_handler.run_generate(msg, acc, 12345, i18n)

    # The disabled message MUST NOT have been sent.
    for call in msg.answer.await_args_list:
        text = call.args[0] if call.args else ""
        assert "отключена" not in text.lower(), f"Gate falsely blocked: {text!r}"


async def test_transits_enabled_does_not_block(session, default_tenant, monkeypatch):
    # All features default ON — gate must not short-circuit.
    acc = await _setup_account(session, default_tenant.id, tg="tr_on_positive")

    from quantuum.bot.handlers import transits as tr_handler

    monkeypatch.setattr(tr_handler, "enqueue_transit", AsyncMock())

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()
    await tr_handler.run_transits(msg, None, acc, i18n)

    # The disabled message MUST NOT have been sent.
    for call in msg.answer.await_args_list:
        text = call.args[0] if call.args else ""
        assert "отключена" not in text.lower(), f"Gate falsely blocked: {text!r}"


async def test_daily_enabled_does_not_block(session, default_tenant, monkeypatch):
    # All features default ON — gate must not short-circuit.
    acc = await _setup_account(session, default_tenant.id, tg="d_on_positive")

    from quantuum.bot.handlers import daily as d_handler

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    msg = _make_message()
    await d_handler.run_daily_settings(msg, acc, i18n)

    # The disabled message MUST NOT have been sent.
    for call in msg.answer.await_args_list:
        text = call.args[0] if call.args else ""
        assert "отключена" not in text.lower(), f"Gate falsely blocked: {text!r}"


# ---------- Readings per-kind ----------


@pytest.mark.parametrize(
    "kind", ["bazi", "numerology", "human_design", "astrology",
             "vedic", "gene_keys", "mayan", "aspects"],
)
async def test_reading_kind_disabled_short_circuits(
    session, default_tenant, monkeypatch, kind
):
    acc = await _setup_account(session, default_tenant.id, tg=f"r_{kind}_off")
    await _disable(session, default_tenant.id, f"reading.{kind}", by=acc.id)

    from quantuum.bot.handlers import readings as r_handler

    monkeypatch.setattr(r_handler, "enqueue_reading", AsyncMock())

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = MagicMock()
    query.message = MagicMock()
    query.message.answer = AsyncMock()
    query.message.chat = MagicMock()
    query.message.chat.id = 12345
    query.answer = AsyncMock()
    query.data = f"rdg:generate:{kind}"

    from quantuum.bot.ui.callbacks import ReadingCb

    monkeypatch.setattr(
        ReadingCb,
        "unpack",
        classmethod(
            lambda cls, data: SimpleNamespace(action="generate", kind=kind)
        ),
    )

    await r_handler.on_reading_choice(query, acc, i18n)

    reading_rows = (await session.execute(select(Reading))).scalars().all()
    assert reading_rows == []
    query.message.answer.assert_awaited_once()
    sent = query.message.answer.await_args.args[0]
    assert "отключена" in sent.lower() or "available" in sent.lower()


async def test_reading_kind_enabled_does_not_block(session, default_tenant, monkeypatch):
    # Pick one kind, leave it default ON, confirm gate doesn't fire.
    acc = await _setup_account(session, default_tenant.id, tg="r_on_positive")

    from quantuum.bot.handlers import readings as r_handler

    monkeypatch.setattr(r_handler, "enqueue_reading", AsyncMock())

    i18n = await build_translator(session, default_tenant.id, lang="ru")
    query = MagicMock()
    query.message = MagicMock()
    query.message.answer = AsyncMock()
    query.message.chat = MagicMock()
    query.message.chat.id = 12345
    query.answer = AsyncMock()
    query.data = "rdg:generate:bazi"

    from quantuum.bot.ui.callbacks import ReadingCb
    monkeypatch.setattr(
        ReadingCb,
        "unpack",
        classmethod(lambda cls, data: SimpleNamespace(action="generate", kind="bazi")),
    )

    await r_handler.on_reading_choice(query, acc, i18n)

    for call in query.message.answer.await_args_list:
        text = call.args[0] if call.args else ""
        assert "отключена" not in text.lower(), f"Gate falsely blocked: {text!r}"
