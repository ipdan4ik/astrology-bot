import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from quantuum.api.routes import admin_payouts, admin_platform, admin_tenants, auth, billing, health, me, webhook
from quantuum.db.bootstrap import (
    ensure_base_strings,
    ensure_default_tenant,
    ensure_default_tenant_bot,
    ensure_global_plans,
    ensure_master_bot,
    ensure_platform_stars_provider,
    ensure_platform_tenant,
    ensure_superadmin,
    ensure_tenant_default_language,
)
from quantuum.db.session import get_sessionmaker
from quantuum.domain.tenants import get_default_tenant_id
from quantuum.logging_setup import bind_request_id, configure_logging


@asynccontextmanager
async def _lifespan(app: FastAPI):
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
        await ensure_default_tenant_bot(session)
        platform = await ensure_platform_tenant(session)
        await ensure_master_bot(session)
        await ensure_superadmin(session)
        await ensure_global_plans(session)
        await ensure_platform_stars_provider(session)
        await ensure_base_strings(session)
        default_tenant_id = await get_default_tenant_id(session)
        await ensure_tenant_default_language(session, default_tenant_id)
        await ensure_tenant_default_language(session, platform.id, default_lang="ru")
    yield


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Quantuum API", lifespan=_lifespan)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        bind_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            bind_request_id(None)
        response.headers["x-request-id"] = request_id
        return response

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(webhook.router)
    app.include_router(admin_platform.router)
    app.include_router(admin_tenants.router)
    app.include_router(billing.router)
    app.include_router(admin_payouts.router)

    from quantuum.common.exceptions import NotFoundError
    from fastapi.responses import JSONResponse

    @app.exception_handler(NotFoundError)
    async def _not_found(_request, _exc):
        return JSONResponse(status_code=404, content={"detail": "not found"})

    return app
