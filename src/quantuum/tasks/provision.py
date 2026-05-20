from quantuum.db.models import Tenant
from quantuum.domain.provisioning import try_programmatic_create
from quantuum.logging_setup import get_logger

logger = get_logger("tasks.provision")

_MANUAL_TOKEN_PROMPT = (
    "Автосоздание бота недоступно. Создай нового бота через @BotFather "
    "и пришли сюда его токен одним сообщением."
)


async def provision_tenant(ctx, tenant_id: int) -> None:
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            logger.warning("provision_unknown_tenant", tenant_id=tenant_id)
            return
        token = await try_programmatic_create(slug=tenant.slug, display_name=tenant.display_name)
        if token is None:
            tenant.status = "awaiting_manual_token"
            session.add(tenant)
            await session.commit()
            master_bot = ctx.get("master_bot")
            if master_bot is not None and tenant.owner_chat_id:
                await master_bot.send_message(int(tenant.owner_chat_id), _MANUAL_TOKEN_PROMPT)
            logger.info("provision_awaiting_manual_token", tenant_id=tenant_id)
            return
        # Programmatic path is not used in MVP (try_programmatic_create always returns None).
        logger.info("provision_programmatic_unsupported", tenant_id=tenant_id)
