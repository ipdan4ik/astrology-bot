from datetime import date, datetime, time
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.ui.callbacks import OnboardCb
from quantuum.bot.ui.keyboards import cancel_kb
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.natal_profiles import upsert_natal_profile
from quantuum.geocoding import coords_to_timezone, geocode, reverse
from quantuum.i18n import Translator

router = Router()


class Onboarding(StatesGroup):
    full_name = State()
    birth_date = State()
    birth_time = State()
    birth_place = State()
    birth_place_confirm = State()


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


async def geo_confirm_kb(i18n: Translator):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=await i18n("profile.kb.place_confirm"),
            callback_data=OnboardCb(action="geo_confirm").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await i18n("profile.kb.place_retry"),
            callback_data=OnboardCb(action="geo_retry").pack(),
        )
    )
    return builder.as_markup()


async def _finalize_profile(state: FSMContext, account: Account) -> None:
    raw = await state.get_data()
    data = build_profile_data(raw, raw["timezone"])
    async with get_sessionmaker()() as session:
        await save_collected_profile(session, account=account, data=data)
    await state.clear()


@router.callback_query(OnboardCb.filter(F.action == "start"))
async def start_onboarding(query: CallbackQuery, state: FSMContext, i18n: Translator) -> None:
    await state.set_state(Onboarding.full_name)
    await query.message.answer(
        await i18n("onb.prompt.full_name"), reply_markup=await cancel_kb(i18n)
    )
    await query.answer()


@router.message(Onboarding.full_name)
async def on_full_name(message: Message, state: FSMContext, i18n: Translator) -> None:
    name = parse_required_text(message.text)
    if name is None:
        await message.answer(await i18n("onb.error.full_name"))
        return
    await state.update_data(full_name=name)
    await state.set_state(Onboarding.birth_date)
    await message.answer(await i18n("onb.prompt.birth_date"))


@router.message(Onboarding.birth_date)
async def on_birth_date(message: Message, state: FSMContext, i18n: Translator) -> None:
    parsed = parse_birth_date(message.text)
    if parsed is None:
        await message.answer(await i18n("onb.error.birth_date"))
        return
    await state.update_data(birth_date=parsed.isoformat())
    await state.set_state(Onboarding.birth_time)
    await message.answer(await i18n("onb.prompt.birth_time"))


@router.message(Onboarding.birth_time)
async def on_birth_time(message: Message, state: FSMContext, i18n: Translator) -> None:
    parsed = parse_birth_time(message.text)
    if parsed is None:
        await message.answer(await i18n("onb.error.birth_time"))
        return
    await state.update_data(birth_time=parsed.isoformat())
    await state.set_state(Onboarding.birth_place)
    await message.answer(await i18n("onb.prompt.birth_place"))


@router.message(Onboarding.birth_place, F.location)
async def on_birth_place_location(
    message: Message, state: FSMContext, account: Account, i18n: Translator
) -> None:
    lat = message.location.latitude
    lon = message.location.longitude
    tz = coords_to_timezone(lat, lon)
    geo = await reverse(lat, lon)
    display = geo.display_name if geo is not None else f"📍 {lat:.4f}, {lon:.4f}"
    await state.update_data(
        birth_place=display, latitude=str(lat), longitude=str(lon), timezone=tz
    )
    await _finalize_profile(state, account)
    await message.answer(await i18n("onb.done"))


@router.message(Onboarding.birth_place, F.text)
async def on_birth_place_text(message: Message, state: FSMContext, i18n: Translator) -> None:
    results = await geocode((message.text or "").strip())
    if not results:
        await message.answer(await i18n("profile.place.not_found"))
        return
    top = results[0]
    tz = coords_to_timezone(top.lat, top.lon)
    await state.update_data(
        birth_place=top.display_name,
        latitude=str(top.lat),
        longitude=str(top.lon),
        timezone=tz,
    )
    await state.set_state(Onboarding.birth_place_confirm)
    await message.answer(
        await i18n("profile.place.confirm", place=top.display_name),
        reply_markup=await geo_confirm_kb(i18n),
    )


@router.message(Onboarding.birth_place)
async def on_birth_place_other(message: Message, state: FSMContext, i18n: Translator) -> None:
    await message.answer(await i18n("profile.prompt.birth_place"))


@router.callback_query(OnboardCb.filter(F.action == "geo_confirm"), Onboarding.birth_place_confirm)
async def on_geo_confirm(
    query: CallbackQuery, callback_data: OnboardCb, state: FSMContext,
    account: Account, i18n: Translator,
) -> None:
    await _finalize_profile(state, account)
    await query.message.answer(await i18n("onb.done"))
    await query.answer()


@router.callback_query(OnboardCb.filter(F.action == "geo_retry"), Onboarding.birth_place_confirm)
async def on_geo_retry(
    query: CallbackQuery, callback_data: OnboardCb, state: FSMContext, i18n: Translator
) -> None:
    await state.set_state(Onboarding.birth_place)
    await query.message.answer(await i18n("profile.prompt.birth_place"))
    await query.answer()
