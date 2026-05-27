from quantuum.db.models import StartToken, StartTokenUse


def test_models_importable():
    assert StartToken.__tablename__ == "start_tokens"
    assert StartTokenUse.__tablename__ == "start_token_uses"


def test_start_token_defaults():
    token = StartToken(code="ABC23K7Q", kind="referral", tenant_id=1)
    assert token.status == "active"
    assert token.used_count == 0
    assert token.payload == {}
    assert token.max_uses is None
    assert token.owner_account_id is None
    assert token.expires_at is None


def test_start_token_use_defaults():
    use = StartTokenUse(token_code="ABC23K7Q", account_id=42)
    assert use.claimed_at is None
