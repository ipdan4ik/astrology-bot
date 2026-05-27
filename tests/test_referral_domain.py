import pytest

from quantuum.db.models import StartToken, StartTokenUse


def test_models_importable():
    assert StartToken.__tablename__ == "start_tokens"
    assert StartTokenUse.__tablename__ == "start_token_uses"
