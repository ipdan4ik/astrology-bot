from quantuum.auth.identity import find_or_create_account_by_tg
from quantuum.bot.rendering.signature import append_signature
from quantuum.domain.tenant_branding import set_branding_text
from quantuum.i18n.cache import invalidate_i18n


async def test_empty_signature_returns_body_unchanged(session, default_tenant):
    out = await append_signature(
        "BODY", tenant_id=default_tenant.id, lang="ru"
    )
    assert out == "BODY"


async def test_set_signature_appends_with_blank_line(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="sig1"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
        text="© Mystic Oracle",
        by_account_id=acc.id,
    )
    await session.commit()
    await invalidate_i18n(default_tenant.id, "ru")

    out = await append_signature(
        "BODY", tenant_id=default_tenant.id, lang="ru"
    )
    assert out == "BODY\n\n© Mystic Oracle"


async def test_whitespace_only_signature_treated_as_empty(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="sig2"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
        text="   ",
        by_account_id=acc.id,
    )
    await session.commit()
    await invalidate_i18n(default_tenant.id, "ru")

    out = await append_signature(
        "BODY", tenant_id=default_tenant.id, lang="ru"
    )
    assert out == "BODY"


async def test_signature_per_lang_routing(session, default_tenant):
    acc = await find_or_create_account_by_tg(
        session, tenant_id=default_tenant.id, tg_user_id="sig3"
    )
    await set_branding_text(
        session,
        tenant_id=default_tenant.id,
        key="brand.signature",
        lang="ru",
        text="© RU only",
        by_account_id=acc.id,
    )
    await session.commit()
    await invalidate_i18n(default_tenant.id, "ru")
    await invalidate_i18n(default_tenant.id, "en")

    ru_out = await append_signature(
        "BODY", tenant_id=default_tenant.id, lang="ru"
    )
    en_out = await append_signature(
        "BODY", tenant_id=default_tenant.id, lang="en"
    )
    assert ru_out == "BODY\n\n© RU only"
    assert en_out == "BODY"  # platform default is ""
