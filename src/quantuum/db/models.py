from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlmodel import Field, SQLModel

from quantuum.common.datetime import utcnow


def _dt_field(**kwargs):
    """Return a SQLModel Field backed by TIMESTAMPTZ (timezone-aware)."""
    sa_type = DateTime(timezone=True)
    return Field(sa_type=sa_type, **kwargs)


class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"

    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    display_name: str
    status: str = "active"  # active|suspended|archived
    tier: str = "basic"  # basic|vip
    is_platform: bool = False
    primary_owner_account_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("accounts.id", use_alter=True, name="fk_tenants_primary_owner_account_id"),
            nullable=True,
        ),
    )
    owner_tg_id: str | None = None
    owner_chat_id: str | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)


class TenantBot(SQLModel, table=True):
    __tablename__ = "tenant_bots"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    bot_telegram_id: int | None = Field(default=None, unique=True, index=True)
    bot_username: str | None = None
    bot_token_enc: bytes
    transport: str = "polling"  # polling|webhook
    webhook_secret_path: str = Field(unique=True, index=True)
    status: str = "active"  # active|paused|error
    created_at: datetime = _dt_field(default_factory=utcnow)
    updated_at: datetime = _dt_field(default_factory=utcnow)


class TenantRole(SQLModel, table=True):
    __tablename__ = "tenant_roles"
    __table_args__ = (UniqueConstraint("tenant_id", "account_id", "role"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    role: str  # owner|admin|...
    granted_by_account_id: int | None = Field(default=None, foreign_key="accounts.id")
    granted_at: datetime = _dt_field(default_factory=utcnow)


class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    status: str = "active"  # active|disabled
    preferred_lang: str | None = None
    last_seen_at: datetime | None = _dt_field(default=None)
    created_at: datetime = _dt_field(default_factory=utcnow)


class AccountIdentity(SQLModel, table=True):
    __tablename__ = "account_identities"

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    provider: str  # tg_chat|magic_link
    provider_user_id: str | None = Field(default=None, index=True)
    email: str | None = Field(default=None, index=True)
    verified_at: datetime = _dt_field(default_factory=utcnow)
    created_at: datetime = _dt_field(default_factory=utcnow)


class AccountRefreshToken(SQLModel, table=True):
    __tablename__ = "account_refresh_tokens"

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    token_hash: str = Field(index=True)
    expires_at: datetime = _dt_field()
    revoked_at: datetime | None = _dt_field(default=None)
    created_at: datetime = _dt_field(default_factory=utcnow)


class NatalProfile(SQLModel, table=True):
    __tablename__ = "natal_profiles"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", unique=True, index=True)
    full_name: str
    birth_date: date
    birth_time: time
    birth_place: str
    latitude: Decimal
    longitude: Decimal
    timezone: str
    for_year: int | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)
    updated_at: datetime = _dt_field(default_factory=utcnow)


class Blueprint(SQLModel, table=True):
    __tablename__ = "blueprints"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    natal_profile_id: int = Field(foreign_key="natal_profiles.id")
    status: str = "pending"  # pending|calculating|generating|done|failed
    calc_md: str | None = None
    llm_md: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    error: str | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)
    completed_at: datetime | None = _dt_field(default=None)


class Request(SQLModel, table=True):
    __tablename__ = "requests"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    kind: str  # blueprint
    reference_id: int | None = None
    reference_type: str | None = None
    status: str = "pending"  # pending|done|failed|refunded
    cost_units: int = 1
    charged_against: str | None = None  # trial|subscription|package|none
    created_at: datetime = _dt_field(default_factory=utcnow)
    completed_at: datetime | None = _dt_field(default=None)


class AccountBalance(SQLModel, table=True):
    __tablename__ = "account_balance"

    account_id: int = Field(foreign_key="accounts.id", primary_key=True)
    free_trial_used: bool = False
    subscription_active_until: datetime | None = _dt_field(default=None)
    package_credits: int = 0
    updated_at: datetime = _dt_field(default_factory=utcnow)
