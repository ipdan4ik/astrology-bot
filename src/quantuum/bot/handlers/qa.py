from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from openai import AsyncOpenAI

from quantuum.bot.handlers._guard import enqueue_or_refund
from quantuum.bot.handlers.generate import _buy_offer_kb
from quantuum.bot.ui.keyboards import cancel_kb, main_menu_kb, profile_kb
from quantuum.common.exceptions import InsufficientFundsError
from quantuum.db.models import Account
from quantuum.db.session import get_sessionmaker
from quantuum.domain.moderation import record_moderation_event
from quantuum.domain.natal_profiles import get_natal_profile
from quantuum.domain.qa import create_qa
from quantuum.domain.quota import consume_quota
from quantuum.domain.requests import create_request
from quantuum.domain.tenant_features import is_feature_enabled
from quantuum.i18n import Translator
from quantuum.llm.registry import get_llm_client
from quantuum.logging_setup import get_logger
from quantuum.moderation import POLICY, Safe, Tier1Hit, moderate
from quantuum.settings import get_settings
from quantuum.tasks.enqueue import enqueue_qa

router = Router()
_log = get_logger("moderation.handler")
_feature_log = get_logger("tenant_features.gate")

MAX_QUESTION_LEN = 1000


class Ask(StatesGroup):
    awaiting_question = State()


async def start_ask(message: Message, state: FSMContext, i18n: Translator) -> None:
    """Begin the ask flow: wait for the user's free-text question."""
    await state.set_state(Ask.awaiting_question)
    await message.answer(await i18n("qa.ask_prompt"), reply_markup=await cancel_kb(i18n))


async def _submit(message: Message, raw: str, account: Account, i18n: Translator) -> None:
    q = (raw or "").strip()
    if not q:
        await message.answer(await i18n("qa.empty"))
        return
    if len(q) > MAX_QUESTION_LEN:
        await message.answer(await i18n("qa.too_long"))
        return

    # Feature gate — before moderation and quota charge.
    async with get_sessionmaker()() as session:
        if not await is_feature_enabled(session, account.tenant_id, "qa"):
            _feature_log.info(
                "feature.gate_blocked",
                tenant_id=account.tenant_id,
                account_id=account.id,
                key="qa",
                surface="qa._submit",
            )
            await message.answer(await i18n("feature.disabled_generic"))
            return

    # Moderation pre-check — before any quota charge.
    settings = get_settings()
    if settings.moderation_enabled and settings.llm_api_key:
        openai_client = AsyncOpenAI(api_key=settings.llm_api_key)
        llm_client = get_llm_client(settings)
        try:
            verdict = await moderate(
                q,
                i18n.lang,
                openai_client=openai_client,
                llm_client=llm_client,
                settings=settings,
            )
        except Exception:
            if not settings.moderation_fail_open:
                raise
            verdict = Safe()

        if not isinstance(verdict, Safe):
            entry = POLICY[verdict.category]
            source = "openai" if isinstance(verdict, Tier1Hit) else "mini_llm"
            text_kwargs: dict[str, str] = {}
            if entry["uses_helpline"]:
                text_kwargs["helpline_url"] = await i18n("moderation.helpline_url")
            response_text = await i18n(entry["i18n_key"], **text_kwargs)
            async with get_sessionmaker()() as session:
                await record_moderation_event(
                    session,
                    account_id=account.id,
                    tenant_id=account.tenant_id,
                    lang=i18n.lang,
                    category=verdict.category,
                    action=entry["action"],
                    source=source,
                    raw_text=q,
                )
                await session.commit()
            _log.info(
                "moderation.triggered",
                account_id=account.id,
                tenant_id=account.tenant_id,
                category=verdict.category.value,
                action=entry["action"].value,
                source=source,
                lang=i18n.lang,
            )
            await message.answer(
                response_text,
                reply_markup=await main_menu_kb(i18n, account.tenant_id),
            )
            return

    # Existing flow: profile → quota → request → qa → enqueue.
    async with get_sessionmaker()() as session:
        profile = await get_natal_profile(session, account.id)
        if profile is None:
            await message.answer(
                await i18n("qa.no_profile"),
                reply_markup=await profile_kb(has_profile=False, i18n=i18n),
            )
            return
        try:
            charged = await consume_quota(session, account.id, "qa")
        except InsufficientFundsError:
            await message.answer(
                await i18n("qa.no_quota"), reply_markup=await _buy_offer_kb(i18n)
            )
            return
        request = await create_request(
            session,
            tenant_id=account.tenant_id,
            account_id=account.id,
            kind="qa",
            charged_against=charged,
        )
        qa = await create_qa(
            session,
            tenant_id=account.tenant_id,
            account_id=account.id,
            natal_profile_id=profile.id,
            question=q,
            lang=i18n.lang,
        )

    if not await enqueue_or_refund(
        enqueue_qa(qa.id, message.chat.id, request.id),
        request_id=request.id,
    ):
        await message.answer(await i18n("errors.queue_failed"))
        return
    await message.answer(await i18n("qa.thinking"))


@router.message(Command("ask"))
async def on_ask(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    account: Account,
    i18n: Translator,
) -> None:
    if command.args and command.args.strip():
        await _submit(message, command.args, account, i18n)
    else:
        await start_ask(message, state, i18n)


@router.message(Ask.awaiting_question)
async def on_ask_question(
    message: Message, state: FSMContext, account: Account, i18n: Translator
) -> None:
    await state.clear()
    await _submit(message, message.text or "", account, i18n)
