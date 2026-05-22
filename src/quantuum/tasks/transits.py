from quantuum.astrology.transits import compute_transits, render_transits_md
from quantuum.common.datetime import utcnow
from quantuum.domain.llm_config import get_llm_config
from quantuum.domain.quota import refund_quota
from quantuum.domain.requests import complete_request
from quantuum.domain.transits import get_transit, resolve_natal, set_transit_status
from quantuum.i18n import resolve_lang
from quantuum.llm.transit_report import transit_report
from quantuum.logging_setup import get_logger
from quantuum.tasks.delivery import deliver_via_tenant_bot

logger = get_logger("task.transits")


async def transit_generate(
    ctx, report_id: int, chat_id: int | None = None, request_id: int | None = None
) -> None:
    sessionmaker = ctx["sessionmaker"]

    delivery_md = None
    tenant_id = None

    async with sessionmaker() as session:
        try:
            row = await get_transit(session, report_id)
            tenant_id = row.tenant_id
            inp, natal_md, blueprint_id = await resolve_natal(
                session, account_id=row.account_id, natal_profile_id=row.natal_profile_id
            )
            as_of = utcnow()
            computed = compute_transits(inp, as_of=as_of, window_days=row.window_days)
            transit_md = render_transits_md(computed)
            await set_transit_status(
                session,
                report_id,
                "generating",
                blueprint_id=blueprint_id,
                as_of=as_of,
                transit_md=transit_md,
            )

            llm_client = ctx.get("llm_client")
            if llm_client is None:
                await set_transit_status(session, report_id, "failed", error="llm unavailable")
                if request_id is not None:
                    await refund_quota(session, request_id)
                return

            cfg = await get_llm_config(session)
            result = await transit_report(
                llm_client,
                natal_md,
                transit_md,
                lang=await resolve_lang(
                    session,
                    tenant_id=row.tenant_id,
                    preferred_lang=row.lang,
                    tg_language_code=None,
                ),
                model=cfg["model"],
                temperature=cfg["temperature"],
                max_tokens=cfg["max_tokens"],
            )
            await set_transit_status(
                session,
                report_id,
                "done",
                report_md=result.text,
                llm_provider=cfg["provider"],
                llm_model=result.model,
                llm_tokens_in=result.tokens_in,
                llm_tokens_out=result.tokens_out,
            )
            delivery_md = result.text

            if request_id is not None:
                # Generation already succeeded; request bookkeeping failure must not refund.
                try:
                    await complete_request(
                        session, request_id, reference_id=report_id, reference_type="transit"
                    )
                except Exception:
                    logger.exception("transit_complete_request_failed", report_id=report_id)
        except Exception:
            logger.exception("transit_generation_failed", report_id=report_id)
            try:
                await set_transit_status(session, report_id, "failed", error="generation failed")
            except Exception:
                logger.exception("transit_set_failed_status_error", report_id=report_id)
            if request_id is not None:
                await refund_quota(session, request_id)
            return

    # Delivery is best-effort and must NOT trigger a refund of a successful report.
    if chat_id is not None and delivery_md is not None and tenant_id is not None:
        try:
            await deliver_via_tenant_bot(
                sessionmaker,
                tenant_id=tenant_id,
                chat_id=chat_id,
                text=delivery_md,
                filename="transits.md",
                preview_len=4000,
                always_document=False,
            )
        except Exception:
            logger.exception("transit_delivery_failed", report_id=report_id, chat_id=chat_id)

    logger.info("transit_generated", report_id=report_id, chat_id=chat_id)
