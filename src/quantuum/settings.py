from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    jwt_signing_key: str
    jwt_access_ttl_seconds: int = 3600
    jwt_refresh_ttl_seconds: int = 2_592_000
    bot_token: str = ""
    webhook_secret_path: str = ""
    api_host: str = "http://localhost:8000"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "noreply@quantuum.example"
    default_tenant_slug: str = "default"
    default_tenant_name: str = "Quantuum"
    magic_link_ttl_seconds: int = 900
    log_json: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
