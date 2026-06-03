from datetime import date, time
from decimal import Decimal

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.onboarding import parse_birth_date, parse_birth_time
from quantuum.i18n.resolver import safe_format
from quantuum.i18n.seed_strings import BASE_STRINGS


class FakeI18n:
    """Returns the seeded RU string for a key, formatted with vars (no DB)."""

    lang = "ru"

    async def __call__(self, key, default=None, **vars):
        template = BASE_STRINGS.get(key, {}).get("ru", default if default is not None else key)
        return safe_format(template, vars)


def test_parse_birth_date_valid():
    assert parse_birth_date("1980-06-24") == date(1980, 6, 24)


def test_parse_birth_date_invalid():
    assert parse_birth_date("nonsense") is None


def test_parse_birth_time_valid():
    assert parse_birth_time("10:00") == time(10, 0)


async def test_finish_onboarding_saves_profile(session, default_tenant):
    from quantuum.bot.handlers.onboarding import save_collected_profile

    acc = await find_or_create_account_by_tg(session, tenant_id=default_tenant.id, tg_user_id="3")
    profile = await save_collected_profile(
        session,
        account=acc,
        data={
            "full_name": "Anna",
            "birth_date": date(1980, 6, 24),
            "birth_time": time(10, 0),
            "birth_place": "Moscow",
            "latitude": Decimal("55.7558"),
            "longitude": Decimal("37.6173"),
            "timezone": "Europe/Moscow",
        },
    )
    assert profile.id is not None
    assert profile.full_name == "Anna"


def test_build_profile_data_roundtrips_isoformat_time():
    # on_birth_time stores time as isoformat ("HH:MM:SS"); reconstruction must
    # not drop it to None (regression: parse_birth_time only accepted "HH:MM").
    from quantuum.bot.handlers.onboarding import build_profile_data

    raw = {
        "full_name": "Даниил",
        "birth_date": "2001-03-04",
        "birth_time": "10:30:00",
        "birth_place": "Bratsk",
        "latitude": "55.7558",
        "longitude": "37.6173",
    }
    data = build_profile_data(raw, "Europe/Moscow")
    assert data["birth_time"] == time(10, 30)
    assert data["birth_date"] == date(2001, 3, 4)
    assert data["latitude"] == Decimal("55.7558")
    assert data["timezone"] == "Europe/Moscow"


def test_parsers_tolerate_none_text():
    # Non-text messages (stickers, photos, voice) arrive with message.text == None;
    # parsers must reject, not crash.
    assert parse_birth_date(None) is None
    assert parse_birth_time(None) is None


def test_parse_required_text():
    from quantuum.bot.handlers.onboarding import parse_required_text

    assert parse_required_text("  Anna  ") == "Anna"
    assert parse_required_text("") is None
    assert parse_required_text("   ") is None
    assert parse_required_text(None) is None


class _State:
    def __init__(self, data):
        self._data = dict(data)
        self.state = None

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kw):
        self._data.update(kw)

    async def set_state(self, s):
        self.state = s

    async def clear(self):
        self._data = {}
        self.state = None


def _patch_sessionmaker(monkeypatch, mod):
    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(mod, "get_sessionmaker", lambda: _Maker())


_BASE = {"full_name": "Anna", "birth_date": "1980-06-24", "birth_time": "10:00"}


