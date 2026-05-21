"""Per-tenant real-time statistics (Plan 5b, Task 12)."""
from datetime import timedelta

from sqlalchemy import distinct, func
from sqlmodel import select

from quantuum.common.datetime import utcnow
from quantuum.db.models import (
    Account,
    AccountSubscription,
    Blueprint,
    Payment,
    Request,
    SubscriptionPlan,
    Tenant,
    TenantInvite,
)


async def tenant_stats(session, tenant_id: int, *, period_days: int = 30) -> dict:
    """Return a dict of aggregated stats for *tenant_id*.

    Fixed windows (independent of *period_days*):
      - dau: distinct accounts with last_seen_at within the last 1 day
      - wau: distinct accounts with last_seen_at within the last 7 days
      - mau: distinct accounts with last_seen_at within the last 30 days

    Windowed metrics (window = now - timedelta(days=period_days)):
      - active_customers: count of accounts with last_seen_at >= window_start
      - paid_customers: distinct account_id in payments (status=paid, paid_at >= window_start)
      - requests_by_kind: {kind: count} for requests with created_at >= window_start
      - revenue_cents: SUM(amount_cents) for payments (status=paid, paid_at >= window_start)
      - llm_tokens_in / llm_tokens_out: SUM over blueprints with created_at >= window_start

    Not windowed:
      - mrr_cents: SUM of SubscriptionPlan.price_cents for active/grace subscriptions

    Returns dict with all keys plus ``period_days``.
    """
    now = utcnow()
    window_start = now - timedelta(days=period_days)

    # --- Fixed DAU/WAU/MAU windows ---
    now_minus_1d = now - timedelta(days=1)
    now_minus_7d = now - timedelta(days=7)
    now_minus_30d = now - timedelta(days=30)

    dau_result = await session.execute(
        select(func.count(distinct(Account.id))).where(
            Account.tenant_id == tenant_id,
            Account.last_seen_at >= now_minus_1d,
        )
    )
    dau: int = dau_result.scalar_one()

    wau_result = await session.execute(
        select(func.count(distinct(Account.id))).where(
            Account.tenant_id == tenant_id,
            Account.last_seen_at >= now_minus_7d,
        )
    )
    wau: int = wau_result.scalar_one()

    mau_result = await session.execute(
        select(func.count(distinct(Account.id))).where(
            Account.tenant_id == tenant_id,
            Account.last_seen_at >= now_minus_30d,
        )
    )
    mau: int = mau_result.scalar_one()

    # --- active_customers: accounts with last_seen_at in the period window ---
    active_result = await session.execute(
        select(func.count(Account.id)).where(
            Account.tenant_id == tenant_id,
            Account.last_seen_at >= window_start,
        )
    )
    active_customers: int = active_result.scalar_one()

    # --- paid_customers: distinct accounts that paid within the window ---
    paid_cust_result = await session.execute(
        select(func.count(distinct(Payment.account_id))).where(
            Payment.tenant_id == tenant_id,
            Payment.status == "paid",
            Payment.paid_at >= window_start,
        )
    )
    paid_customers: int = paid_cust_result.scalar_one()

    # --- requests_by_kind: group by kind within the window ---
    requests_result = await session.execute(
        select(Request.kind, func.count(Request.id))
        .where(
            Request.tenant_id == tenant_id,
            Request.created_at >= window_start,
        )
        .group_by(Request.kind)
    )
    requests_by_kind: dict[str, int] = {kind: count for kind, count in requests_result.all()}

    # --- revenue_cents: sum of paid payments within window ---
    revenue_result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
            Payment.tenant_id == tenant_id,
            Payment.status == "paid",
            Payment.paid_at >= window_start,
        )
    )
    revenue_cents: int = revenue_result.scalar_one()

    # --- mrr_cents: sum of plan prices for active/grace subscriptions (not windowed) ---
    mrr_result = await session.execute(
        select(func.coalesce(func.sum(SubscriptionPlan.price_cents), 0))
        .select_from(AccountSubscription)
        .join(SubscriptionPlan, SubscriptionPlan.id == AccountSubscription.plan_id)
        .where(
            AccountSubscription.tenant_id == tenant_id,
            AccountSubscription.status.in_(("active", "grace")),
        )
    )
    mrr_cents: int = mrr_result.scalar_one()

    # --- llm tokens: sum over blueprints within window ---
    tokens_result = await session.execute(
        select(
            func.coalesce(func.sum(Blueprint.llm_tokens_in), 0),
            func.coalesce(func.sum(Blueprint.llm_tokens_out), 0),
        ).where(
            Blueprint.tenant_id == tenant_id,
            Blueprint.created_at >= window_start,
        )
    )
    tokens_in, tokens_out = tokens_result.one()

    return {
        "period_days": period_days,
        "active_customers": active_customers,
        "paid_customers": paid_customers,
        "dau": dau,
        "wau": wau,
        "mau": mau,
        "requests_by_kind": requests_by_kind,
        "revenue_cents": int(revenue_cents),
        "mrr_cents": int(mrr_cents),
        "llm_tokens_in": int(tokens_in),
        "llm_tokens_out": int(tokens_out),
    }


