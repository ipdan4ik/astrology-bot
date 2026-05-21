from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from zoneinfo import available_timezones

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from quantuum.bot.ui.callbacks import OnboardCb
from quantuum.bot.ui.keyboards import cancel_kb
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.natal_profiles import upsert_natal_profile

router = Router()


class Onboarding(StatesGroup):
    full_name = State()
    birth_date = State()
    birth_time = State()
    birth_place = State()
    coords = State()
    timezone = State()


def parse_required_text(text: str | None) -> str | None:
    """Trim a free-text field; return None if empty (or a non-text message)."""
    cleaned = (text or "").strip()
    return cleaned or None


def parse_birth_date(text: str | None) -> date | None:
    try:
        return datetime.strptime((text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_birth_time(text: str | None) -> time | None:
    try:
        return datetime.strptime((text or "").strip(), "%H:%M").time()
    except ValueError:
        return None


def parse_coords(text: str | None) -> tuple[Decimal, Decimal] | None:
    parts = (text or "").replace(" ", "").split(",")
    if len(parts) != 2:
        return None
    try:
        lat, lon = Decimal(parts[0]), Decimal(parts[1])
    except (InvalidOperation, ValueError):
        return None
    if not (Decimal("-90") <= lat <= Decimal("90")):
        return None
    if not (Decimal("-180") <= lon <= Decimal("180")):
        return None
    return lat, lon


@lru_cache(maxsize=1)
def _valid_timezones() -> frozenset[str]:
    return frozenset(available_timezones())


def is_valid_timezone(text: str | None) -> bool:
    """True only for a full IANA zone key (e.g. Europe/Moscow).

    Membership in available_timezones() is the authoritative check: it rejects bare regions
    like "Europe" (which would otherwise make ZoneInfo raise IsADirectoryError on the tzdata
    package layout) as well as unknown zones, blanks, and non-text messages.
    """
    return (text or "").strip() in _valid_timezones()


def build_profile_data(raw: dict, timezone: str) -> dict:
    """Reconstruct typed profile values from the FSM's string-only storage.

    FSM data must be JSON-serializable, so dates/times/decimals are stored as
    strings (via isoformat / str). Parse them back symmetrically here — using
    fromisoformat (not the input-validation parse_* helpers, which only accept
    the user-facing HH:MM / YYYY-MM-DD entry formats).
    """
    return {
        "full_name": raw["full_name"],
        "birth_date": date.fromisoformat(raw["birth_date"]),
        "birth_time": time.fromisoformat(raw["birth_time"]),
        "birth_place": raw["birth_place"],
        "latitude": Decimal(raw["latitude"]),
        "longitude": Decimal(raw["longitude"]),
        "timezone": timezone.strip(),
    }


async def save_collected_profile(session, *, account: Account, data: dict):
    return await upsert_natal_profile(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        full_name=data["full_name"],
        birth_date=data["birth_date"],
        birth_time=data["birth_time"],
        birth_place=data["birth_place"],
        latitude=data["latitude"],
        longitude=data["longitude"],
        timezone=data["timezone"],
    )


@router.callback_query(OnboardCb.filter(F.action == "start"))
async def start_onboarding(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Onboarding.full_name)
    await query.message.answer(
        "Введи полное имя (как в свидетельстве о рождении):", reply_markup=await cancel_kb()
    )
    await query.answer()


@router.message(Onboarding.full_name)
async def on_full_name(message: Message, state: FSMContext) -> None:
    name = parse_required_text(message.text)
    if name is None:
        await message.answer("Не понял имя. Введи полное имя текстом:")
        return
    await state.update_data(full_name=name)
    await state.set_state(Onboarding.birth_date)
    await message.answer("Дата рождения в формате ГГГГ-ММ-ДД (например 1980-06-24):")


@router.message(Onboarding.birth_date)
async def on_birth_date(message: Message, state: FSMContext) -> None:
    parsed = parse_birth_date(message.text)
    if parsed is None:
        await message.answer("Не понял дату. Формат ГГГГ-ММ-ДД:")
        return
    await state.update_data(birth_date=parsed.isoformat())
    await state.set_state(Onboarding.birth_time)
    await message.answer("Время рождения ЧЧ:ММ (например 10:00):")


@router.message(Onboarding.birth_time)
async def on_birth_time(message: Message, state: FSMContext) -> None:
    parsed = parse_birth_time(message.text)
    if parsed is None:
        await message.answer("Не понял время. Формат ЧЧ:ММ:")
        return
    await state.update_data(birth_time=parsed.isoformat())
    await state.set_state(Onboarding.birth_place)
    await message.answer("Город рождения (например Moscow):")


@router.message(Onboarding.birth_place)
async def on_birth_place(message: Message, state: FSMContext) -> None:
    place = parse_required_text(message.text)
    if place is None:
        await message.answer("Не понял город. Введи город рождения текстом (например Moscow):")
        return
    await state.update_data(birth_place=place)
    await state.set_state(Onboarding.coords)
    await message.answer("Координаты «широта, долгота» (например 55.7558, 37.6173):")


@router.message(Onboarding.coords)
async def on_coords(message: Message, state: FSMContext) -> None:
    parsed = parse_coords(message.text)
    if parsed is None:
        await message.answer("Не понял координаты. Формат «55.7558, 37.6173»:")
        return
    lat, lon = parsed
    await state.update_data(latitude=str(lat), longitude=str(lon))
    await state.set_state(Onboarding.timezone)
    await message.answer("Таймзона IANA (например Europe/Moscow):")


@router.message(Onboarding.timezone)
async def on_timezone(message: Message, state: FSMContext, account: Account) -> None:
    if not is_valid_timezone(message.text):
        await message.answer(
            "Не понял таймзону. Нужна IANA-зона, например Europe/Moscow или Asia/Irkutsk:"
        )
        return
    raw = await state.get_data()
    data = build_profile_data(raw, message.text)
    async with get_sessionmaker()() as session:
        await save_collected_profile(session, account=account, data=data)
    await state.clear()
    await message.answer("Готово! Профиль сохранён. Команда /blueprint сгенерирует твой разбор.")
