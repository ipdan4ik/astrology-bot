import secrets


def url_safe_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)
