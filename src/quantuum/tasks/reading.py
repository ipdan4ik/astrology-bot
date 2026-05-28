from quantuum.astrology.blueprint import from_natal_profile
from quantuum.astrology.sections import build_reading_calc_md
from quantuum.bot.rendering.signature import append_signature
from quantuum.db.models import NatalProfile
from quantuum.divination import build_divination_calc_md
from quantuum.domain.llm_config import get_llm_config
from quantuum.domain.quota import refund_quota
from quantuum.domain.readings import get_reading, set_reading_status
from quantuum.domain.requests import complete_request
from quantuum.i18n.strings import get_tenant_default_lang
from quantuum.llm.reading_polish import polish_reading
from quantuum.logging_setup import get_logger
from quantuum.tasks.delivery import deliver_via_tenant_bot

logger = get_logger("task.reading")


async def reading_generate(
    ctx, reading_id: int, chat_id: int | None = None, request_id: int | None = None
) -> None:
    sessionmaker = ctx["sessionmaker"]
    delivery_md = None
    tenant_id = None
    kind = None

    async with sessionmaker() as session:
        try:
            reading = await get_reading(session, reading_id)
            tenant_id = reading.tenant_id
            kind = reading.kind

            if reading.kind in ("tarot", "iching"):
                calc_md = build_divination_calc_md(reading.kind, reading.draw_jsonb)
            else:
                profile = await session.get(NatalProfile, reading.natal_profile_id)
                inp = from_natal_profile(profile)
                calc_md = build_reading_calc_md(reading.kind, inp)
            await set_reading_status(session, reading_id, "calculating", calc_md=calc_md)
            await set_reading_status(session, reading_id, "generating")

            cfg = await get_llm_config(session)
            llm_client = ctx.get("llm_client")
            lang = reading.lang or await get_tenant_default_lang(session, tenant_id) or "ru"

            if llm_client is None:
                await set_reading_status(
                    session, reading_id, "done",
                    llm_md=calc_md, llm_provider="none", llm_model="none",
                )
                delivery_md = calc_md
            else:
                result = await polish_reading(
                    llm_client, reading.kind, calc_md,
                    lang=lang, model=cfg["model"],
                    temperature=cfg["temperature"], max_tokens=cfg["max_tokens"],
                )
                await set_reading_status(
                    session, reading_id, "done",
                    llm_md=result.text,
                    llm_provider=cfg["provider"], llm_model=result.model,
                    llm_tokens_in=result.tokens_in, llm_tokens_out=result.tokens_out,
                )
                delivery_md = result.text

            if request_id is not None:
                # Generation already succeeded; request bookkeeping failure must not refund.
                try:
                    await complete_request(
                        session, request_id,
                        reference_id=reading_id, reference_type="reading",
                    )
                except Exception:
                    logger.exception("reading_complete_request_failed", reading_id=reading_id)
        except Exception:
            logger.exception("reading_generation_failed", reading_id=reading_id)
            try:
                await set_reading_status(session, reading_id, "failed", error="generation failed")
            except Exception:
                logger.exception("reading_set_failed_status_error", reading_id=reading_id)
            if request_id is not None:
                await refund_quota(session, request_id)
            return

    # Delivery is best-effort and must NOT trigger a refund of a successful generation.
    if chat_id is not None and delivery_md is not None and tenant_id is not None:
        try:
            delivery_md = await append_signature(
                delivery_md, tenant_id=tenant_id, lang=lang
            )
            await deliver_via_tenant_bot(
                sessionmaker,
                tenant_id=tenant_id,
                chat_id=chat_id,
                text=delivery_md,
                filename=f"reading-{kind}.md",
                preview_len=4000,
                always_document=False,
            )
        except Exception:
            logger.exception("reading_delivery_failed", reading_id=reading_id, chat_id=chat_id)

    logger.info("reading_generated", reading_id=reading_id, chat_id=chat_id)
