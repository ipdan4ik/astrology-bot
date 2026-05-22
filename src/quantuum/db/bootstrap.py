from sqlmodel import select

from quantuum.common.crypto import encrypt_token
from quantuum.common.datetime import utcnow
from quantuum.db.models import Account, AccountIdentity, PackagePlan, PlatformString, SubscriptionPlan, Tenant, TenantBot, TenantLanguage
from quantuum.domain.tenants import get_default_tenant_id
from quantuum.settings import get_settings


async def ensure_default_tenant(session) -> Tenant:
    settings = get_settings()
    result = await session.execute(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(slug=settings.default_tenant_slug, display_name=settings.default_tenant_name)
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
    return tenant


async def ensure_default_tenant_bot(session) -> None:
    """Migrate the env BOT_TOKEN into a tenant_bots row for the default tenant (idempotent)."""
    settings = get_settings()
    token = settings.bot_token
    if not token:
        return
    bot_id = int(token.split(":")[0])
    existing = await session.execute(
        select(TenantBot).where(TenantBot.bot_telegram_id == bot_id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    tenant_id = await get_default_tenant_id(session)
    session.add(
        TenantBot(
            tenant_id=tenant_id,
            bot_telegram_id=bot_id,
            bot_token_enc=encrypt_token(token),
            transport=settings.default_bot_transport,
            webhook_secret_path=settings.webhook_secret_path or f"tg-{bot_id}",
        )
    )
    await session.commit()


async def ensure_platform_tenant(session) -> Tenant:
    settings = get_settings()
    result = await session.execute(
        select(Tenant).where(Tenant.slug == settings.platform_tenant_slug)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(
            slug=settings.platform_tenant_slug,
            display_name=settings.platform_tenant_name,
            is_platform=True,
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
    return tenant


async def ensure_master_bot(session) -> None:
    """Migrate env MASTER_BOT_TOKEN into the platform tenant's tenant_bots row (idempotent)."""
    settings = get_settings()
    token = settings.master_bot_token
    if not token:
        return
    bot_id = int(token.split(":")[0])
    existing = await session.execute(
        select(TenantBot).where(TenantBot.bot_telegram_id == bot_id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    platform = await ensure_platform_tenant(session)
    session.add(
        TenantBot(
            tenant_id=platform.id,
            bot_telegram_id=bot_id,
            bot_username=settings.master_bot_username or None,
            bot_token_enc=encrypt_token(token),
            transport=settings.default_bot_transport,
            webhook_secret_path=f"master-{bot_id}",
        )
    )
    await session.commit()


async def ensure_superadmin(session) -> None:
    """Create the bootstrap superadmin from env and idempotently link its Telegram
    identity (both env-gated, idempotent across restarts)."""
    settings = get_settings()
    email = settings.bootstrap_superadmin_email
    if not email:
        return

    existing = await session.execute(
        select(AccountIdentity).where(
            AccountIdentity.provider == "magic_link", AccountIdentity.email == email
        )
    )
    identity = existing.scalar_one_or_none()
    if identity is not None:
        account_id = identity.account_id
    else:
        account = Account(tenant_id=None, is_superadmin=True)
        session.add(account)
        await session.flush()
        session.add(
            AccountIdentity(
                account_id=account.id, provider="magic_link", email=email, verified_at=utcnow()
            )
        )
        account_id = account.id

    tg_id = settings.bootstrap_superadmin_tg_id
    if tg_id:
        # The env var is authoritative for the superadmin's Telegram identity:
        # drop any previously-linked tg_chat identities that don't match (so
        # rotating BOOTSTRAP_SUPERADMIN_TG_ID revokes the old one), then ensure
        # the configured one exists. Idempotent across restarts.
        rows = (
            await session.execute(
                select(AccountIdentity).where(
                    AccountIdentity.provider == "tg_chat",
                    AccountIdentity.account_id == account_id,
                )
            )
        ).scalars().all()
        has_current = False
        for row in rows:
            if row.provider_user_id == tg_id:
                has_current = True
            else:
                await session.delete(row)
        if not has_current:
            session.add(
                AccountIdentity(
                    account_id=account_id,
                    provider="tg_chat",
                    provider_user_id=tg_id,
                    verified_at=utcnow(),
                )
            )

    await session.commit()


async def ensure_global_plans(session) -> None:
    """Seed global (tenant_id NULL) plan structure with placeholder prices (idempotent).

    Prices are placeholders in XTR (Star amount) — adjust later via /admin/platform/plans.
    """
    sub_exists = await session.execute(
        select(SubscriptionPlan).where(
            SubscriptionPlan.tenant_id.is_(None), SubscriptionPlan.slug == "monthly"
        )
    )
    if sub_exists.scalar_one_or_none() is None:
        session.add(
            SubscriptionPlan(slug="monthly", name="Monthly", period_days=30, price_cents=250)
        )
    for slug, name, count, price in (
        ("pack_small", "Small pack", 5, 400),
        ("pack_large", "Large pack", 20, 1200),
    ):
        pkg_exists = await session.execute(
            select(PackagePlan).where(PackagePlan.tenant_id.is_(None), PackagePlan.slug == slug)
        )
        if pkg_exists.scalar_one_or_none() is None:
            session.add(PackagePlan(slug=slug, name=name, request_count=count, price_cents=price))
    await session.commit()


async def ensure_platform_stars_provider(session) -> None:
    """Seed a Telegram Stars provider row for the platform tenant (idempotent)."""
    from quantuum.domain.providers import ensure_stars_provider

    platform = await ensure_platform_tenant(session)
    await ensure_stars_provider(session, platform.id)


async def ensure_base_strings(session) -> None:
    """Idempotently INSERT missing (key, lang) rows into platform_strings.

    Only inserts rows that do not already exist — existing rows are never
    updated, so admin edits survive re-seed.  A single commit is issued at
    the end only when at least one row was inserted.
    """
    from quantuum.i18n.seed_strings import BASE_STRINGS

    # Fetch all existing (key, lang) pairs in one query
    result = await session.execute(select(PlatformString.key, PlatformString.lang))
    existing: set[tuple[str, str]] = {(row[0], row[1]) for row in result.all()}

    added = False
    for key, lang_map in BASE_STRINGS.items():
        for lang, text in lang_map.items():
            if (key, lang) not in existing:
                session.add(PlatformString(key=key, lang=lang, text=text))
                added = True

    if added:
        await session.commit()


async def ensure_tenant_default_language(
    session,
    tenant_id: int,
    default_lang: str = "ru",
    extra_langs: tuple[str, ...] = ("en",),
) -> None:
    """Idempotently ensure TenantLanguage rows for *tenant_id*.

    * default_lang gets is_default=True, enabled=True.
    * each lang in extra_langs gets is_default=False, enabled=True.
    * Never creates duplicate rows; never flips an already-set default.
    """
    result = await session.execute(
        select(TenantLanguage).where(TenantLanguage.tenant_id == tenant_id)
    )
    existing: dict[str, TenantLanguage] = {row.lang: row for row in result.scalars()}

    all_langs = [(default_lang, True)] + [(lang, False) for lang in extra_langs]
    added = False
    for lang, is_default in all_langs:
        if lang not in existing:
            session.add(
                TenantLanguage(
                    tenant_id=tenant_id,
                    lang=lang,
                    enabled=True,
                    is_default=is_default,
                )
            )
            added = True

    if added:
        await session.commit()
