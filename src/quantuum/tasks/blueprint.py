from aiogram.types import BufferedInputFile

from quantuum.domain.blueprints import set_status
from quantuum.domain.mock_blueprint import MOCK_BLUEPRINT_MD
from quantuum.logging_setup import get_logger

logger = get_logger("task.blueprint")


async def blueprint_generate(ctx, blueprint_id: int, chat_id: int | None = None) -> None:
    sessionmaker = ctx["sessionmaker"]
    bot = ctx["bot"]

    async with sessionmaker() as session:
        await set_status(session, blueprint_id, "calculating", calc_md=MOCK_BLUEPRINT_MD)
        await set_status(
            session,
            blueprint_id,
            "done",
            llm_md=MOCK_BLUEPRINT_MD,
            llm_provider="mock",
            llm_model="mock",
        )

    if chat_id is not None:
        await bot.send_message(chat_id, MOCK_BLUEPRINT_MD[:500])
        await bot.send_document(
            chat_id,
            BufferedInputFile(MOCK_BLUEPRINT_MD.encode(), filename="blueprint.md"),
        )

    logger.info("blueprint_generated", blueprint_id=blueprint_id, chat_id=chat_id)
