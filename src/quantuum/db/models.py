from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, LargeBinary, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
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
    invite_id: int | None = Field(default=None, foreign_key="tenant_invites.id", index=True)
    created_at: datetime = _dt_field(default_factory=utcnow)


class TenantBot(SQLModel, table=True):
    __tablename__ = "tenant_bots"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    bot_telegram_id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, unique=True, index=True, nullable=True),
    )
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


class TenantInvite(SQLModel, table=True):
    __tablename__ = "tenant_invites"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True)
    created_by_account_id: int | None = Field(default=None, foreign_key="accounts.id")
    tier: str = "basic"  # basic|vip
    max_uses: int = 1
    used_count: int = 0
    expires_at: datetime | None = _dt_field(default=None)
    status: str = "active"  # active|used|expired|revoked
    preset_slug: str | None = None
    preset_display_name: str | None = None
    preset_username: str | None = None
    preset_default_lang: str | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)
    used_at: datetime | None = _dt_field(default=None)


class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, foreign_key="tenants.id", index=True)
    is_superadmin: bool = False
    status: str = "active"  # active|disabled
    ban_reason: str | None = None
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
    lang: str | None = None
    calc_md: str | None = None
    llm_md: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    error: str | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)
    completed_at: datetime | None = _dt_field(default=None)


class Reading(SQLModel, table=True):
    __tablename__ = "readings"
    __table_args__ = (Index("ix_readings_tenant_created", "tenant_id", "created_at"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    natal_profile_id: int = Field(foreign_key="natal_profiles.id")
    kind: str  # bazi|numerology|human_design|astrology|vedic|gene_keys|mayan|aspects
    status: str = "pending"  # pending|calculating|generating|done|failed
    lang: str | None = None
    calc_md: str | None = None
    llm_md: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    error: str | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)
    completed_at: datetime | None = _dt_field(default=None)
    draw_jsonb: dict | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )


