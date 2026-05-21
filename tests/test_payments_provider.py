import pytest

from quantuum.payments.base import Invoice, PaymentNotSupportedInApiError
from quantuum.payments.registry import provider_for_kind
from quantuum.payments.tg_stars import TgStarsProvider


def test_invoice_dataclass():
    inv = Invoice(title="t", description="d", payload="7", currency="XTR", amount=250)
    assert inv.payload == "7"
    assert inv.amount == 250


def test_registry_resolves_tg_stars():
    impl = provider_for_kind("tg_stars")
    assert isinstance(impl, TgStarsProvider)
    assert impl.kind == "tg_stars"


def test_registry_unknown_kind_returns_none():
    assert provider_for_kind("cloudpayments") is None


async def test_tg_stars_create_invoice_not_supported_in_api():
    impl = TgStarsProvider()
    with pytest.raises(PaymentNotSupportedInApiError):
        await impl.create_invoice(
            account_id=1, tenant_id=1, plan_kind="subscription", plan_id=1,
            amount_cents=250, currency="XTR", metadata={},
        )
