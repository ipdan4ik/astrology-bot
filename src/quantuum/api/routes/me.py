from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from quantuum.api.deps import current_account, get_session
from quantuum.api.schemas import (
    BalanceOut,
    BlueprintCreatedOut,
    BlueprintOut,
    DailyHoroscopeOut,
    DailySettingsIn,
    DailySettingsOut,
    MeOut,
    NatalProfileIn,
    NatalProfileOut,
    PackagePlanOut,
    PaymentOut,
    PlansOut,
    PurchaseIn,
    QaCreatedOut,
    QaCreateIn,
    QaOut,
    SubscriptionOut,
    SubscriptionPlanOut,
    TransitCreatedOut,
    TransitCreateIn,
    TransitOut,
)
from quantuum.common.exceptions import InsufficientFundsError, NotFoundError
from quantuum.db.models import Account, AccountBalance, AccountSubscription, Blueprint, Payment
from quantuum.domain.plans import (
    get_package_plan,
    get_subscription_plan,
    list_package_plans,
    list_subscription_plans,
)
from quantuum.domain.providers import get_active_provider
from quantuum.payments.base import PaymentNotSupportedInApiError
from quantuum.payments.registry import provider_for_kind
from quantuum.domain.blueprints import create_blueprint, get_blueprint
from quantuum.domain.natal_profiles import get_natal_profile, upsert_natal_profile
from quantuum.domain.qa import create_qa, get_qa, list_qa
from quantuum.domain.transits import create_transit, get_transit, list_transits
from quantuum.domain.daily import get_settings, is_subscriber, list_horoscopes, upsert_settings
from quantuum.domain.quota import consume_quota, refund_quota
from quantuum.i18n import resolve_lang
from quantuum.domain.requests import create_request
from quantuum.tasks import enqueue

router = APIRouter(prefix="/v1/me", tags=["me"])


@router.get("", response_model=MeOut)
async def get_me(account: Account = Depends(current_account)) -> MeOut:
    return MeOut(account_id=account.id, tenant_id=account.tenant_id)


@router.get("/natal-profile", response_model=NatalProfileOut)
async def read_natal_profile(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> NatalProfileOut:
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="no natal profile")
    return NatalProfileOut(
        id=profile.id,
        full_name=profile.full_name,
        birth_date=profile.birth_date,
        birth_time=profile.birth_time,
        birth_place=profile.birth_place,
        latitude=profile.latitude,
        longitude=profile.longitude,
        timezone=profile.timezone,
        for_year=profile.for_year,
    )


