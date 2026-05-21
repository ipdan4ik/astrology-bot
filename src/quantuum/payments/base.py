from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


class PaymentNotSupportedInApiError(Exception):
    """Raised when a provider cannot create an invoice outside its native channel.

    Telegram Stars invoices can only be sent inside the bot (via ``bot.send_invoice``),
    so there is no public-API create-invoice path for them in MVP.
    """


@dataclass
class Invoice:
    title: str
    description: str
    payload: str
    currency: str
    amount: int  # smallest currency unit; for XTR this is the integer Star amount


@dataclass
class PaymentEvent:
    external_id: str
    payment_id: int
    amount: int
    currency: str


@runtime_checkable
class PaymentProvider(Protocol):
    kind: str

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
    ) -> Invoice: ...

    async def verify_callback(self, body: bytes, headers: dict) -> PaymentEvent: ...

    async def refund(self, payment_id: int) -> bool: ...
