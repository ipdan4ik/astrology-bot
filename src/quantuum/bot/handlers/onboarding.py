from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

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


def parse_birth_date(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_birth_time(text: str) -> time | None:
    try:
        return datetime.strptime(text.strip(), "%H:%M").time()
    except ValueError:
        return None


def parse_coords(text: str) -> tuple[Decimal, Decimal] | None:
    parts = text.replace(" ", "").split(",")
    if len(parts) != 2:
        return None
    try:
        return Decimal(parts[0]), Decimal(parts[1])
    except (InvalidOperation, ValueError):
        return None


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


@router.message(Command("profile"))
async def start_onboarding(message: Message, state: FSMContext) -> None:
    await state.set_state(Onboarding.full_name)
    await message.answer("Введи полное имя (как в свидетельстве о рождении):")


@router.message(Onboarding.full_name)
async def on_full_name(message: Message, state: FSMContext) -> None:
    await state.update_data(full_name=message.text.strip())
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
    await state.update_data(birth_place=message.text.strip())
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
    raw = await state.get_data()
    data = {
        "full_name": raw["full_name"],
        "birth_date": parse_birth_date(raw["birth_date"]),
        "birth_time": parse_birth_time(raw["birth_time"]),
        "birth_place": raw["birth_place"],
        "latitude": Decimal(raw["latitude"]),
        "longitude": Decimal(raw["longitude"]),
        "timezone": message.text.strip(),
    }
    async with get_sessionmaker()() as session:
        await save_collected_profile(session, account=account, data=data)
    await state.clear()
    await message.answer("Готово! Профиль сохранён. Команда /blueprint сгенерирует твой разбор.")
