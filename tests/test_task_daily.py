from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

from sqlmodel import select

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.common.datetime import utcnow
from quantuum.db.models import AccountBalance, DailyHoroscope, DailySubscription, NatalProfile
from quantuum.domain.daily import upsert_settings
from quantuum.llm.base import LLMResult
from quantuum.tasks.daily import daily_generate


class FakeLLM:
    async def complete(self, *, system, user, model, temperature, max_tokens):
        return LLMResult(text="DAILY BLURB", tokens_in=5, tokens_out=9, model="claude-test")


class _Maker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _Ctx(self._session)


class _Ctx:
    def __init__(self, s):
        self._s = s

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *a):
        return False


async def _setup(session, tenant_id, tg="42", *, subscriber=True, profile=True, enabled=True):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id=tg)
    if profile:
        session.add(NatalProfile(
            tenant_id=tenant_id, account_id=acc.id, full_name="Anna",
            birth_date=date(1990, 6, 15), birth_time=time(14, 30), birth_place="Moscow",
            latitude=Decimal("55.7558"), longitude=Decimal("37.6176"), timezone="Europe/Moscow",
        ))
    bal = await session.get(AccountBalance, acc.id)
    if bal is None:
        bal = AccountBalance(account_id=acc.id)
    bal.subscription_active_until = utcnow() + timedelta(days=30) if subscriber else None
    session.add(bal)
    await session.commit()
    if enabled:
        await upsert_settings(session, tenant_id=tenant_id, account_id=acc.id, enabled=True, send_hour=9)
    return acc


async def test_daily_generate_happy(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    deliver = AsyncMock()
    monkeypatch.setattr(daily_mod, "deliver_daily", deliver)
    acc = await _setup(session, default_tenant.id)

    ctx = {"sessionmaker": _Maker(session), "llm_client": FakeLLM()}
    await daily_generate(ctx, acc.id)

    rows = (await session.execute(select(DailyHoroscope).where(DailyHoroscope.account_id == acc.id))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "done"
    assert row.horoscope_md == "DAILY BLURB"
    assert row.transit_md and "Active now" in row.transit_md
    assert row.llm_tokens_in == 5 and row.llm_provider == "openai"
    settings = await session.get(DailySubscription, acc.id)
    assert settings.last_sent_on is not None
    deliver.assert_awaited_once()


async def test_daily_generate_already_sent_skips(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    deliver = AsyncMock()
    monkeypatch.setattr(daily_mod, "deliver_daily", deliver)
    acc = await _setup(session, default_tenant.id)
    acc_id = acc.id
    ctx = {"sessionmaker": _Maker(session), "llm_client": FakeLLM()}

    await daily_generate(ctx, acc_id)
    await daily_generate(ctx, acc_id)  # second call same day -> claim returns None

    # The duplicate claim_horoscope rolls back the shared test session, which expires
    # the identity-mapped rows; drop them so the assertion query loads fresh state.
    session.expunge_all()
    rows = (await session.execute(select(DailyHoroscope).where(DailyHoroscope.account_id == acc_id))).scalars().all()
    assert len(rows) == 1
    deliver.assert_awaited_once()


async def test_daily_generate_not_subscriber_skips(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    deliver = AsyncMock()
    monkeypatch.setattr(daily_mod, "deliver_daily", deliver)
    acc = await _setup(session, default_tenant.id, subscriber=False)
    ctx = {"sessionmaker": _Maker(session), "llm_client": FakeLLM()}

    await daily_generate(ctx, acc.id)
    rows = (await session.execute(select(DailyHoroscope))).scalars().all()
    assert rows == []
    deliver.assert_not_awaited()


async def test_daily_generate_no_profile_skips(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    deliver = AsyncMock()
    monkeypatch.setattr(daily_mod, "deliver_daily", deliver)
    acc = await _setup(session, default_tenant.id, profile=False)
    ctx = {"sessionmaker": _Maker(session), "llm_client": FakeLLM()}

    await daily_generate(ctx, acc.id)
    assert (await session.execute(select(DailyHoroscope))).scalars().first() is None
    deliver.assert_not_awaited()


async def test_daily_generate_llm_failure_marks_failed_no_delivery(session, default_tenant, monkeypatch):
    from quantuum.tasks import daily as daily_mod

    deliver = AsyncMock()
    monkeypatch.setattr(daily_mod, "deliver_daily", deliver)
    acc = await _setup(session, default_tenant.id)
    ctx = {"sessionmaker": _Maker(session), "llm_client": None}  # no LLM -> failure path

    await daily_generate(ctx, acc.id)
    row = (await session.execute(select(DailyHoroscope).where(DailyHoroscope.account_id == acc.id))).scalars().first()
    assert row.status == "failed"
    settings = await session.get(DailySubscription, acc.id)
    assert settings.last_sent_on is not None  # day skipped even on failure
    deliver.assert_not_awaited()
