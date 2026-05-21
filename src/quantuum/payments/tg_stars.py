from typing import Literal

from quantuum.payments.base import Invoice, PaymentEvent, PaymentNotSupportedInApiError


class TgStarsProvider:
    """Telegram Stars (XTR). Invoices are sent in-bot via ``bot.send_invoice``; there is no
    HTTP create-invoice or callback path. This class is the abstraction seam used by the
    public API (which therefore returns 501 for Stars) and by future HTTP providers."""

    kind = "tg_stars"

    async def create_invoice(
        self,
        *,
        account_id: int,
        tenant_id: int,
        plan_kind: Literal["subscription", "package"],
        plan_id: int,
        amount_cents: int,
        currency: str,
        metadata: dict,
    ) -> Invoice:
        raise PaymentNotSupportedInApiError(
            "Telegram Stars payments are only available inside the bot"
        )

    async def verify_callback(self, body: bytes, headers: dict) -> PaymentEvent:
        raise PaymentNotSupportedInApiError(
            "Telegram Stars has no HTTP callback; events arrive via the bot"
        )

    async def refund(self, payment_id: int) -> bool:
        raise NotImplementedError("Stars refunds are out of scope for MVP")