async def platform_stats(session, *, period_days: int = 30) -> dict:
    """Return platform-wide aggregated stats across ALL tenants (Plan 5b, Task 13).

    Headline metrics are computed with the SAME aggregation queries as
    ``tenant_stats`` but WITHOUT the ``tenant_id`` filter. This matters for the
    distinct-count metrics (active_customers, paid_customers, dau/wau/mau): they
    must be computed globally, not by summing per-tenant counts (which would
    double-count nothing here since accounts belong to one tenant, but the
    correct/robust approach is a single global distinct query).

    In addition to the global headline metrics, returns:
      - ``per_tenant``: list of headline numbers per non-platform Tenant, by
        calling :func:`tenant_stats` for each (excludes is_platform tenants).
      - ``funnel``: onboarding funnel counts.
      - ``period_days``.
    """
    now = utcnow()
    window_start = now - timedelta(days=period_days)

    # --- Fixed DAU/WAU/MAU windows (global distinct counts) ---
    now_minus_1d = now - timedelta(days=1)
    now_minus_7d = now - timedelta(days=7)
    now_minus_30d = now - timedelta(days=30)

    dau_result = await session.execute(
        select(func.count(distinct(Account.id))).where(Account.last_seen_at >= now_minus_1d)
    )
    dau: int = dau_result.scalar_one()

    wau_result = await session.execute(
        select(func.count(distinct(Account.id))).where(Account.last_seen_at >= now_minus_7d)
    )
    wau: int = wau_result.scalar_one()

    mau_result = await session.execute(
        select(func.count(distinct(Account.id))).where(Account.last_seen_at >= now_minus_30d)
    )
    mau: int = mau_result.scalar_one()

    # --- active_customers: accounts with last_seen_at in the period window ---
    active_result = await session.execute(
        select(func.count(Account.id)).where(Account.last_seen_at >= window_start)
    )
    active_customers: int = active_result.scalar_one()

    # --- paid_customers: distinct accounts that paid within the window (global) ---
    paid_cust_result = await session.execute(
        select(func.count(distinct(Payment.account_id))).where(
            Payment.status == "paid",
            Payment.paid_at >= window_start,
        )
    )
    paid_customers: int = paid_cust_result.scalar_one()

    # --- requests_by_kind: group by kind within the window (summed globally) ---
    requests_result = await session.execute(
        select(Request.kind, func.count(Request.id))
        .where(Request.created_at >= window_start)
        .group_by(Request.kind)
    )
    requests_by_kind: dict[str, int] = {kind: count for kind, count in requests_result.all()}

    # --- revenue_cents: sum of paid payments within window ---
    revenue_result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
            Payment.status == "paid",
            Payment.paid_at >= window_start,
        )
    )
    revenue_cents: int = revenue_result.scalar_one()

    # --- mrr_cents: sum of plan prices for active/grace subscriptions (not windowed) ---
    mrr_result = await session.execute(
        select(func.coalesce(func.sum(SubscriptionPlan.price_cents), 0))
        .select_from(AccountSubscription)
        .join(SubscriptionPlan, SubscriptionPlan.id == AccountSubscription.plan_id)
        .where(AccountSubscription.status.in_(("active", "grace")))
    )
    mrr_cents: int = mrr_result.scalar_one()

    # --- llm tokens: sum over blueprints within window ---
    tokens_result = await session.execute(
        select(
            func.coalesce(func.sum(Blueprint.llm_tokens_in), 0),
            func.coalesce(func.sum(Blueprint.llm_tokens_out), 0),
        ).where(Blueprint.created_at >= window_start)
    )
    tokens_in, tokens_out = tokens_result.one()

    # --- per-tenant breakdown (exclude platform tenants) ---
    tenants_result = await session.execute(
        select(Tenant).where(Tenant.is_platform == False).order_by(Tenant.id)  # noqa: E712
    )
    tenants = tenants_result.scalars().all()
    per_tenant: list[dict] = []
    for t in tenants:
        ts = await tenant_stats(session, t.id, period_days=period_days)
        per_tenant.append(
            {
                "tenant_id": t.id,
                "slug": t.slug,
                "active_customers": ts["active_customers"],
                "paid_customers": ts["paid_customers"],
                "revenue_cents": ts["revenue_cents"],
                "mrr_cents": ts["mrr_cents"],
            }
        )

    # --- onboarding funnel ---
    invites_issued_result = await session.execute(select(func.count(TenantInvite.id)))
    invites_issued: int = invites_issued_result.scalar_one()

    invites_used_result = await session.execute(
        select(func.count(TenantInvite.id)).where(
            (TenantInvite.status == "used") | (TenantInvite.used_count > 0)
        )
    )
    invites_used: int = invites_used_result.scalar_one()

    active_tenants_result = await session.execute(
        select(func.count(Tenant.id)).where(
            Tenant.status == "active",
            Tenant.is_platform == False,  # noqa: E712
        )
    )
    active_tenants: int = active_tenants_result.scalar_one()

    return {
        "period_days": period_days,
        "active_customers": active_customers,
        "paid_customers": paid_customers,
        "dau": dau,
        "wau": wau,
        "mau": mau,
        "requests_by_kind": requests_by_kind,
        "revenue_cents": int(revenue_cents),
        "mrr_cents": int(mrr_cents),
        "llm_tokens_in": int(tokens_in),
        "llm_tokens_out": int(tokens_out),
        "per_tenant": per_tenant,
        "funnel": {
            "invites_issued": invites_issued,
            "invites_used": invites_used,
            "active_tenants": active_tenants,
        },
    }
