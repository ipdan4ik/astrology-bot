import uuid

from fastapi import FastAPI, Request

from quantuum.api.routes import auth, health, me
from quantuum.logging_setup import bind_request_id, configure_logging


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Quantuum API")

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
    return app
