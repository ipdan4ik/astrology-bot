from quantuum.domain.llm_config import get_llm_config
from quantuum.domain.qa import get_qa, resolve_calc_md, set_qa_status
from quantuum.domain.quota import refund_quota
from quantuum.domain.requests import complete_request
from quantuum.llm.qa_answer import qa_answer
from quantuum.logging_setup import get_logger
from quantuum.tasks.delivery import deliver_via_tenant_bot

logger = get_logger("task.qa")


async def qa_generate(
    ctx, qa_id: int, chat_id: int | None = None, request_id: int | None = None
) -> None:
    sessionmaker = ctx["sessionmaker"]

    delivery_md = None
    tenant_id = None

    async with sessionmaker() as session:
        try:
            qa = await get_qa(session, qa_id)
            tenant_id = qa.tenant_id
            calc_md, blueprint_id = await resolve_calc_md(
                session, account_id=qa.account_id, natal_profile_id=qa.natal_profile_id
            )
            await set_qa_status(session, qa_id, "generating", blueprint_id=blueprint_id)

            llm_client = ctx.get("llm_client")

            if llm_client is None:
                await set_qa_status(session, qa_id, "failed", error="llm unavailable")
                if request_id is not None:
                    await refund_quota(session, request_id)
                return

            cfg = await get_llm_config(session)
            result = await qa_answer(
                llm_client,
                calc_md,
                qa.question,
                model=cfg["model"],
                temperature=cfg["temperature"],
                max_tokens=cfg["max_tokens"],
            )
            await set_qa_status(
                session,
                qa_id,
                "done",
                answer_md=result.text,
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
                        session, request_id, reference_id=qa_id, reference_type="qa"
                    )
                except Exception:
                    logger.exception("qa_complete_request_failed", qa_id=qa_id)
        except Exception:
            logger.exception("qa_generation_failed", qa_id=qa_id)
            try:
                await set_qa_status(session, qa_id, "failed", error="generation failed")
            except Exception:
                logger.exception("qa_set_failed_status_error", qa_id=qa_id)
            if request_id is not None:
                await refund_quota(session, request_id)
            return

    # Delivery is best-effort and must NOT trigger a refund of a successful generation.
    if chat_id is not None and delivery_md is not None and tenant_id is not None:
        try:
            await deliver_via_tenant_bot(
                sessionmaker,
                tenant_id=tenant_id,
                chat_id=chat_id,
                text=delivery_md,
                filename="answer.md",
                preview_len=4000,
                always_document=False,
            )
        except Exception:
            logger.exception("qa_delivery_failed", qa_id=qa_id, chat_id=chat_id)

    logger.info("qa_generated", qa_id=qa_id, chat_id=chat_id)
