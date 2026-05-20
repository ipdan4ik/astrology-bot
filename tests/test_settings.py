
from quantuum.settings import Settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SIGNING_KEY", "secret")
    s = Settings()
    assert s.database_url.endswith("/db")
    assert s.jwt_access_ttl_seconds == 3600
    assert s.default_tenant_slug == "default"
