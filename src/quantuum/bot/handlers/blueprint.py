from collections.abc import Awaitable, Callable

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.blueprints import create_blueprint
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.quota import consume_quota
from quantuum.domain.requests import create_request
from quantuum.tasks.enqueue import enqueue_blueprint

router = Router()


async def request_blueprint_for_account(
    session,
    *,
    account: Account,
    chat_id: int,
    enqueue: Callable[[int, int | None], Awaitable[None]],
) -> tuple[str, int | None]:
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        return "no_profile", None
    try:
        charged = await consume_quota(session, account.id, "blueprint")
    except InsufficientFundsError:
        return "no_quota", None

    blueprint = await create_blueprint(
        session, tenant_id=account.tenant_id, account_id=account.id, natal_profile_id=profile.id
    )
    await create_request(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        kind="blueprint",
        charged_against=charged,
    )
    await enqueue(blueprint.id, chat_id)
    return "queued", blueprint.id


@router.message(Command("blueprint"))
async def on_blueprint(message: Message, account: Account, chat_id: int) -> None:
    async with get_sessionmaker()() as session:
        status, _ = await request_blueprint_for_account(
            session, account=account, chat_id=chat_id, enqueue=enqueue_blueprint
        )
    if status == "no_profile":
        await message.answer("Сначала заполни профиль командой /profile.")
    elif status == "no_quota":
        await message.answer(
            "Бесплатная генерация уже использована. Подписка и пакеты появятся в "
            "следующем обновлении."
        )
    else:
        await message.answer("Генерирую твой разбор, это займёт около минуты…")
