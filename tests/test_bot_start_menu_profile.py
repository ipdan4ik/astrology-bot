"""Handler-level i18n tests for the start / menu / profile flows.

Each handler is invoked with a fake Message/CallbackQuery that captures the
``answer`` calls, plus a real Translator built against the test tenant. We then
assert the rendered text/labels come from the seeded BASE_STRINGS (ru default).
"""
from datetime import date, time
from decimal import Decimal

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.handlers import menu, profile, start
from quantuum.bot.ui.callbacks import OnboardCb, ProfileCb
from quantuum.domain.natal_profiles import upsert_natal_profile

from .conftest import build_translator


class FakeMessage:
    def __init__(self, text="", chat_id=1):
        self.text = text
        self.chat = type("C", (), {"id": chat_id})()
        self.answers = []  # list of (text, reply_markup)

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup))


class FakeCallbackQuery:
    def __init__(self, message):
        self.message = message
        self.answered = False

    async def answer(self, *a, **k):
        self.answered = True


def _reply_texts(markup):
    return [b.text for row in markup.keyboard for b in row]


def _inline(markup):
    return [b for row in markup.inline_keyboard for b in row]


def _fsm():
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_on_start_with_lang_set_sends_welcome_and_menu(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="600"
    )
    acc.preferred_lang = "ru"  # already chosen → no picker
    msg = FakeMessage("/start")
    await start.on_start(msg, acc, default_tenant.id, i18n)

    welcome = msg.answers[0][0]
    assert welcome == "Привет! Я построю твой астрологический разбор ✨"
    menu_text, menu_markup = msg.answers[1]
    assert menu_text == "Главное меню:"
    assert set(_reply_texts(menu_markup)) == {
        "🔮 Разбор", "❓ Спросить астролога", "📖 Разборы", "🌌 Транзиты", "🔔 Ежедневный гороскоп",
        "👤 Профиль", "📜 История", "ℹ️ Помощь", "🌐 Язык", "🎁 Пригласить друга",
    }


async def test_on_start_first_time_shows_language_picker(session, default_tenant):
    from quantuum.db.bootstrap import ensure_tenant_default_language
    from quantuum.bot.ui.callbacks import LangCb

    await ensure_tenant_default_language(session, default_tenant.id)
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="601"
    )  # preferred_lang is None → picker
    msg = FakeMessage("/start")
    await start.on_start(msg, acc, default_tenant.id, i18n)

    assert len(msg.answers) == 1  # picker only, no welcome/menu yet
    prompt, markup = msg.answers[0]
    assert prompt == "Выбери язык:"
    from quantuum.i18n.langs import PLATFORM_LANGS

    codes = {LangCb.unpack(b.callback_data).lang for row in markup.inline_keyboard for b in row}
    assert codes == set(PLATFORM_LANGS)


async def test_on_help_btn_sends_help_text(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    await session.commit()  # ensure tenant visible to separate session in main_menu_kb
    msg = FakeMessage("ℹ️ Помощь")
    await menu.on_help_btn(msg, default_tenant.id, i18n)
    help_text, markup = msg.answers[0]
    assert "Quantuum Blueprint" in help_text
    assert "@quantuum_support" in help_text
    assert set(_reply_texts(markup)) == {
        "🔮 Разбор", "❓ Спросить астролога", "📖 Разборы", "🌌 Транзиты", "🔔 Ежедневный гороскоп",
        "👤 Профиль", "📜 История", "ℹ️ Помощь", "🌐 Язык", "🎁 Пригласить друга",
    }


async def test_language_button_opens_picker(session, default_tenant):
    from quantuum.db.bootstrap import ensure_tenant_default_language
    from quantuum.bot.handlers import menu as menu_mod
    from quantuum.bot.ui.callbacks import LangCb

    await ensure_tenant_default_language(session, default_tenant.id)
    await session.commit()
    i18n = await build_translator(session, default_tenant.id)
    msg = FakeMessage("🌐 Язык")
    await menu_mod.on_language_btn(msg, default_tenant.id, i18n)

    prompt, markup = msg.answers[0]
    assert prompt == "Выбери язык:"
    actions = {LangCb.unpack(b.callback_data).action for row in markup.inline_keyboard for b in row}
    assert actions == {"set"}


async def test_on_cancel_sends_cancelled(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    await session.commit()  # ensure tenant visible to separate session in main_menu_kb
    msg = FakeMessage()
    query = FakeCallbackQuery(msg)
    await menu.on_cancel(query, _fsm(), default_tenant.id, i18n)
    assert msg.answers[0][0] == "Отменено."
    assert query.answered


async def test_show_profile_empty(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="500"
    )
    msg = FakeMessage()
    await profile.show_profile(msg, acc, i18n)
    profile_text, markup = msg.answers[0]
    assert profile_text == "Профиль не заполнен."
    labels = {b.text for b in _inline(markup)}
    assert labels == {"📝 Заполнить профиль"}
    assert OnboardCb.unpack(_inline(markup)[0].callback_data).action == "start"


async def test_show_profile_filled_renders_localised_fields(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="501"
    )
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="Anna",
        birth_date=date(1980, 6, 24), birth_time=time(10, 0), birth_place="Moscow",
        latitude=Decimal("55.7558"), longitude=Decimal("37.6173"), timezone="Europe/Moscow",
    )
    msg = FakeMessage()
    await profile.show_profile(msg, acc, i18n)
    profile_text, markup = msg.answers[0]
    assert "👤 Твой профиль:" in profile_text
    assert "Имя: Anna" in profile_text
    assert "Место: Moscow" in profile_text
    assert "Europe/Moscow" not in profile_text  # timezone hidden
    fields = {ProfileCb.unpack(b.callback_data).field for b in _inline(markup)}
    assert {"name", "birth_date", "birth_place"} <= fields
    assert "timezone" not in fields and "coords" not in fields


async def test_on_edit_field_sends_prompt(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    msg = FakeMessage()
    query = FakeCallbackQuery(msg)
    state = _fsm()
    await profile.on_edit_field(
        query, ProfileCb(action="edit", field="birth_time"), state, i18n
    )
    prompt, markup = msg.answers[0]
    assert prompt == "Время рождения ЧЧ:ММ (например 10:00):"
    assert [b.text for b in _inline(markup)] == ["✖️ Отмена"]
    assert (await state.get_data())["field"] == "birth_time"


async def test_on_edit_value_invalid_shows_localised_error(session, default_tenant):
    i18n = await build_translator(session, default_tenant.id)
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="502"
    )
    await upsert_natal_profile(
        session, tenant_id=default_tenant.id, account_id=acc.id, full_name="Anna",
        birth_date=date(1980, 6, 24), birth_time=time(10, 0), birth_place="Moscow",
        latitude=Decimal("55.7558"), longitude=Decimal("37.6173"), timezone="Europe/Moscow",
    )
    state = _fsm()
    await state.update_data(field="birth_time")
    msg = FakeMessage(text="nonsense")
    await profile.on_edit_value(msg, state, acc, i18n)
    err_text = msg.answers[0][0]
    assert "Не понял время. Формат ЧЧ:ММ." in err_text
    assert "Попробуй ещё раз:" in err_text
