from aiogram.types import BufferedInputFile

from quantuum.domain.blueprints import set_status
from quantuum.domain.mock_blueprint import MOCK_BLUEPRINT_MD
from quantuum.domain.quota import refund_quota
from quantuum.domain.requests import complete_request
from quantuum.logging_setup import get_logger

logger = get_logger("task.blueprint")


async def blueprint_generate(
    ctx, blueprint_id: int, chat_id: int | None = None, request_id: int | None = None
) -> None:
    sessionmaker = ctx["sessionmaker"]
    bot = ctx["bot"]

    async with sessionmaker() as session:
        try:
            await set_status(session, blueprint_id, "calculating", calc_md=MOCK_BLUEPRINT_MD)
            await set_status(
                session,
                blueprint_id,
                "done",
                llm_md=MOCK_BLUEPRINT_MD,
                llm_provider="mock",
                llm_model="mock",
            )
            if request_id is not None:
                await complete_request(
                    session, request_id, reference_id=blueprint_id, reference_type="blueprint"
                )
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
    if chat_id is not None:
        try:
            await bot.send_message(chat_id, MOCK_BLUEPRINT_MD[:500])
            await bot.send_document(
                chat_id,
                BufferedInputFile(MOCK_BLUEPRINT_MD.encode(), filename="blueprint.md"),
            )
        except Exception:
            logger.exception("blueprint_delivery_failed", blueprint_id=blueprint_id, chat_id=chat_id)

    logger.info("blueprint_generated", blueprint_id=blueprint_id, chat_id=chat_id)
