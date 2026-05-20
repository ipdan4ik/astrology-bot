import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from quantuum.api.routes import auth, health, me, webhook
from quantuum.db.bootstrap import ensure_default_tenant
from quantuum.db.session import get_sessionmaker
from quantuum.logging_setup import bind_request_id, configure_logging


@asynccontextmanager
async def _lifespan(app: FastAPI):
    async with get_sessionmaker()() as session:
        await ensure_default_tenant(session)
    yield


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Quantuum API", lifespan=_lifespan)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        bind_request_id(request_id)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(webhook.router)

    from quantuum.common.exceptions import NotFoundError
    from fastapi.responses import JSONResponse

    @app.exception_handler(NotFoundError)
    async def _not_found(_request, _exc):
        return JSONResponse(status_code=404, content={"detail": "not found"})

    return app
