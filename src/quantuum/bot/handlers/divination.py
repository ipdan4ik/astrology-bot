import random

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from openai import AsyncOpenAI

from quantuum.bot.handlers.generate import _buy_offer_kb
from quantuum.bot.ui.keyboards import main_menu_kb, profile_kb
from quantuum.bot.ui.callbacks import DivinationCb, OnboardCb, ReadingCb
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.divination import iching, tarot
from quantuum.domain.moderation import record_moderation_event
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.quota import consume_quota
from quantuum.domain.readings import create_reading
from quantuum.domain.requests import create_request
from quantuum.domain.tenant_features import is_feature_enabled
from quantuum.i18n import Translator
from quantuum.llm.registry import get_llm_client
from quantuum.logging_setup import get_logger
from quantuum.moderation import POLICY, Safe, Tier1Hit, moderate
from quantuum.settings import get_settings
from quantuum.tasks.enqueue import enqueue_reading

router = Router()
_log = get_logger("divination.handler")
_feature_log = get_logger("tenant_features.gate")
_mod_log = get_logger("moderation.handler")


class Divination(StatesGroup):
    awaiting_question = State()


_DIVINATION_KINDS = {"tarot", "iching"}


async def _divination_question_kb(i18n: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text=await i18n("divination.skip_btn"),
        callback_data=DivinationCb(action="skip"),
    )
    b.button(
        text=await i18n("kb.cancel"),
        callback_data=OnboardCb(action="cancel"),
    )
    b.adjust(1)
    return b.as_markup()


@router.callback_query(
    ReadingCb.filter((F.action == "generate") & F.kind.in_(_DIVINATION_KINDS))
)
async def on_divination_choice(
    query: CallbackQuery,
    account: Account,
    state: FSMContext,
    i18n: Translator,
) -> None:
    kind = ReadingCb.unpack(query.data).kind
    flag_key = f"reading.{kind}"
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, account.tenant_id, flag_key):
            _feature_log.info(
                "feature.gate_blocked",
                tenant_id=account.tenant_id, account_id=account.id,
                key=flag_key, surface="divination.on_divination_choice",
            )
            await query.message.answer(await i18n("feature.disabled_generic"))
            await query.answer()
            return
        profile = await get_natal_profile(session, account.id)
    if profile is None:
        await query.message.answer(
            await i18n("readings.no_profile"),
            reply_markup=await profile_kb(has_profile=False, i18n=i18n),
        )
        await query.answer()
        return

    await state.set_state(Divination.awaiting_question)
    await state.update_data(kind=kind)

    await query.message.answer(
        await i18n("divination.question_prompt"),
        reply_markup=await _divination_question_kb(i18n),
    )
    await query.answer()


async def _moderate_question(question: str, lang: str) -> object:
    settings = get_settings()
    if not (settings.moderation_enabled and settings.llm_api_key):
        return Safe()
    openai_client = AsyncOpenAI(api_key=settings.llm_api_key)
    llm_client = get_llm_client(settings)
    try:
        return await moderate(
            question, lang,
            openai_client=openai_client,
            llm_client=llm_client,
            settings=settings,
        )
    except Exception:
        if not settings.moderation_fail_open:
            raise
        return Safe()


async def _record_moderation_hit(
    message: Message, account: Account, verdict, lang: str
) -> None:
    entry = POLICY[verdict.category]
    source = "openai" if isinstance(verdict, Tier1Hit) else "mini_llm"
    async with get_sessionmaker()() as session:
        await record_moderation_event(
            session,
            account_id=account.id,
            tenant_id=account.tenant_id,
            lang=lang,
            category=verdict.category,
            action=entry["action"],
            source=source,
            raw_text=message.text or "",
        )
        await session.commit()
    _mod_log.info(
        "moderation.triggered",
        account_id=account.id, tenant_id=account.tenant_id,
        category=verdict.category.value, action=entry["action"].value,
        source=source, lang=lang,
    )