async def test_birth_place_location_saves_with_derived_tz(default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob
    from quantuum.geocoding import GeoResult

    _patch_sessionmaker(monkeypatch, ob)
    saved = AsyncMock()
    monkeypatch.setattr(ob, "save_collected_profile", saved)
    monkeypatch.setattr(ob, "coords_to_timezone", lambda lat, lon: "Europe/Moscow")
    monkeypatch.setattr(ob, "reverse", AsyncMock(return_value=GeoResult(55.75, 37.62, "Moscow, Russia")))

    state = _State(_BASE)
    state.state = ob.Onboarding.birth_place
    message = SimpleNamespace(
        location=SimpleNamespace(latitude=55.75, longitude=37.62), answer=AsyncMock()
    )
    account = SimpleNamespace(id=1, tenant_id=default_tenant.id)

    await ob.on_birth_place_location(message, state, account=account, i18n=FakeI18n())

    saved.assert_awaited_once()
    data = saved.await_args.kwargs["data"]
    assert data["timezone"] == "Europe/Moscow"
    assert str(data["latitude"]) == "55.75"
    assert state.state is None  # cleared


async def test_birth_place_location_falls_back_when_reverse_fails(default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob

    _patch_sessionmaker(monkeypatch, ob)
    saved = AsyncMock()
    monkeypatch.setattr(ob, "save_collected_profile", saved)
    monkeypatch.setattr(ob, "coords_to_timezone", lambda lat, lon: "Europe/Moscow")
    monkeypatch.setattr(ob, "reverse", AsyncMock(return_value=None))  # reverse-geocode failed

    state = _State(_BASE)
    state.state = ob.Onboarding.birth_place
    message = SimpleNamespace(
        location=SimpleNamespace(latitude=55.75, longitude=37.62), answer=AsyncMock()
    )
    account = SimpleNamespace(id=1, tenant_id=default_tenant.id)

    await ob.on_birth_place_location(message, state, account=account, i18n=FakeI18n())

    saved.assert_awaited_once()
    assert saved.await_args.kwargs["data"]["birth_place"] == "📍 55.7500, 37.6200"


async def test_birth_place_text_geocodes_then_confirms(default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob
    from quantuum.geocoding import GeoResult

    monkeypatch.setattr(
        ob, "geocode", AsyncMock(return_value=[GeoResult(56.13, 101.61, "Bratsk, Russia")])
    )
    monkeypatch.setattr(ob, "coords_to_timezone", lambda lat, lon: "Asia/Irkutsk")

    state = _State(_BASE)
    state.state = ob.Onboarding.birth_place
    message = SimpleNamespace(text="Bratsk", answer=AsyncMock())

    await ob.on_birth_place_text(message, state, i18n=FakeI18n())

    assert state.state == ob.Onboarding.birth_place_confirm
    assert (await state.get_data())["timezone"] == "Asia/Irkutsk"
    text = message.answer.await_args.args[0]
    assert "Bratsk" in text
    assert "Asia/Irkutsk" not in text  # tz line dropped (matches profile place-only flow)


async def test_birth_place_text_not_found_reprompts(default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob

    monkeypatch.setattr(ob, "geocode", AsyncMock(return_value=[]))

    state = _State(_BASE)
    state.state = ob.Onboarding.birth_place
    message = SimpleNamespace(text="asdfghjkl", answer=AsyncMock())

    await ob.on_birth_place_text(message, state, i18n=FakeI18n())

    assert state.state == ob.Onboarding.birth_place  # unchanged, re-prompt
    message.answer.assert_awaited()


async def test_geo_confirm_saves(default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob
    from quantuum.bot.ui.callbacks import OnboardCb

    _patch_sessionmaker(monkeypatch, ob)
    saved = AsyncMock()
    monkeypatch.setattr(ob, "save_collected_profile", saved)

    state = _State(
        {**_BASE, "birth_place": "Bratsk, Russia", "latitude": "56.13",
         "longitude": "101.61", "timezone": "Asia/Irkutsk"}
    )
    state.state = ob.Onboarding.birth_place_confirm
    query = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    account = SimpleNamespace(id=1, tenant_id=default_tenant.id)

    await ob.on_geo_confirm(query, OnboardCb(action="geo_confirm"), state, account=account, i18n=FakeI18n())

    saved.assert_awaited_once()
    assert state.state is None


async def test_geo_retry_returns_to_birth_place(default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob
    from quantuum.bot.ui.callbacks import OnboardCb

    state = _State({**_BASE})
    state.state = ob.Onboarding.birth_place_confirm
    query = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())

    await ob.on_geo_retry(query, OnboardCb(action="geo_retry"), state, i18n=FakeI18n())

    assert state.state == ob.Onboarding.birth_place


async def test_on_full_name_invalid_localised(default_tenant):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob

    state = _State({})
    state.state = ob.Onboarding.full_name
    message = SimpleNamespace(text="   ", answer=AsyncMock())

    await ob.on_full_name(message, state, i18n=FakeI18n())

    assert message.answer.await_args.args[0] == BASE_STRINGS["onb.error.full_name"]["ru"]


async def test_on_birth_date_prompt_localised_en(session, default_tenant):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from quantuum.bot.handlers import onboarding as ob

    from .conftest import build_translator

    i18n = await build_translator(session, default_tenant.id, lang="en")
    state = _State({})
    state.state = ob.Onboarding.full_name
    message = SimpleNamespace(text="Anna", answer=AsyncMock())

    await ob.on_full_name(message, state, i18n=i18n)

    # advancing to birth_date prompts the EN string
    assert message.answer.await_args.args[0] == BASE_STRINGS["onb.prompt.birth_date"]["en"]
    assert state.state == ob.Onboarding.birth_date


# ---------------------------------------------------------------------------
# Cancel-kb persistence tests (PR1 fix/fsm-cancel)
# ---------------------------------------------------------------------------
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from quantuum.bot.ui.callbacks import OnboardCb


def _fsm_ctx(chat_id: int) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=chat_id, user_id=chat_id),
    )


class _FakeMsg:
    def __init__(self, text="", chat_id=1):
        self.text = text
        self.chat = SimpleNamespace(id=chat_id)
        self.answer = AsyncMock()


def _has_cancel(msg) -> bool:
    if not msg.answer.called:
        return False
    kb = msg.answer.call_args_list[-1].kwargs.get("reply_markup")
    if kb is None:
        return False
    btns = [b for row in kb.inline_keyboard for b in row]
    return any(OnboardCb.unpack(b.callback_data).action == "cancel" for b in btns)


async def test_onboarding_birth_date_prompt_carries_cancel_kb(session, default_tenant):
    from quantuum.bot.handlers import onboarding
    from tests.conftest import build_translator

    i18n = await build_translator(session, default_tenant.id)
    state = _fsm_ctx(301)
    await state.set_state(onboarding.Onboarding.full_name)
    msg = _FakeMsg(text="Иван Петров", chat_id=301)
    await onboarding.on_full_name(msg, state, i18n)

    assert await state.get_state() == onboarding.Onboarding.birth_date.state
    assert _has_cancel(msg), "birth_date prompt must carry cancel_kb"


async def test_onboarding_birth_date_error_carries_cancel_kb(session, default_tenant):
    from quantuum.bot.handlers import onboarding
    from tests.conftest import build_translator

    i18n = await build_translator(session, default_tenant.id)
    state = _fsm_ctx(302)
    await state.set_state(onboarding.Onboarding.birth_date)
    msg = _FakeMsg(text="not-a-date", chat_id=302)
    await onboarding.on_birth_date(msg, state, i18n)

    assert await state.get_state() == onboarding.Onboarding.birth_date.state
    assert _has_cancel(msg), "birth_date error must carry cancel_kb"


async def test_onboarding_birth_time_prompt_carries_cancel_kb(session, default_tenant):
    from quantuum.bot.handlers import onboarding
    from tests.conftest import build_translator

    i18n = await build_translator(session, default_tenant.id)
    state = _fsm_ctx(303)
    await state.set_state(onboarding.Onboarding.birth_date)
    await state.update_data(full_name="Иван")
    msg = _FakeMsg(text="1990-06-24", chat_id=303)
    await onboarding.on_birth_date(msg, state, i18n)

    assert await state.get_state() == onboarding.Onboarding.birth_time.state
    assert _has_cancel(msg), "birth_time prompt must carry cancel_kb"


async def test_onboarding_birth_time_error_carries_cancel_kb(session, default_tenant):
    from quantuum.bot.handlers import onboarding
    from tests.conftest import build_translator

    i18n = await build_translator(session, default_tenant.id)
    state = _fsm_ctx(304)
    await state.set_state(onboarding.Onboarding.birth_time)
    msg = _FakeMsg(text="not-a-time", chat_id=304)
    await onboarding.on_birth_time(msg, state, i18n)

    assert await state.get_state() == onboarding.Onboarding.birth_time.state
    assert _has_cancel(msg), "birth_time error must carry cancel_kb"


async def test_onboarding_birth_place_prompt_carries_cancel_kb(session, default_tenant):
    from quantuum.bot.handlers import onboarding
    from tests.conftest import build_translator

    i18n = await build_translator(session, default_tenant.id)
    state = _fsm_ctx(305)
    await state.set_state(onboarding.Onboarding.birth_time)
    await state.update_data(full_name="Иван", birth_date="1990-06-24")
    msg = _FakeMsg(text="10:00", chat_id=305)
    await onboarding.on_birth_time(msg, state, i18n)

    assert await state.get_state() == onboarding.Onboarding.birth_place.state
    assert _has_cancel(msg), "birth_place prompt must carry cancel_kb"
