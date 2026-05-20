import contextvars
import logging

import structlog

from quantuum.settings import get_settings

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def bind_request_id(request_id: str | None) -> None:
    _request_id.set(request_id)


def _add_request_id(_logger, _method, event_dict):
    rid = _request_id.get()
    if rid is not None:
        event_dict["request_id"] = rid
    return event_dict


def configure_logging() -> None:
    renderer = (
        structlog.processors.JSONRenderer()
        if get_settings().log_json
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _add_request_id,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "quantuum"):
    return structlog.get_logger(name)
