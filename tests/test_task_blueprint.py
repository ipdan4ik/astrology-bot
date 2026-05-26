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
    bal_before = await session.get(AccountBalance, acc.id)
    starting = bal_before.package_credits
    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "package"
    req = await create_request(
        session, tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint",
        charged_against=charged,
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

    # credit restored after failed generation
    bal = await session.get(AccountBalance, acc.id)
    await session.refresh(bal)
    assert bal.package_credits == starting


async def test_blueprint_generate_llm_failure_refunds(session, default_tenant):
    from quantuum.domain.quota import consume_quota
    from quantuum.domain.requests import create_request
    from quantuum.db.models import AccountBalance
    from quantuum.domain.blueprints import get_blueprint
    from quantuum.llm.base import LLMError

    acc, bp = await _setup(session, default_tenant.id)
    bal_before = await session.get(AccountBalance, acc.id)
    starting = bal_before.package_credits
    charged = await consume_quota(session, acc.id, "blueprint")
    assert charged == "package"
    req = await create_request(
        session, tenant_id=default_tenant.id, account_id=acc.id, kind="blueprint",
        charged_against=charged,
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
    assert bal.package_credits == starting


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
    # llm_md is now the composite stitched document from 8 parallel polish_reading calls.
    assert reloaded.llm_md is not None
    assert "QUANTUUM SOULMAP BLUEPRINT" in reloaded.llm_md
    assert "## 🌌 FIELD OVERVIEW" in reloaded.llm_md
    # tokens_in/out are summed over 8 polish_reading calls (FakeLLM returns 11/22 each).
    assert reloaded.llm_tokens_in == 11 * 8
    assert reloaded.llm_provider == "openai"
    assert reloaded.llm_model == "claude-test"


async def test_blueprint_delivers_via_owning_tenant_bot(session, default_tenant, monkeypatch):
    """Regression: a blueprint must be delivered through ITS tenant's bot, not the platform
    default ctx[bot]. A user who only ever talked to their own tenant bot cannot be messaged
    by the default bot, so delivery via ctx[bot] silently failed (blueprint_delivery_failed)."""
    import quantuum.tasks.blueprint as bp_mod
    from quantuum.db.models import Tenant

    other = Tenant(slug="other-co", display_name="Other Co", status="active")
    session.add(other)
    await session.flush()

    acc, bp = await _setup(session, other.id)

    captured: dict = {}

    async def fake_deliver(sessionmaker, *, tenant_id, chat_id, text, filename, **kw):
        captured.update(tenant_id=tenant_id, chat_id=chat_id, filename=filename)

    monkeypatch.setattr(bp_mod, "deliver_via_tenant_bot", fake_deliver, raising=False)

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

    ctx = {"sessionmaker": _Maker(), "bot": AsyncMock(), "llm_client": FakeLLM()}
    await bp_mod.blueprint_generate(ctx, bp.id, chat_id=999)

    assert captured.get("tenant_id") == other.id
    assert captured.get("chat_id") == 999
    assert captured.get("filename") == "blueprint.md"


async def test_blueprint_generate_without_llm_falls_back_to_calc_md(session, default_tenant, monkeypatch):
    import quantuum.tasks.blueprint as bp_mod

    acc, bp = await _setup(session, default_tenant.id)
    deliver = AsyncMock()
    monkeypatch.setattr(bp_mod, "deliver_via_tenant_bot", deliver)

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

    ctx = {"sessionmaker": _Maker(), "bot": AsyncMock(), "llm_client": None}
    await blueprint_generate(ctx, bp.id, chat_id=999)

    reloaded = await get_blueprint(session, bp.id)
    assert reloaded.status == "done"
    assert reloaded.llm_md == reloaded.calc_md
    assert reloaded.llm_provider == "none"
    deliver.assert_awaited_once()
    assert deliver.await_args.kwargs["tenant_id"] == default_tenant.id


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


async def test_blueprint_generate_passes_stored_lang(session, default_tenant):
    from quantuum.domain.natal_profiles import get_natal_profile
    from quantuum.llm.base import LLMResult

    acc, _ = await _setup(session, default_tenant.id)
    profile = await get_natal_profile(session, acc.id)
    bp = await create_blueprint(
        session, tenant_id=default_tenant.id, account_id=acc.id,
        natal_profile_id=profile.id, lang="de",
    )

    capture = {}

    class CaptureLLM:
        async def complete(self, *, system, user, model, temperature, max_tokens):
            capture["user"] = user
            return LLMResult(text="X", tokens_in=1, tokens_out=1, model="m")

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

    ctx = {"sessionmaker": _Maker(), "llm_client": CaptureLLM()}
    await blueprint_generate(ctx, bp.id, chat_id=None, request_id=None)
    assert "Answer in language: de." in capture["user"]
