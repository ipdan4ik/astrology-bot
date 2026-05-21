from datetime import date, time
from decimal import Decimal
from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.db.models import AccountBalance, AccountPackage, PackagePlan
from quantuum.domain.natal_profiles import upsert_natal_profile
from quantuum.domain.qa import create_qa, get_qa
from quantuum.llm.base import LLMResult
from quantuum.tasks.qa import qa_generate


class FakeLLM:
    async def complete(self, *, system, user, model, temperature, max_tokens):
        return LLMResult(text="ANSWER", tokens_in=11, tokens_out=22, model="claude-test")


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


async def _setup(session, tenant_id):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="42")
    profile = await upsert_natal_profile(
        session,
        tenant_id=tenant_id,
        account_id=acc.id,
        full_name="Anna",
        birth_date=date(1990, 6, 15),
        birth_time=time(14, 30),
        birth_place="Moscow",
        latitude=Decimal("55.7558"),
        longitude=Decimal("37.6176"),
        timezone="Europe/Moscow",
    )

    # Seed a PackagePlan and give the account package_credits so consume_quota
    # returns "package" (QaAnswer has no free trial path).
    plan = PackagePlan(slug="qa-pack", name="QA Pack", request_count=5, price_cents=100)
    session.add(plan)
    await session.flush()

    pkg = AccountPackage(
        tenant_id=tenant_id,
        account_id=acc.id,
        plan_id=plan.id,
        requests_remaining=5,
    )
    session.add(pkg)
    await session.flush()
    # AccountBalance is created by find_or_create_account_by_tg; update it to
    # mark trial used and seed package_credits so consume_quota uses "package".
    bal = await session.get(AccountBalance, acc.id)
    bal.free_trial_used = True
    bal.package_credits = 5
    session.add(bal)
    await session.commit()

    qa = await create_qa(
        session,
        tenant_id=tenant_id,
        account_id=acc.id,
        natal_profile_id=profile.id,
        question="What is my destiny?",
        lang="en",
    )
    return acc, profile, qa


async def test_qa_generate_happy_path(session, default_tenant):
    from quantuum.domain.quota import consume_quota
    from quantuum.domain.requests import create_request

    acc, profile, qa = await _setup(session, default_tenant.id)
    charged = await consume_quota(session, acc.id, "qa")
    assert charged == "package"

    req = await create_request(
        session,
        tenant_id=default_tenant.id,
        account_id=acc.id,
        kind="qa",
        charged_against="package",
    )

    bot = AsyncMock()
    ctx = {"sessionmaker": _Maker(session), "bot": bot, "llm_client": FakeLLM()}
    await qa_generate(ctx, qa.id, chat_id=999, request_id=req.id)

    reloaded = await get_qa(session, qa.id)
    assert reloaded.status == "done"
    assert reloaded.answer_md == "ANSWER"
    assert reloaded.llm_tokens_in == 11
    assert reloaded.llm_tokens_out == 22
    assert reloaded.llm_provider == "openai"
    assert reloaded.llm_model == "claude-test"
    bot.send_message.assert_awaited()


async def test_qa_generate_no_llm_refunds(session, default_tenant):
    from quantuum.domain.quota import consume_quota
    from quantuum.domain.requests import create_request

    acc, profile, qa = await _setup(session, default_tenant.id)
    charged = await consume_quota(session, acc.id, "qa")
    assert charged == "package"

    req = await create_request(
        session,
        tenant_id=default_tenant.id,
        account_id=acc.id,
        kind="qa",
        charged_against="package",
    )

    # Record balance before so we can confirm refund restores it.
    bal_before = await session.get(AccountBalance, acc.id)
    credits_before = bal_before.package_credits

    bot = AsyncMock()
    ctx = {"sessionmaker": _Maker(session), "bot": bot, "llm_client": None}
    await qa_generate(ctx, qa.id, chat_id=None, request_id=req.id)

    reloaded = await get_qa(session, qa.id)
    assert reloaded.status == "failed"

    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.package_credits == credits_before + 1


async def test_qa_generate_llm_failure_refunds(session, default_tenant):
    from quantuum.domain.quota import consume_quota
    from quantuum.domain.requests import create_request
    from quantuum.llm.base import LLMError

    class BoomLLM:
        async def complete(self, *, system, user, model, temperature, max_tokens):
            raise LLMError("upstream 500")

    acc, profile, qa = await _setup(session, default_tenant.id)
    charged = await consume_quota(session, acc.id, "qa")
    assert charged == "package"

    req = await create_request(
        session,
        tenant_id=default_tenant.id,
        account_id=acc.id,
        kind="qa",
        charged_against="package",
    )

    bal_before = await session.get(AccountBalance, acc.id)
    credits_before = bal_before.package_credits

    bot = AsyncMock()
    ctx = {"sessionmaker": _Maker(session), "bot": bot, "llm_client": BoomLLM()}
    await qa_generate(ctx, qa.id, chat_id=None, request_id=req.id)

    reloaded = await get_qa(session, qa.id)
    assert reloaded.status == "failed"

    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.package_credits == credits_before + 1
