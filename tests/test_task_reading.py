from datetime import date, time
from decimal import Decimal

import pytest

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import NatalProfile
from quantuum.domain.readings import create_reading, get_reading


class _Result:
    def __init__(self, text="POLISHED"):
        self.text = text
        self.model = "m"
        self.tokens_in = 10
        self.tokens_out = 20


class _FakeLLM:
    async def complete(self, **kw):
        return _Result()


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


async def _setup(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="t1"
    )
    p = NatalProfile(
        tenant_id=default_tenant.id,
        account_id=acc.id,
        full_name="X",
        birth_date=date(1990, 1, 1),
        birth_time=time(12, 0),
        birth_place="X",
        latitude=Decimal("0"),
        longitude=Decimal("0"),
        timezone="UTC",
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return acc, p


async def test_reading_generate_happy_path(session, default_tenant):
    from quantuum.tasks.reading import reading_generate

    acc, prof = await _setup(session, default_tenant)
    r = await create_reading(
        session,
        tenant_id=default_tenant.id,
        account_id=acc.id,
        natal_profile_id=prof.id,
        kind="bazi",
        lang="en",
    )
    rid = r.id

    ctx = {"sessionmaker": _Maker(session), "llm_client": _FakeLLM()}
    await reading_generate(ctx, rid, chat_id=None, request_id=None)

    r2 = await get_reading(session, rid)
    await session.refresh(r2)
    assert r2.status == "done"
    assert r2.llm_md == "POLISHED"
    assert r2.calc_md is not None and ("BaZi" in r2.calc_md or "\U0001f409" in r2.calc_md)
    assert r2.completed_at is not None


async def test_reading_generate_no_llm_client_degrades_gracefully(session, default_tenant):
    from quantuum.tasks.reading import reading_generate

    acc, prof = await _setup(session, default_tenant)
    r = await create_reading(
        session,
        tenant_id=default_tenant.id,
        account_id=acc.id,
        natal_profile_id=prof.id,
        kind="numerology",
        lang="en",
    )
    rid = r.id

    ctx = {"sessionmaker": _Maker(session), "llm_client": None}
    await reading_generate(ctx, rid, chat_id=None, request_id=None)

    r2 = await get_reading(session, rid)
    await session.refresh(r2)
    assert r2.status == "done"
    assert r2.llm_md == r2.calc_md
    assert r2.llm_provider == "none"


async def test_reading_generate_llm_failure_refunds_and_fails(session, default_tenant):
    from quantuum.tasks.reading import reading_generate
    from quantuum.domain.quota import consume_quota
    from quantuum.domain.requests import create_request
    from quantuum.db.models import AccountBalance, AccountPackage, PackagePlan, Request

    class _BadLLM:
        async def complete(self, **kw):
            raise RuntimeError("LLM down")

    acc, prof = await _setup(session, default_tenant)
    plan = PackagePlan(
        tenant_id=default_tenant.id, slug="t-pkg", name="t", request_count=1, price_cents=0
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    bal = await session.get(AccountBalance, acc.id)
    bal.free_trial_used = True
    bal.package_credits = 1
    pkg = AccountPackage(
        account_id=acc.id, tenant_id=default_tenant.id, plan_id=plan.id, requests_remaining=1
    )
    session.add(bal)
    session.add(pkg)
    await session.commit()

    charged = await consume_quota(session, acc.id, "reading", cost_units=1)
    req = await create_request(
        session,
        tenant_id=default_tenant.id,
        account_id=acc.id,
        kind="reading",
        charged_against=charged,
    )
    r = await create_reading(
        session,
        tenant_id=default_tenant.id,
        account_id=acc.id,
        natal_profile_id=prof.id,
        kind="bazi",
        lang="en",
    )
    rid, reqid = r.id, req.id

    ctx = {"sessionmaker": _Maker(session), "llm_client": _BadLLM()}
    await reading_generate(ctx, rid, chat_id=None, request_id=reqid)

    r2 = await get_reading(session, rid)
    await session.refresh(r2)
    assert r2.status == "failed"
    req2 = await session.get(Request, reqid)
    await session.refresh(req2)
    assert req2.status == "refunded"


async def test_enqueue_reading_dispatches(monkeypatch):
    from quantuum.tasks import enqueue as enq

    captured = {}

    class _Pool:
        async def enqueue_job(self, name, *args):
            captured["name"] = name
            captured["args"] = args

    async def _fake_get_pool():
        return _Pool()

    monkeypatch.setattr(enq, "_get_pool", _fake_get_pool)
    await enq.enqueue_reading(42, chat_id=5, request_id=7)
    assert captured == {"name": "reading_generate", "args": (42, 5, 7)}
