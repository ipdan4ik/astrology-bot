
from quantuum.settings import Settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SIGNING_KEY", "secret")
    s = Settings()
    assert s.database_url.endswith("/db")
    assert s.jwt_access_ttl_seconds == 3600
    assert s.default_tenant_slug == "default"


def test_settings_have_2b_defaults():
    # Assert the DECLARED field defaults, not a constructed instance — Settings reads the
    # real .env (env_file=".env"), so a populated .env (e.g. a real MASTER_BOT_TOKEN) must
    # not break this test.
    defaults = Settings.model_fields
    assert defaults["master_bot_token"].default == ""
    assert defaults["master_bot_username"].default == ""
    assert defaults["bootstrap_superadmin_email"].default == ""
    assert defaults["platform_tenant_slug"].default == "platform"
    assert defaults["platform_tenant_name"].default == "Quantuum Platform"
