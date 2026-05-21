from quantuum.payments.base import PaymentProvider
from quantuum.payments.tg_stars import TgStarsProvider

PROVIDERS: dict[str, type[PaymentProvider]] = {
    "tg_stars": TgStarsProvider,
}


def provider_for_kind(kind: str) -> PaymentProvider | None:
    cls = PROVIDERS.get(kind)
    return cls() if cls is not None else None
