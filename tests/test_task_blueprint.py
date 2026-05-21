from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.domain.blueprints import create_blueprint, get_blueprint
from quantuum.domain.natal_profiles import upsert_natal_profile
from quantuum.llm.base import LLMResult
from quantuum.tasks.blueprint import blueprint_generate


class FakeLLM:
    def __init__(self):
        self.last_model = None
        self.last_temperature = None

    async def complete(self, *, system, user, model, temperature, max_tokens):
        self.last_model = model
        self.last_temperature = temperature
        return LLMResult(text="POLISHED REPORT", tokens_in=11, tokens_out=22, model="claude-test")


async def _setup(session, tenant_id):
    from datetime import date, time
    from decimal import Decimal

    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="7")
    profile = await upsert_natal_profile(
        session, tenant_id=tenant_id, account_id=acc.id, full_name="A",
        birth_date=date(1990, 1, 1), birth_time=time(12, 0), birth_place="Moscow",
        latitude=Decimal("55"), longitude=Decimal("37"), timezone="Europe/Moscow",
    )
    bp = await create_blueprint(
        session, tenant_id=tenant_id, account_id=acc.id, natal_profile_id=profile.id
    )
    return acc, bp


async def test_blueprint_generate_failure_refunds(session, default_tenant, monkeypatch):
    from quantuum.domain.quota import consume_quota
    from quantuum.domain.requests import create_request
    from quantuum.db.models import AccountBalance

    acc, bp = await _setup(session, default_tenant.id)
    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "trial"
    req = await create_request(
        session, tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint",
        charged_against="trial",
    )

    bot = AsyncMock()

    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *a):
            return False

    # Force the generation to fail.
    import quantuum.tasks.blueprint as bp_mod

    async def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(bp_mod, "set_status", boom)

    ctx = {"sessionmaker": _Maker(), "bot": bot, "llm_client": None}
    await bp_mod.blueprint_generate(ctx, bp.id, chat_id=None, request_id=req.id)

    # trial restored
    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.free_trial_used is False


async def test_blueprint_generate_llm_failure_refunds(session, default_tenant):
    from quantuum.domain.quota import consume_quota
    from quantuum.domain.requests import create_request
    from quantuum.db.models import AccountBalance
    from quantuum.domain.blueprints import get_blueprint
    from quantuum.llm.base import LLMError

    acc, bp = await _setup(session, default_tenant.id)
    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "trial"
    req = await create_request(
        session, tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint",
        charged_against="trial",
    )

    class _BoomLLM:
        async def complete(self, *, system, user, model, temperature, max_tokens):
            raise LLMError("upstream 500")

    bot = AsyncMock()

    class _Maker:
        def __call__(self):
            return _Ctx(session)

    class _Ctx:
        def __init__(self, s):
            self._s = s
        async def __aenter__(self):
            return self._s
        async def __aexit__(self, *a):
            return False

    ctx = {"sessionmaker": _Maker(), "bot": bot, "llm_client": _BoomLLM()}
    await blueprint_generate(ctx, bp.id, chat_id=None, request_id=req.id)

    reloaded = await get_blueprint(session, bp.id)
    assert reloaded.status == "failed"
    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.free_trial_used is False


async def test_blueprint_generate_real_engine_with_llm(session, default_tenant):
    acc, bp = await _setup(session, default_tenant.id)
    bot = AsyncMock()

    class _Maker:
        def __call__(self):
            return _Ctx(session)

    class _Ctx:
        def __init__(self, s):
            self._s = s
        async def __aenter__(self):
            return self._s
        async def __aexit__(self, *a):
            return False

    ctx = {"sessionmaker": _Maker(), "bot": bot, "llm_client": FakeLLM()}
    await blueprint_generate(ctx, bp.id, chat_id=999)

    reloaded = await get_blueprint(session, bp.id)
    assert reloaded.status == "done"
    assert reloaded.calc_md.startswith("# Quantuum Blueprint —")
    assert reloaded.llm_md == "POLISHED REPORT"
    assert reloaded.llm_tokens_in == 11
    assert reloaded.llm_provider == "openai"
    assert reloaded.llm_model == "claude-test"
    bot.send_document.assert_awaited()


async def test_blueprint_generate_without_llm_falls_back_to_calc_md(session, default_tenant):
    acc, bp = await _setup(session, default_tenant.id)
    bot = AsyncMock()

    class _Maker:
        def __call__(self):
            return _Ctx(session)

    class _Ctx:
        def __init__(self, s):
            self._s = s
        async def __aenter__(self):
            return self._s
        async def __aexit__(self, *a):
            return False

    ctx = {"sessionmaker": _Maker(), "bot": bot, "llm_client": None}
    await blueprint_generate(ctx, bp.id, chat_id=999)

    reloaded = await get_blueprint(session, bp.id)
    assert reloaded.status == "done"
    assert reloaded.llm_md == reloaded.calc_md
    assert reloaded.llm_provider == "none"
    bot.send_document.assert_awaited()


async def test_blueprint_uses_db_config_model(session, default_tenant):
    """When a DB override for llm.model is present, the task passes it to the LLM client."""
    from quantuum.domain.llm_config import set_llm_config

    # Seed a DB override for model and temperature
    await set_llm_config(session, model="claude-db-model", temperature=0.42)
    await session.commit()

    acc, bp = await _setup(session, default_tenant.id)
    bot = AsyncMock()
    fake_llm = FakeLLM()

    class _Maker:
        def __call__(self):
            return _Ctx(session)

    class _Ctx:
        def __init__(self, s):
            self._s = s
        async def __aenter__(self):
            return self._s
        async def __aexit__(self, *a):
            return False

    ctx = {"sessionmaker": _Maker(), "bot": bot, "llm_client": fake_llm}
    await blueprint_generate(ctx, bp.id, chat_id=None)

    # The FakeLLM must have been called with the DB-overridden model/temperature
    assert fake_llm.last_model == "claude-db-model"
    assert fake_llm.last_temperature == 0.42

    reloaded = await get_blueprint(session, bp.id)
    assert reloaded.status == "done"