class ModerationEvent(SQLModel, table=True):
    __tablename__ = "moderation_events"
    __table_args__ = (
        Index("ix_moderation_events_account_created", "account_id", "created_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    account_id: int | None = Field(default=None, foreign_key="accounts.id", index=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    lang: str | None = Field(default=None, max_length=8)
    category: str  # Category enum value
    action: str  # Action enum value
    source: str  # "openai" | "mini_llm"
    text_sha256: bytes = Field(
        sa_column=Column(LargeBinary(length=32), nullable=False),
    )
    text_preview: str = Field(max_length=80)
    created_at: datetime = _dt_field(default_factory=utcnow, index=True)


class QaAnswer(SQLModel, table=True):
    __tablename__ = "qa_answers"
    __table_args__ = (Index("ix_qa_answers_tenant_created", "tenant_id", "created_at"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    natal_profile_id: int = Field(foreign_key="natal_profiles.id")
    blueprint_id: int | None = Field(default=None, foreign_key="blueprints.id")
    question: str
    answer_md: str | None = None
    lang: str | None = None
    status: str = "pending"  # pending|generating|done|failed
    error: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)
    completed_at: datetime | None = _dt_field(default=None)


class TransitReport(SQLModel, table=True):
    __tablename__ = "transit_reports"
    __table_args__ = (Index("ix_transit_reports_tenant_created", "tenant_id", "created_at"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    natal_profile_id: int = Field(foreign_key="natal_profiles.id")
    blueprint_id: int | None = Field(default=None, foreign_key="blueprints.id")
    as_of: datetime | None = _dt_field(default=None)
    window_days: int = 90
    transit_md: str | None = None
    report_md: str | None = None
    lang: str | None = None
    status: str = "pending"  # pending|generating|done|failed
    error: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)
    completed_at: datetime | None = _dt_field(default=None)


class DailySubscription(SQLModel, table=True):
    __tablename__ = "daily_subscriptions"

    account_id: int = Field(foreign_key="accounts.id", primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    enabled: bool = False
    send_hour: int = 9  # user's preferred LOCAL hour, 0-23
    last_sent_on: date | None = None  # user's local date of last successful send
    created_at: datetime = _dt_field(default_factory=utcnow)
    updated_at: datetime = _dt_field(default_factory=utcnow)


class DailyHoroscope(SQLModel, table=True):
    __tablename__ = "daily_horoscopes"
    __table_args__ = (
        Index("ix_daily_horoscopes_tenant_created", "tenant_id", "created_at"),
        UniqueConstraint("account_id", "local_date", name="uq_daily_horoscope_account_date"),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    natal_profile_id: int = Field(foreign_key="natal_profiles.id")
    local_date: date
    transit_md: str | None = None
    horoscope_md: str | None = None
    lang: str | None = None
    # No "pending" state (unlike QaAnswer/TransitReport): the row is created only
    # when generation starts, via claim_horoscope (the unique guard claims the day).
    status: str = "generating"  # generating|done|failed
    error: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
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


class SubscriptionPlan(SQLModel, table=True):
    __tablename__ = "subscription_plans"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, foreign_key="tenants.id", index=True)
    slug: str = Field(index=True)
    name: str
    period_days: int  # MVP: integer days instead of calendar interval
    price_cents: int  # for XTR this is the integer Star amount
    currency: str = "XTR"
    active: bool = True
    created_at: datetime = _dt_field(default_factory=utcnow)


class PackagePlan(SQLModel, table=True):
    __tablename__ = "package_plans"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, foreign_key="tenants.id", index=True)
    slug: str = Field(index=True)
    name: str
    request_count: int
    price_cents: int  # for XTR this is the integer Star amount
    currency: str = "XTR"
    expires_after_days: int | None = None  # NULL = never expires
    active: bool = True
    created_at: datetime = _dt_field(default_factory=utcnow)


class PaymentProvider(SQLModel, table=True):
    __tablename__ = "payment_providers"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    kind: str  # tg_stars|cloudpayments|cryptobot
    config_enc: bytes = b""
    active: bool = True
    created_at: datetime = _dt_field(default_factory=utcnow)


class Payment(SQLModel, table=True):
    __tablename__ = "payments"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    provider_id: int | None = Field(default=None, foreign_key="payment_providers.id")
    amount_cents: int
    currency: str = "XTR"
    external_id: str | None = Field(default=None, index=True)
    status: str = "pending"  # pending|paid|refunded|failed
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default="{}"))
    created_at: datetime = _dt_field(default_factory=utcnow)
    paid_at: datetime | None = _dt_field(default=None)
    refunded_at: datetime | None = _dt_field(default=None)


class AccountSubscription(SQLModel, table=True):
    __tablename__ = "account_subscriptions"
    __table_args__ = (
        Index(
            "uq_active_subscription_per_plan",
            "tenant_id",
            "account_id",
            "plan_id",
            unique=True,
            postgresql_where=text("status IN ('active','grace')"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    plan_id: int = Field(foreign_key="subscription_plans.id")
    status: str = "active"  # active|grace|expired|cancelled
    started_at: datetime = _dt_field(default_factory=utcnow)
    ends_at: datetime = _dt_field(default_factory=utcnow)
    renewed_at: datetime | None = _dt_field(default=None)
    cancelled_at: datetime | None = _dt_field(default=None)
    reminder_sent_at: datetime | None = _dt_field(default=None)
    payment_id: int | None = Field(default=None, foreign_key="payments.id")
    created_at: datetime = _dt_field(default_factory=utcnow)


class AccountPackage(SQLModel, table=True):
    __tablename__ = "account_packages"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    plan_id: int | None = Field(default=None, foreign_key="package_plans.id")
    source: str = "purchase"  # purchase|gift|referral|welcome|manual|backfill
    requests_remaining: int
    purchased_at: datetime = _dt_field(default_factory=utcnow)
    expires_at: datetime | None = _dt_field(default=None)
    payment_id: int | None = Field(default=None, foreign_key="payments.id")
    created_at: datetime = _dt_field(default_factory=utcnow)


class Payout(SQLModel, table=True):
    __tablename__ = "payouts"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    period_start: datetime = _dt_field()
    period_end: datetime = _dt_field()
    gross_amount_cents: int
    platform_fee_cents: int
    net_amount_cents: int
    currency: str = "XTR"
    status: str = "calculated"  # calculated|paid
    paid_at: datetime | None = _dt_field(default=None)
    external_ref: str | None = None
    calculated_by_account_id: int | None = Field(default=None, foreign_key="accounts.id")
    created_at: datetime = _dt_field(default_factory=utcnow)


class TenantLicense(SQLModel, table=True):
    __tablename__ = "tenant_licenses"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    status: str = "active"  # active|expired|cancelled
    started_at: datetime = _dt_field(default_factory=utcnow)
    ends_at: datetime | None = _dt_field(default=None)
    price_cents: int
    currency: str = "XTR"
    payment_provider_id: int | None = Field(default=None, foreign_key="payment_providers.id")
    created_at: datetime = _dt_field(default_factory=utcnow)


class PlatformConfig(SQLModel, table=True):
    __tablename__ = "platform_config"
    key: str = Field(primary_key=True)
    value_jsonb: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    updated_at: datetime = _dt_field(default_factory=utcnow)
    updated_by_account_id: int | None = Field(default=None, foreign_key="accounts.id")


class TenantConfig(SQLModel, table=True):
    __tablename__ = "tenant_config"
    tenant_id: int = Field(foreign_key="tenants.id", primary_key=True)
    key: str = Field(primary_key=True)
    value_jsonb: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    updated_at: datetime = _dt_field(default_factory=utcnow)
    updated_by_account_id: int | None = Field(default=None, foreign_key="accounts.id")


class PlatformString(SQLModel, table=True):
    __tablename__ = "platform_strings"
    key: str = Field(primary_key=True)
    lang: str = Field(primary_key=True)
    text: str


class TenantStringOverride(SQLModel, table=True):
    __tablename__ = "tenant_string_overrides"
    tenant_id: int = Field(foreign_key="tenants.id", primary_key=True)
    key: str = Field(primary_key=True)
    lang: str = Field(primary_key=True)
    text: str
    updated_at: datetime = _dt_field(default_factory=utcnow)
    updated_by_account_id: int | None = Field(default=None, foreign_key="accounts.id")


class TenantLanguage(SQLModel, table=True):
    __tablename__ = "tenant_languages"
    __table_args__ = (
        Index(
            "uq_tenant_default_language",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_default = true"),
        ),
    )
    tenant_id: int = Field(foreign_key="tenants.id", primary_key=True)
    lang: str = Field(primary_key=True)
    enabled: bool = True
    is_default: bool = False
    created_at: datetime = _dt_field(default_factory=utcnow)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_tenant_created", "tenant_id", "created_at"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int | None = Field(default=None, foreign_key="tenants.id", index=True)
    actor_account_id: int | None = Field(default=None, foreign_key="accounts.id")
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    payload_jsonb: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime = _dt_field(default_factory=utcnow)


class StartToken(SQLModel, table=True):
    __tablename__ = "start_tokens"

    code: str = Field(primary_key=True, max_length=64)
    kind: str = Field(index=True)  # referral | discount | promo | ...
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    owner_account_id: int | None = Field(default=None, foreign_key="accounts.id", index=True)
    payload: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default="{}")
    )
    status: str = "active"  # active | disabled
    max_uses: int | None = Field(default=None)
    used_count: int = 0
    expires_at: datetime | None = _dt_field(default=None)
    created_at: datetime = _dt_field(default_factory=utcnow)


class StartTokenUse(SQLModel, table=True):
    __tablename__ = "start_token_uses"

    id: int | None = Field(default=None, primary_key=True)
    token_code: str = Field(foreign_key="start_tokens.code", index=True)
    account_id: int = Field(foreign_key="accounts.id")
    used_at: datetime = _dt_field(default_factory=utcnow)
    claimed_at: datetime | None = _dt_field(default=None)