async def _perform_draw_and_enqueue(
    *,
    chat_id: int,
    account: Account,
    state: FSMContext,
    i18n: Translator,
    message_for_reply,
    question: str | None,
) -> None:
    """Consume quota -> draw -> create_reading -> enqueue. Aborts on no-quota."""
    data = await state.get_data()
    kind = data["kind"]

    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
        if profile is None:
            await message_for_reply.answer(await i18n("readings.no_profile"))
            await state.clear()
            return

        try:
            charged = await consume_quota(session, account.id, "reading", cost_units=1)
        except InsufficientFundsError:
            await message_for_reply.answer(
                await i18n("readings.no_quota"),
                reply_markup=await _buy_offer_kb(i18n),
            )
            await state.clear()
            return

        if kind == "tarot":
            cards = tarot.draw_three(rng=random.SystemRandom())
            draw_jsonb = {
                "question": question,
                "cards": [
                    {"id": d.card.id, "reversed": d.reversed, "position": d.position}
                    for d in cards
                ],
            }
        elif kind == "iching":
            cast = iching.cast_three_coins(rng=random.SystemRandom())
            draw_jsonb = {
                "question": question,
                "lines": list(cast.lines),
                "primary_id": cast.primary_id,
                "transformed_id": cast.transformed_id,
                "changing_indices": list(cast.changing_indices),
            }
        else:
            await message_for_reply.answer(await i18n("feature.disabled_generic"))
            await state.clear()
            return

        reading = await create_reading(
            session,
            tenant_id=account.tenant_id, account_id=account.id,
            natal_profile_id=profile.id, kind=kind, lang=i18n.lang,
        )
        reading.draw_jsonb = draw_jsonb
        session.add(reading)
        await session.commit()
        await session.refresh(reading)

        request = await create_request(
            session,
            tenant_id=account.tenant_id, account_id=account.id,
            kind="reading", charged_against=charged,
        )

    await enqueue_reading(reading.id, chat_id, request.id)
    await message_for_reply.answer(await i18n("readings.queued"))
    await state.clear()


@router.message(Command("skip"), Divination.awaiting_question)
async def on_divination_skip_cmd(
    message: Message, account: Account, state: FSMContext, i18n: Translator
) -> None:
    await on_divination_skip(message, account=account, state=state, i18n=i18n)


@router.callback_query(DivinationCb.filter(F.action == "skip"), Divination.awaiting_question)
async def on_divination_skip_cb(
    query: CallbackQuery, account: Account, state: FSMContext, i18n: Translator
) -> None:
    await on_divination_skip(query.message, account=account, state=state, i18n=i18n)
    await query.answer()


async def on_divination_skip(
    message: Message,
    *,
    account: Account,
    state: FSMContext,
    i18n: Translator,
) -> None:
    await _perform_draw_and_enqueue(
        chat_id=message.chat.id,
        account=account, state=state, i18n=i18n,
        message_for_reply=message, question=None,
    )


@router.message(Divination.awaiting_question)
async def on_divination_question(
    message: Message,
    account: Account,
    state: FSMContext,
    i18n: Translator,
) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer(await i18n("divination.question_prompt"))
        return

    verdict = await _moderate_question(text, i18n.lang)
    if not isinstance(verdict, Safe):
        entry = POLICY[verdict.category]
        text_kwargs: dict[str, str] = {}
        if entry["uses_helpline"]:
            text_kwargs["helpline_url"] = await i18n("moderation.helpline_url")
        response_text = await i18n(entry["i18n_key"], **text_kwargs)
        await _record_moderation_hit(message, account, verdict, i18n.lang)
        await message.answer(
            response_text,
            reply_markup=await main_menu_kb(i18n, account.tenant_id),
        )
        await state.clear()
        return

    await _perform_draw_and_enqueue(
        chat_id=message.chat.id,
        account=account, state=state, i18n=i18n,
        message_for_reply=message, question=text,
    )
