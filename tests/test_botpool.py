from quantuum.bot.botpool import build_bots
from quantuum.common.crypto import encrypt_token
from quantuum.db.models import TenantBot


def test_build_bots_keyed_by_bot_id():
    rows = [
        TenantBot(tenant_id=1, bot_telegram_id=111, bot_token_enc=encrypt_token("111:aaa"),
                  webhook_secret_path="a"),
        TenantBot(tenant_id=2, bot_telegram_id=222, bot_token_enc=encrypt_token("222:bbb"),
                  webhook_secret_path="b"),
    ]
    bots = build_bots(rows)
    assert set(bots.keys()) == {111, 222}
    assert bots[111].id == 111
    assert bots[222].id == 222


def test_build_bots_skips_rows_without_telegram_id():
    rows = [TenantBot(tenant_id=1, bot_telegram_id=None, bot_token_enc=encrypt_token("9:x"),
                      webhook_secret_path="z")]
    assert build_bots(rows) == {}
