from datetime import date, time
from decimal import Decimal

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers.profile import profile_to_kwargs, save_field
from quantuum.domain.natal_profiles import get_natal_profile, upsert_natal_profile

from .conftest import build_translator


async def _acc_with_profile(session, tenant_id):
    acc = await find_or_create_account_by_tg(session, tenant_id=tenant_id, tg_user_id="77")
    await upsert_natal_profile(
        session, tenant_id=tenant_id, account_id=acc.id, full_name="Anna",
        birth_date=date(1980, 6, 24), birth_time=time(10, 0), birth_place="Moscow",
        latitude=Decimal("55.7558"), longitude=Decimal("37.6173"), timezone="Europe/Moscow",
    )
    return acc


async def test_profile_to_kwargs_roundtrip(session, default_tenant):
    acc = await _acc_with_profile(session, default_tenant.id)
    profile = await get_natal_profile(session, acc.id)
    kw = profile_to_kwargs(profile)
    assert kw["full_name"] == "Anna"
    assert kw["birth_time"] == time(10, 0)
    assert kw["latitude"] == Decimal("55.7558")


async def test_save_field_updates_one_field(session, default_tenant):
    acc = await _acc_with_profile(session, default_tenant.id)
    err_key = await save_field(session, account=acc, field="birth_time", raw="07:45")
    assert err_key is None
    profile = await get_natal_profile(session, acc.id)
    assert profile.birth_time == time(7, 45)
    assert profile.full_name == "Anna"  # others untouched


async def test_save_field_invalid_returns_error_key(session, default_tenant):
    acc = await _acc_with_profile(session, default_tenant.id)
    err_key = await save_field(session, account=acc, field="birth_time", raw="bad")
    assert err_key == "profile.error.birth_time_invalid"


async def test_save_field_no_profile_returns_not_found_key(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="404"
    )
    err_key = await save_field(session, account=acc, field="birth_time", raw="07:45")
    assert err_key == "profile.not_found"


class _FakeState:
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


def _patch_sessionmaker(monkeypatch, session):
    class _Maker:
        def __call__(self):
            return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    import quantuum.bot.handlers.profile as pr

    monkeypatch.setattr(pr, "get_sessionmaker", lambda: _Maker())


async def test_save_place_updates_only_place_fields(session, default_tenant):
    from decimal import Decimal

    from quantuum.bot.handlers.profile import save_place

    acc = await _acc_with_profile(session, default_tenant.id)
    err = await save_place(
        session, account=acc, place="Bratsk, Russia",
        latitude=56.13, longitude=101.61, timezone="Asia/Irkutsk",
    )
    assert err is None
    profile = await get_natal_profile(session, acc.id)
    assert profile.birth_place == "Bratsk, Russia"
    assert profile.timezone == "Asia/Irkutsk"
    assert profile.latitude == Decimal("56.13")
    assert profile.full_name == "Anna"  # untouched
    assert profile.birth_time == time(10, 0)  # untouched


async def test_edit_place_location_updates_profile(session, default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import quantuum.bot.handlers.profile as pr
    from quantuum.geocoding import GeoResult

    acc = await _acc_with_profile(session, default_tenant.id)
    _patch_sessionmaker(monkeypatch, session)
    monkeypatch.setattr(pr, "coords_to_timezone", lambda lat, lon: "Asia/Irkutsk")
    monkeypatch.setattr(pr, "reverse", AsyncMock(return_value=GeoResult(56.13, 101.61, "Bratsk, Russia")))
    monkeypatch.setattr(pr, "show_profile", AsyncMock())

    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState({})
    state.state = pr.ProfileEdit.awaiting_place
    message = SimpleNamespace(
        location=SimpleNamespace(latitude=56.13, longitude=101.61), answer=AsyncMock()
    )

    await pr.on_edit_place_location(message, state, account=acc, i18n=i18n)

    profile = await get_natal_profile(session, acc.id)
    assert profile.birth_place == "Bratsk, Russia"
    assert profile.timezone == "Asia/Irkutsk"
    assert state.state is None
    pr.show_profile.assert_awaited_once()


async def test_edit_place_text_geocodes_then_confirms(session, default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import quantuum.bot.handlers.profile as pr
    from quantuum.geocoding import GeoResult

    monkeypatch.setattr(
        pr, "geocode", AsyncMock(return_value=[GeoResult(56.13, 101.61, "Bratsk, Russia")])
    )
    monkeypatch.setattr(pr, "coords_to_timezone", lambda lat, lon: "Asia/Irkutsk")

    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState({})
    state.state = pr.ProfileEdit.awaiting_place
    message = SimpleNamespace(text="Bratsk", answer=AsyncMock())

    await pr.on_edit_place_text(message, state, i18n=i18n)

    assert state.state == pr.ProfileEdit.place_confirm
    data = await state.get_data()
    assert data["place"] == "Bratsk, Russia" and data["timezone"] == "Asia/Irkutsk"
    text_out = message.answer.await_args.args[0]
    assert "Bratsk, Russia" in text_out


async def test_edit_place_text_not_found_reprompts(session, default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import quantuum.bot.handlers.profile as pr

    monkeypatch.setattr(pr, "geocode", AsyncMock(return_value=[]))

    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState({})
    state.state = pr.ProfileEdit.awaiting_place
    message = SimpleNamespace(text="asdfghjkl", answer=AsyncMock())

    await pr.on_edit_place_text(message, state, i18n=i18n)

    assert state.state == pr.ProfileEdit.awaiting_place  # unchanged
    message.answer.assert_awaited()


async def test_place_confirm_saves(session, default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import quantuum.bot.handlers.profile as pr
    from quantuum.bot.ui.callbacks import ProfileCb

    acc = await _acc_with_profile(session, default_tenant.id)
    _patch_sessionmaker(monkeypatch, session)
    monkeypatch.setattr(pr, "show_profile", AsyncMock())

    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState(
        {"place": "Bratsk, Russia", "latitude": "56.13", "longitude": "101.61", "timezone": "Asia/Irkutsk"}
    )
    state.state = pr.ProfileEdit.place_confirm
    query = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())

    await pr.on_place_confirm(query, ProfileCb(action="place_confirm"), state, account=acc, i18n=i18n)

    profile = await get_natal_profile(session, acc.id)
    assert profile.birth_place == "Bratsk, Russia"
    assert state.state is None


async def test_place_retry_returns_to_awaiting_place(session, default_tenant, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import quantuum.bot.handlers.profile as pr
    from quantuum.bot.ui.callbacks import ProfileCb

    i18n = await build_translator(session, default_tenant.id)
    state = _FakeState({"place": "x"})
    state.state = pr.ProfileEdit.place_confirm
    query = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())

    await pr.on_place_retry(query, ProfileCb(action="place_retry"), state, i18n=i18n)

    assert state.state == pr.ProfileEdit.awaiting_place
