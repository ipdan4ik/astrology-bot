
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


def test_bot_reload_interval_default():
    from quantuum.settings import Settings

    assert Settings.model_fields["bot_reload_interval_seconds"].default == 10.0


def test_geocoder_settings_defaults():
    from quantuum.settings import Settings

    assert Settings.model_fields["geocoder_url"].default == "https://nominatim.openstreetmap.org"
    assert Settings.model_fields["geocoder_user_agent"].default == "quantuum-bot (onboarding geocoder)"


def test_moderation_settings_defaults():
    from quantuum.settings import Settings

    s = Settings(
        database_url="postgresql://x",
        redis_url="redis://x",
        jwt_signing_key="x",
    )
    assert s.moderation_enabled is True
    assert s.moderation_fail_open is True
    assert s.moderation_openai_model == "omni-moderation-latest"
    assert s.moderation_advice_model is None  # falls back to llm_model
    assert s.moderation_advice_max_tokens == 32
    assert s.moderation_advice_temperature == 0.0


def test_moderation_settings_env_override(monkeypatch):
    from quantuum.settings import Settings

    monkeypatch.setenv("MODERATION_ENABLED", "false")
    monkeypatch.setenv("MODERATION_ADVICE_MODEL", "gpt-4o-mini")
    s = Settings(
        database_url="postgresql://x",
        redis_url="redis://x",
        jwt_signing_key="x",
    )
    assert s.moderation_enabled is False
    assert s.moderation_advice_model == "gpt-4o-mini"
