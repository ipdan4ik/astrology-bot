from quantuum.common.crypto import decrypt_token, encrypt_token


def test_encrypt_decrypt_roundtrip():
    token = "811895373:AAEHJCCl-secret"
    blob = encrypt_token(token)
    assert isinstance(blob, bytes)
    assert blob != token.encode()
    assert decrypt_token(blob) == token
