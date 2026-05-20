from unittest.mock import AsyncMock

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.domain.blueprints import create_blueprint, get_blueprint
from quantuum.domain.mock_blueprint import MOCK_BLUEPRINT_MD
from quantuum.domain.natal_profiles import upsert_natal_profile
from quantuum.tasks.blueprint import blueprint_generate


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

    ctx = {"sessionmaker": _Maker(), "bot": bot}
    await bp_mod.blueprint_generate(ctx, bp.id, chat_id=None, request_id=req.id)

    # trial restored
    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.free_trial_used is False


async def test_blueprint_generate_sets_done_and_sends(session, default_tenant):
    acc, bp = await _setup(session, default_tenant.id)
    bot = AsyncMock()

    # ctx mimics what arq's startup provides: a sessionmaker and a bot.
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

    ctx = {"sessionmaker": _Maker(), "bot": bot}
    await blueprint_generate(ctx, bp.id, chat_id=999)

    reloaded = await get_blueprint(session, bp.id)
    assert reloaded.status == "done"
    assert reloaded.llm_md == MOCK_BLUEPRINT_MD
    bot.send_document.assert_awaited()
