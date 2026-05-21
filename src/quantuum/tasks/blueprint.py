from aiogram.types import BufferedInputFile

from quantuum.astrology.blueprint import build_blueprint, from_natal_profile
from quantuum.db.models import NatalProfile
from quantuum.domain.blueprints import get_blueprint, set_status
from quantuum.domain.quota import refund_quota
from quantuum.domain.requests import complete_request
from quantuum.llm.blueprint_polish import polish_blueprint
from quantuum.logging_setup import get_logger
from quantuum.settings import get_settings

logger = get_logger("task.blueprint")


async def blueprint_generate(
    ctx, blueprint_id: int, chat_id: int | None = None, request_id: int | None = None
) -> None:
    sessionmaker = ctx["sessionmaker"]
    bot = ctx["bot"]

    delivery_md = None

    async with sessionmaker() as session:
        try:
            bp = await get_blueprint(session, blueprint_id)
            profile = await session.get(NatalProfile, bp.natal_profile_id)

            inp = from_natal_profile(profile)
            calc_md = build_blueprint(inp)
            await set_status(session, blueprint_id, "calculating", calc_md=calc_md)
            await set_status(session, blueprint_id, "generating")

            settings = get_settings()
            llm_client = ctx.get("llm_client")

            if llm_client is not None:
                result = await polish_blueprint(
                    llm_client,
                    calc_md,
                    model=settings.llm_model,
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                )
                await set_status(
                    session,
                    blueprint_id,
                    "done",
                    llm_md=result.text,
                    llm_provider=settings.llm_provider,
                    llm_model=result.model,
                    llm_tokens_in=result.tokens_in,
                    llm_tokens_out=result.tokens_out,
                )
                delivery_md = result.text
            else:
                # No LLM key configured — graceful degradation.
                await set_status(
                    session,
                    blueprint_id,
                    "done",
                    llm_md=calc_md,
                    llm_provider="none",
                    llm_model="none",
                )
                delivery_md = calc_md

            if request_id is not None:
                # Generation already succeeded; request bookkeeping failure must not refund.
                try:
                    await complete_request(
                        session, request_id, reference_id=blueprint_id, reference_type="blueprint"
                    )
                except Exception:
                    logger.exception("blueprint_complete_request_failed", blueprint_id=blueprint_id)
        except Exception:
            logger.exception("blueprint_generation_failed", blueprint_id=blueprint_id)
            try:
                await set_status(session, blueprint_id, "failed", error="generation failed")
            except Exception:
                logger.exception("blueprint_set_failed_status_error", blueprint_id=blueprint_id)
            if request_id is not None:
                await refund_quota(session, request_id)
            return

    # Delivery is best-effort and must NOT trigger a refund of a successful generation.
    if chat_id is not None and delivery_md is not None:
        try:
            await bot.send_message(chat_id, delivery_md[:500])
            await bot.send_document(
                chat_id,
                BufferedInputFile(delivery_md.encode(), filename="blueprint.md"),
            )
        except Exception:
            logger.exception("blueprint_delivery_failed", blueprint_id=blueprint_id, chat_id=chat_id)

    logger.info("blueprint_generated", blueprint_id=blueprint_id, chat_id=chat_id)
