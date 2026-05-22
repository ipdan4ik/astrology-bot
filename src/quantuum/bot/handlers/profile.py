from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from quantuum.bot.ui.callbacks import ProfileCb
from quantuum.bot.ui.keyboards import cancel_kb, profile_kb
from quantuum.bot.ui.profile_fields import FIELD_PROMPT_KEYS, apply_field_edit
from quantuum.bot.ui.text import render_profile
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.natal_profiles import get_natal_profile, upsert_natal_profile
from quantuum.geocoding import coords_to_timezone, geocode, reverse
from quantuum.i18n import Translator

router = Router()


class ProfileEdit(StatesGroup):
    awaiting_value = State()  # name / birth_date / birth_time (text)
    awaiting_place = State()  # birth_place: location or typed text
    place_confirm = State()  # typed place awaiting Да / Другой адрес


def profile_to_kwargs(profile) -> dict:
    return {
        "full_name": profile.full_name,
        "birth_date": profile.birth_date,
        "birth_time": profile.birth_time,
        "birth_place": profile.birth_place,
        "latitude": profile.latitude,
        "longitude": profile.longitude,
        "timezone": profile.timezone,
        "for_year": profile.for_year,
    }


async def save_field(session, *, account: Account, field: str, raw: str) -> str | None:
    """Apply a single-field edit. Returns None on success, or an i18n error key."""
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        return "profile.not_found"
    updated, err_key = apply_field_edit(profile_to_kwargs(profile), field, raw)
    if err_key is not None:
        return err_key
    await upsert_natal_profile(
        session, tenant_id=account.tenant_id, account_id=account.id, **updated
    )
    return None


async def save_place(
    session, *, account: Account, place: str, latitude, longitude, timezone: str
) -> str | None:
    """Update only the place + derived coordinates/timezone of the existing profile.

    Returns None on success, or an i18n error key.
    """
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        return "profile.not_found"
    kwargs = profile_to_kwargs(profile)
    kwargs.update(
        birth_place=place,
        latitude=Decimal(str(latitude)),
        longitude=Decimal(str(longitude)),
        timezone=timezone,
    )
    await upsert_natal_profile(
        session, tenant_id=account.tenant_id, account_id=account.id, **kwargs
    )
    return None


async def show_profile(message: Message, account: Account, i18n: Translator) -> None:
    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
    if profile is None:
        await message.answer(
            await i18n("profile.empty"),
            reply_markup=await profile_kb(has_profile=False, i18n=i18n),
        )
    else:
        await message.answer(
            await render_profile(i18n, profile),
            reply_markup=await profile_kb(has_profile=True, i18n=i18n),
        )


@router.message(Command("profile"))
async def on_profile_cmd(message: Message, account: Account, i18n: Translator) -> None:
    await show_profile(message, account, i18n)


@router.callback_query(ProfileCb.filter(F.action == "edit"))
async def on_edit_field(
    query: CallbackQuery, callback_data: ProfileCb, state: FSMContext, i18n: Translator
) -> None:
    field = callback_data.field
    if field == "birth_place":
        await state.set_state(ProfileEdit.awaiting_place)
        await query.message.answer(
            await i18n("profile.prompt.birth_place"), reply_markup=await cancel_kb(i18n)
        )
        await query.answer()
        return
    await state.set_state(ProfileEdit.awaiting_value)
    await state.update_data(field=field)
    await query.message.answer(
        await i18n(FIELD_PROMPT_KEYS[field]), reply_markup=await cancel_kb(i18n)
    )
    await query.answer()


@router.message(ProfileEdit.awaiting_value)
async def on_edit_value(
    message: Message, state: FSMContext, account: Account, i18n: Translator
) -> None:
    data = await state.get_data()
    field = data["field"]
    async with get_sessionmaker()() as session:
        err_key = await save_field(session, account=account, field=field, raw=message.text or "")
    if err_key is not None:
        err_text = await i18n(err_key)
        await message.answer(
            await i18n("profile.field_edit_error", err=err_text),
            reply_markup=await cancel_kb(i18n),
        )
        return
    await state.clear()
    await show_profile(message, account, i18n)


async def place_confirm_kb(i18n: Translator):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=await i18n("profile.kb.place_confirm"),
            callback_data=ProfileCb(action="place_confirm").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=await i18n("profile.kb.place_retry"),
            callback_data=ProfileCb(action="place_retry").pack(),
        )
    )
    return builder.as_markup()


@router.message(ProfileEdit.awaiting_place, F.location)
async def on_edit_place_location(
    message: Message, state: FSMContext, account: Account, i18n: Translator
) -> None:
    lat = message.location.latitude
    lon = message.location.longitude
    tz = coords_to_timezone(lat, lon)
    geo = await reverse(lat, lon)
    place = geo.display_name if geo is not None else f"📍 {lat:.4f}, {lon:.4f}"
    async with get_sessionmaker()() as session:
        err_key = await save_place(
            session, account=account, place=place, latitude=lat, longitude=lon, timezone=tz
        )
    if err_key is not None:
        await message.answer(await i18n(err_key))
        return
    await state.clear()
    await show_profile(message, account, i18n)


@router.message(ProfileEdit.awaiting_place, F.text)
async def on_edit_place_text(message: Message, state: FSMContext, i18n: Translator) -> None:
    results = await geocode((message.text or "").strip())
    if not results:
        await message.answer(
            await i18n("profile.place.not_found"), reply_markup=await cancel_kb(i18n)
        )
        return
    top = results[0]
    tz = coords_to_timezone(top.lat, top.lon)
    await state.update_data(
        place=top.display_name, latitude=str(top.lat), longitude=str(top.lon), timezone=tz
    )
    await state.set_state(ProfileEdit.place_confirm)
    await message.answer(
        await i18n("profile.place.confirm", place=top.display_name),
        reply_markup=await place_confirm_kb(i18n),
    )


@router.message(ProfileEdit.awaiting_place)
async def on_edit_place_other(message: Message, i18n: Translator) -> None:
    await message.answer(
        await i18n("profile.prompt.birth_place"), reply_markup=await cancel_kb(i18n)
    )


@router.callback_query(ProfileCb.filter(F.action == "place_confirm"), ProfileEdit.place_confirm)
async def on_place_confirm(
    query: CallbackQuery, callback_data: ProfileCb, state: FSMContext,
    account: Account, i18n: Translator,
) -> None:
    data = await state.get_data()
    async with get_sessionmaker()() as session:
        err_key = await save_place(
            session, account=account, place=data["place"],
            latitude=data["latitude"], longitude=data["longitude"], timezone=data["timezone"],
        )
    await query.answer()
    if err_key is not None:
        await query.message.answer(await i18n(err_key))
        return
    await state.clear()
    await show_profile(query.message, account, i18n)


@router.callback_query(ProfileCb.filter(F.action == "place_retry"), ProfileEdit.place_confirm)
async def on_place_retry(
    query: CallbackQuery, callback_data: ProfileCb, state: FSMContext, i18n: Translator
) -> None:
    await state.set_state(ProfileEdit.awaiting_place)
    await query.message.answer(
        await i18n("profile.prompt.birth_place"), reply_markup=await cancel_kb(i18n)
    )
    await query.answer()
