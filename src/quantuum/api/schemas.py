from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, EmailStr


class MagicRequestIn(BaseModel):
    email: EmailStr


class MagicRequestOut(BaseModel):
    sent: bool


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str


class RefreshIn(BaseModel):
    refresh_token: str


class MeOut(BaseModel):
    account_id: int
    tenant_id: int | None


class NatalProfileIn(BaseModel):
    full_name: str
    birth_date: date
    birth_time: time
    birth_place: str
    latitude: Decimal
    longitude: Decimal
    timezone: str
    for_year: int | None = None


class NatalProfileOut(NatalProfileIn):
    id: int


class BlueprintOut(BaseModel):
    id: int
    status: str
    created_at: str
    completed_at: str | None = None


class BlueprintCreatedOut(BaseModel):
    id: int
    status: str


class InviteCreateIn(BaseModel):
    tier: str = "basic"
    max_uses: int = 1
    expires_at: datetime | None = None
    preset_slug: str | None = None
    preset_display_name: str | None = None
    preset_username: str | None = None
    preset_default_lang: str | None = None


class InviteOut(BaseModel):
    id: int
    code: str
    tier: str
    max_uses: int
    used_count: int
    status: str
    deeplink: str


class TenantOut(BaseModel):
    id: int
    slug: str
    display_name: str
    tier: str
    status: str
    is_platform: bool


class BalanceOut(BaseModel):
    free_trial_used: bool
    subscription_active_until: str | None
    package_credits: int


class SubscriptionPlanOut(BaseModel):
    id: int
    slug: str
    name: str
    period_days: int
    price_cents: int
    currency: str


class PackagePlanOut(BaseModel):
    id: int
    slug: str
    name: str
    request_count: int
    price_cents: int
    currency: str
    expires_after_days: int | None


class PlansOut(BaseModel):
    subscriptions: list[SubscriptionPlanOut]
    packages: list[PackagePlanOut]


class SubscriptionOut(BaseModel):
    id: int
    plan_id: int
    status: str
    started_at: str
    ends_at: str


class PaymentOut(BaseModel):
    id: int
    amount_cents: int
    currency: str
    status: str
    created_at: str
    paid_at: str | None


class SubscriptionPlanCreateIn(BaseModel):
    slug: str
    name: str
    period_days: int
    price_cents: int
    currency: str = "XTR"
    tenant_id: int | None = None


class PackagePlanCreateIn(BaseModel):
    slug: str
    name: str
    request_count: int
    price_cents: int
    currency: str = "XTR"
    expires_after_days: int | None = None
    tenant_id: int | None = None


class SubscriptionPlanPatchIn(BaseModel):
    name: str | None = None
    period_days: int | None = None
    price_cents: int | None = None
    active: bool | None = None


class PackagePlanPatchIn(BaseModel):
    name: str | None = None
    request_count: int | None = None
    price_cents: int | None = None
    expires_after_days: int | None = None
    active: bool | None = None


class SubscriptionPlanAdminOut(SubscriptionPlanOut):
    active: bool
    tenant_id: int | None


class PackagePlanAdminOut(PackagePlanOut):
    active: bool
    tenant_id: int | None


class PurchaseIn(BaseModel):
    plan_id: int


class PayoutCalculateIn(BaseModel):
    tenant_id: int
    period_start: datetime
    period_end: datetime


class PayoutMarkPaidIn(BaseModel):
    external_ref: str


class PayoutOut(BaseModel):
    id: int
    tenant_id: int
    period_start: str
    period_end: str
    gross_amount_cents: int
    platform_fee_cents: int
    net_amount_cents: int
    currency: str
    status: str
    external_ref: str | None
    paid_at: str | None


class TenantBotBrief(BaseModel):
    username: str | None
    status: str


class TenantDetailOut(BaseModel):
    id: int
    slug: str
    display_name: str
    status: str
    tier: str
    is_platform: bool
    primary_owner_account_id: int | None
    created_at: str
    bot: TenantBotBrief | None


class TenantPatchIn(BaseModel):
    display_name: str | None = None
    tier: str | None = None


class RoleIn(BaseModel):
    account_id: int
    role: str


class RoleOut(BaseModel):
    id: int
    account_id: int
    role: str
    granted_at: datetime


class TransferIn(BaseModel):
    new_owner_account_id: int
    revoke_previous: bool = False


# ---------------------------------------------------------------------------
# i18n / config schemas (Plan 5b, Tasks 7-9)
# ---------------------------------------------------------------------------


class LanguageItem(BaseModel):
    lang: str
    enabled: bool
    is_default: bool


class LanguagesPutIn(BaseModel):
    languages: list[LanguageItem]


class LanguageOut(BaseModel):
    lang: str
    enabled: bool
    is_default: bool


class StringOverrideIn(BaseModel):
    key: str
    lang: str
    text: str


class StringOut(BaseModel):
    key: str
    lang: str
    text: str
    is_override: bool


class ConfigPutIn(BaseModel):
    key: str
    value: dict


# ---------------------------------------------------------------------------
# Tenant plans + accounts schemas (Plan 5b, Tasks 10-11)
# ---------------------------------------------------------------------------


class TenantPlansOut(BaseModel):
    subscriptions: list["SubscriptionPlanAdminOut"]
    packages: list["PackagePlanAdminOut"]


class AccountSummaryOut(BaseModel):
    id: int
    created_at: datetime
    last_seen_at: datetime | None
    package_credits: int
    subscription_active_until: datetime | None


class BalancePatchIn(BaseModel):
    package_credits: int | None = None
    subscription_active_until: datetime | None = None


# ---------------------------------------------------------------------------
# Tenant stats schema (Plan 5b, Task 12)
# ---------------------------------------------------------------------------


class TenantStatsOut(BaseModel):
    period_days: int
    active_customers: int
    paid_customers: int
    dau: int
    wau: int
    mau: int
    requests_by_kind: dict[str, int]
    revenue_cents: int
    mrr_cents: int
    llm_tokens_in: int
    llm_tokens_out: int
