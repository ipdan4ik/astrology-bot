from collections.abc import Awaitable

from quantuum.db.session import get_sessionmaker
from quantuum.domain.quota import refund_quota
from quantuum.logging_setup import get_logger

logger = get_logger(__name__)


async def enqueue_or_refund(coro: Awaitable[None], *, request_id: int) -> bool:
    """Await an enqueue coroutine; refund the request's charge if it fails.

    The charge (``consume_quota``) and the ``Request`` row are already committed
    by the time a handler enqueues, so a failed enqueue would otherwise leave the
    user charged with no worker job. On failure we open a fresh session and call
    the idempotent ``refund_quota``.

    Returns True if the job was enqueued, False if it failed and was refunded.
    """
    try:
        await coro
        return True
    except Exception:
        logger.exception("enqueue_failed", request_id=request_id)
        async with get_sessionmaker()() as session:
            await refund_quota(session, request_id)
        return False
