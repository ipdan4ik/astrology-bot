class DomainError(Exception):
    """Base class for domain-level errors."""


class NotFoundError(DomainError):
    pass


class InsufficientFundsError(DomainError):
    pass


class NatalProfileMissingError(DomainError):
    pass
