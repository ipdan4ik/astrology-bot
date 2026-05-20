from cryptography.fernet import Fernet

from quantuum.settings import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().bot_token_enc_key.encode())


def encrypt_token(token: str) -> bytes:
    return _fernet().encrypt(token.encode())


def decrypt_token(blob: bytes) -> str:
    return _fernet().decrypt(blob).decode()