@router.put("/natal-profile", response_model=NatalProfileOut)
async def write_natal_profile(
    body: NatalProfileIn,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> NatalProfileOut:
    profile = await upsert_natal_profile(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        full_name=body.full_name,
        birth_date=body.birth_date,
        birth_time=body.birth_time,
        birth_place=body.birth_place,
        latitude=body.latitude,
        longitude=body.longitude,
        timezone=body.timezone,
        for_year=body.for_year,
    )
    return NatalProfileOut(
        id=profile.id,
        full_name=profile.full_name,
        birth_date=profile.birth_date,
        birth_time=profile.birth_time,
        birth_place=profile.birth_place,
        latitude=profile.latitude,
        longitude=profile.longitude,
        timezone=profile.timezone,
        for_year=profile.for_year,
    )


@router.post("/blueprints", response_model=BlueprintCreatedOut, status_code=201)
async def create_blueprint_route(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> BlueprintCreatedOut:
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        raise HTTPException(status_code=409, detail="natal profile required")
    try:
        charged = await consume_quota(session, account.id, "blueprint")
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=402, detail="no quota; buy a plan") from exc

    blueprint = await create_blueprint(
        session, tenant_id=account.tenant_id, account_id=account.id, natal_profile_id=profile.id
    )
    request = await create_request(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        kind="blueprint",
        charged_against=charged,
    )
    try:
        await enqueue.enqueue_blueprint(blueprint.id, None, request.id)
    except Exception as exc:
        await refund_quota(session, request.id)
        raise HTTPException(status_code=503, detail="could not enqueue; refunded") from exc
    return BlueprintCreatedOut(id=blueprint.id, status=blueprint.status)


@router.get("/blueprints", response_model=list[BlueprintOut])
async def list_blueprints(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[BlueprintOut]:
    result = await session.execute(
        select(Blueprint).where(Blueprint.account_id == account.id).order_by(Blueprint.id.desc())
    )
    return [
        BlueprintOut(
            id=bp.id,
            status=bp.status,
            created_at=bp.created_at.isoformat(),
            completed_at=bp.completed_at.isoformat() if bp.completed_at else None,
        )
        for bp in result.scalars().all()
    ]


@router.get("/blueprints/{blueprint_id}", response_model=BlueprintOut)
async def read_blueprint(
    blueprint_id: int,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> BlueprintOut:
    bp = await get_blueprint(session, blueprint_id)
    if bp.account_id != account.id:
        raise HTTPException(status_code=404, detail="not found")
    return BlueprintOut(
        id=bp.id,
        status=bp.status,
        created_at=bp.created_at.isoformat(),
        completed_at=bp.completed_at.isoformat() if bp.completed_at else None,
    )


@router.get("/blueprints/{blueprint_id}/download")
async def download_blueprint(
    blueprint_id: int,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> Response:
    bp = await get_blueprint(session, blueprint_id)
    if bp.account_id != account.id:
        raise HTTPException(status_code=404, detail="not found")
    if not bp.llm_md:
        raise HTTPException(status_code=409, detail="not ready")
    return Response(
        content=bp.llm_md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="blueprint-{bp.id}.md"'},
    )


def _qa_out(qa) -> QaOut:
    return QaOut(
        id=qa.id,
        question=qa.question,
        answer_md=qa.answer_md,
        status=qa.status,
        lang=qa.lang,
        created_at=qa.created_at,
        completed_at=qa.completed_at,
    )


@router.post("/qa", response_model=QaCreatedOut, status_code=202)
async def create_qa_route(
    body: QaCreateIn,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> QaCreatedOut:
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="natal profile required")

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question required")
    if len(question) > 1000:
        question = question[:1000]

    lang = await resolve_lang(
        session,
        tenant_id=account.tenant_id,
        preferred_lang=account.preferred_lang,
        tg_language_code=None,
    )

    try:
        charged = await consume_quota(session, account.id, "qa")
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=402, detail="insufficient quota") from exc

    request = await create_request(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        kind="qa",
        charged_against=charged,
    )
    qa = await create_qa(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        natal_profile_id=profile.id,
        question=question,
        lang=lang,
    )
    try:
        await enqueue.enqueue_qa(qa.id, None, request.id)
    except Exception as exc:
        await refund_quota(session, request.id)
        raise HTTPException(status_code=503, detail="could not enqueue; refunded") from exc
    return QaCreatedOut(id=qa.id, status=qa.status)


@router.get("/qa", response_model=list[QaOut])
async def list_qa_route(
    limit: int = 50,
    offset: int = 0,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[QaOut]:
    rows = await list_qa(session, account_id=account.id, limit=limit, offset=offset)
    return [_qa_out(qa) for qa in rows]


@router.get("/qa/{qa_id}", response_model=QaOut)
async def read_qa_route(
    qa_id: int,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> QaOut:
    try:
        qa = await get_qa(session, qa_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="not found") from exc
    if qa.account_id != account.id:
        raise HTTPException(status_code=404, detail="not found")
    return _qa_out(qa)


def _transit_out(row) -> TransitOut:
    return TransitOut(
        id=row.id,
        window_days=row.window_days,
        as_of=row.as_of,
        report_md=row.report_md,
        status=row.status,
        lang=row.lang,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


@router.post("/transits", response_model=TransitCreatedOut, status_code=202)
async def create_transit_route(
    body: TransitCreateIn,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> TransitCreatedOut:
    profile = await get_natal_profile(session, account.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="natal profile required")

    lang = await resolve_lang(
        session,
        tenant_id=account.tenant_id,
        preferred_lang=account.preferred_lang,
        tg_language_code=None,
    )

    try:
        charged = await consume_quota(session, account.id, "transit")
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=402, detail="insufficient quota") from exc

    request = await create_request(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        kind="transit",
        charged_against=charged,
    )
    row = await create_transit(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        natal_profile_id=profile.id,
        window_days=body.window_days,  # create_transit clamps to [MIN, MAX], default if None
        lang=lang,
    )
    try:
        await enqueue.enqueue_transit(row.id, None, request.id)
    except Exception as exc:
        await refund_quota(session, request.id)
        raise HTTPException(status_code=503, detail="could not enqueue; refunded") from exc
    return TransitCreatedOut(id=row.id, status=row.status)


@router.get("/transits", response_model=list[TransitOut])
async def list_transits_route(
    limit: int = 50,
    offset: int = 0,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[TransitOut]:
    rows = await list_transits(session, account_id=account.id, limit=limit, offset=offset)
    return [_transit_out(row) for row in rows]


@router.get("/transits/{report_id}", response_model=TransitOut)
async def read_transit_route(
    report_id: int,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> TransitOut:
    try:
        row = await get_transit(session, report_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="not found") from exc
    if row.account_id != account.id:
        raise HTTPException(status_code=404, detail="not found")
    return _transit_out(row)


def _daily_horoscope_out(row) -> DailyHoroscopeOut:
    return DailyHoroscopeOut(
        id=row.id,
        local_date=row.local_date,
        horoscope_md=row.horoscope_md,
        status=row.status,
        lang=row.lang,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


@router.get("/daily", response_model=DailySettingsOut)
async def read_daily_settings(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> DailySettingsOut:
    row = await get_settings(session, account.id)
    if row is None:
        return DailySettingsOut(enabled=False, send_hour=9, last_sent_on=None)
    return DailySettingsOut(enabled=row.enabled, send_hour=row.send_hour, last_sent_on=row.last_sent_on)


@router.put("/daily", response_model=DailySettingsOut)
async def write_daily_settings(
    body: DailySettingsIn,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> DailySettingsOut:
    if body.enabled and not await is_subscriber(session, account.id):
        raise HTTPException(status_code=403, detail="daily horoscope is a subscriber feature")
    row = await upsert_settings(
        session,
        tenant_id=account.tenant_id,
        account_id=account.id,
        enabled=body.enabled,
        send_hour=body.send_hour,
    )
    return DailySettingsOut(enabled=row.enabled, send_hour=row.send_hour, last_sent_on=row.last_sent_on)


@router.get("/daily/horoscopes", response_model=list[DailyHoroscopeOut])
async def list_daily_horoscopes(
    limit: int = 30,
    offset: int = 0,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[DailyHoroscopeOut]:
    rows = await list_horoscopes(session, account_id=account.id, limit=limit, offset=offset)
    return [_daily_horoscope_out(row) for row in rows]


@router.get("/balance", response_model=BalanceOut)
async def get_balance(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> BalanceOut:
    balance = await session.get(AccountBalance, account.id)
    if balance is None:
        return BalanceOut(free_trial_used=False, subscription_active_until=None, package_credits=0)
    return BalanceOut(
        free_trial_used=balance.free_trial_used,
        subscription_active_until=(
            balance.subscription_active_until.isoformat()
            if balance.subscription_active_until
            else None
        ),
        package_credits=balance.package_credits,
    )


@router.get("/plans", response_model=PlansOut)
async def get_plans(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> PlansOut:
    subs = await list_subscription_plans(session, tenant_id=account.tenant_id)
    pkgs = await list_package_plans(session, tenant_id=account.tenant_id)
    return PlansOut(
        subscriptions=[
            SubscriptionPlanOut(
                id=s.id, slug=s.slug, name=s.name, period_days=s.period_days,
                price_cents=s.price_cents, currency=s.currency,
            )
            for s in subs
        ],
        packages=[
            PackagePlanOut(
                id=p.id, slug=p.slug, name=p.name, request_count=p.request_count,
                price_cents=p.price_cents, currency=p.currency,
                expires_after_days=p.expires_after_days,
            )
            for p in pkgs
        ],
    )


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[SubscriptionOut]:
    result = await session.execute(
        select(AccountSubscription)
        .where(AccountSubscription.account_id == account.id)
        .order_by(AccountSubscription.id.desc())
    )
    return [
        SubscriptionOut(
            id=s.id, plan_id=s.plan_id, status=s.status,
            started_at=s.started_at.isoformat(), ends_at=s.ends_at.isoformat(),
        )
        for s in result.scalars().all()
    ]


@router.get("/payments", response_model=list[PaymentOut])
async def list_payments(
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> list[PaymentOut]:
    result = await session.execute(
        select(Payment).where(Payment.account_id == account.id).order_by(Payment.id.desc())
    )
    return [
        PaymentOut(
            id=p.id, amount_cents=p.amount_cents, currency=p.currency, status=p.status,
            created_at=p.created_at.isoformat(),
            paid_at=p.paid_at.isoformat() if p.paid_at else None,
        )
        for p in result.scalars().all()
    ]


async def _create_invoice_via_provider(
    session: AsyncSession, account: Account, *, plan_kind: str, plan
) -> None:
    """Route a purchase through the PaymentProvider abstraction.

    In MVP the only provider is Telegram Stars, which is bot-only and raises
    PaymentNotSupportedInApiError -> 501. Future HTTP providers will return an invoice URL here.
    """
    provider_row = await get_active_provider(session, account.tenant_id)
    impl = provider_for_kind(provider_row.kind) if provider_row else None
    if impl is None:
        raise HTTPException(status_code=501, detail="no payment provider configured")
    try:
        await impl.create_invoice(
            account_id=account.id,
            tenant_id=account.tenant_id,
            plan_kind=plan_kind,
            plan_id=plan.id,
            amount_cents=plan.price_cents,
            currency=plan.currency,
            metadata={"kind": plan_kind, "plan_id": plan.id},
        )
    except PaymentNotSupportedInApiError as exc:
        raise HTTPException(
            status_code=501, detail="this payment method is available only in the bot"
        ) from exc


@router.post("/subscriptions", status_code=201)
async def buy_subscription(
    body: PurchaseIn,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
):
    plan = await get_subscription_plan(session, body.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    await _create_invoice_via_provider(session, account, plan_kind="subscription", plan=plan)
    return {"status": "invoice_created"}  # unreachable in MVP (Stars raises 501)


@router.post("/packages", status_code=201)
async def buy_package(
    body: PurchaseIn,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
):
    plan = await get_package_plan(session, body.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    await _create_invoice_via_provider(session, account, plan_kind="package", plan=plan)
    return {"status": "invoice_created"}  # unreachable in MVP (Stars raises 501)
