from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from quantuum.bot.ui.callbacks import ProfileCb
from quantuum.bot.ui.keyboards import cancel_kb, profile_kb
from quantuum.bot.ui.profile_fields import FIELD_PROMPTS, apply_field_edit
from quantuum.bot.ui.text import render_profile
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.natal_profiles import get_natal_profile, upsert_natal_profile

router = Router()


class ProfileEdit(StatesGroup):
    awaiting_value = State()


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
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        return "Профиль не найден."
    updated, err = apply_field_edit(profile_to_kwargs(profile), field, raw)
    if err is not None:
        return err
    await upsert_natal_profile(
        session, tenant_id=account.tenant_id, account_id=account.id, **updated
    )
    return None


async def show_profile(message: Message, account: Account) -> None:
    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
    if profile is None:
        await message.answer("Профиль не заполнен.", reply_markup=profile_kb(has_profile=False))
    else:
        await message.answer(render_profile(profile), reply_markup=profile_kb(has_profile=True))


@router.message(Command("profile"))
async def on_profile_cmd(message: Message, account: Account) -> None:
    await show_profile(message, account)


@router.callback_query(ProfileCb.filter(F.action == "edit"))
async def on_edit_field(query: CallbackQuery, callback_data: ProfileCb, state: FSMContext) -> None:
    await state.set_state(ProfileEdit.awaiting_value)
    await state.update_data(field=callback_data.field)
    await query.message.answer(FIELD_PROMPTS[callback_data.field], reply_markup=cancel_kb())
    await query.answer()


@router.message(ProfileEdit.awaiting_value)
async def on_edit_value(message: Message, state: FSMContext, account: Account) -> None:
    data = await state.get_data()
    field = data["field"]
    async with get_sessionmaker()() as session:
        err = await save_field(session, account=account, field=field, raw=message.text or "")
    if err is not None:
        await message.answer(err + "\nПопробуй ещё раз:", reply_markup=cancel_kb())
        return
    await state.clear()
    await show_profile(message, account)
